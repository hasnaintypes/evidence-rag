import os
import time
import json
from typing import Any, Dict

from fastapi import BackgroundTasks, HTTPException, UploadFile

from api.authz import get_owned_document, get_owned_document_for_mutation
from api.deps import CurrentUser
from src.config import settings
from src.ingestion.pipeline import prepare_ingest, finish_ingest, SUPPORTED_EXTENSIONS
from src.response_cache import invalidate_doc_id
from src.retrieval.hybrid import invalidate_index_cache
from src.security import verify_source_token
from src.storage.database import (
    delete_document_data,
    delete_document_record,
    document_filename_accessible,
    filename_exists_elsewhere,
    filename_in_use_by_other,
    get_document_status,
    list_documents,
    rename_document,
)
from src.storage.files import delete_file, get_source_path, rename_file, save_upload

MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # matches the Supabase bucket's file size limit
SSE_WATCH_INTERVAL_SECONDS = 1.0


class DocumentService:
    """
    Owns document upload/ingestion, status, and source-file serving -
    loading the resource, asserting ownership via api/authz.py, then
    acting - so api/routers/documents.py stays a thin HTTP-shape adapter.
    See GitHub issue #18 / 02-Architecture.md's Proposed Changes.
    """

    @staticmethod
    def list_for_user(user: CurrentUser) -> Dict[str, Any]:
        """The caller's own uploaded documents plus shared/demo documents
        (docs/fixtures/sample_docs), used by the UI sidebar."""
        return {"documents": list_documents(user_id=user.id)}

    @staticmethod
    def upload(file: UploadFile, user: CurrentUser, background_tasks: BackgroundTasks) -> Dict[str, Any]:
        """
        Saves and parses/chunks an uploaded document inline (fast, local CPU
        work), then hands the slow part - one Gemini embedding call per chunk -
        to a background task instead of holding the request open for however
        long that takes (large documents were taking 25+ minutes end-to-end).
        The caller polls get_status()/the SSE stream for progress.

        Runs the exact same pipeline as scripts/ingest.py's per-file logic
        (tree-aware parsing for PDFs, hash-based dedup, doc_id tracking) so a
        file uploaded through the UI is indexed identically to one placed in
        docs/fixtures/sample_docs and ingested via the CLI script.
        """
        filename = file.filename
        ext = os.path.splitext(filename)[1].lower()

        if ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400, detail=f"Unsupported file format. Supported types: {', '.join(SUPPORTED_EXTENSIONS)}"
            )

        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        file.file.seek(0)
        if size > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=413, detail=f"File exceeds the 50MB upload limit ({size / 1024 / 1024:.1f}MB)."
            )

        # File storage (src/storage/files.py) keys the actual bytes purely by
        # filename with no per-user namespacing, so without this check a
        # same-named upload would silently overwrite a shared/demo document's
        # or another user's file content on disk/in Storage - see
        # filename_in_use_by_other()'s docstring.
        if filename_in_use_by_other(filename, user.id):
            raise HTTPException(
                status_code=409,
                detail=f"'{filename}' matches an existing document you don't own - rename the file and try again.",
            )

        try:
            with save_upload(filename, file.file) as file_path:
                prep = prepare_ingest(file_path, filename, user_id=user.id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"File processing error: {str(e)}")

        if prep["status"] == "unchanged":
            return {
                "status": "unchanged",
                "message": f"'{filename}' is identical to the already-indexed version - skipped.",
                "analytics": {"chunk_count": 0},
                "doc_id": prep["doc_id"],
            }

        if prep["status"] == "empty":
            raise HTTPException(status_code=400, detail="The file content is empty or could not be chunked properly.")

        background_tasks.add_task(finish_ingest, prep["doc_id"], prep["chunks_data"])

        return {
            "status": "processing",
            "message": f"'{filename}' is being indexed…",
            "doc_id": prep["doc_id"],
            "analytics": {"chunk_count": len(prep["chunks_data"])},
        }

    @staticmethod
    def rename(doc_id: str, new_filename: str, user: CurrentUser) -> Dict[str, Any]:
        """
        Updates the display/storage filename only - doc_id (and every
        chunk/node/entity/conversation reference keyed by it) is left
        untouched, so existing chat history and citations over this
        document keep working after a rename. Restricted to the caller's
        own uploads (get_owned_document_for_mutation 403s on a shared/
        demo document) since it also moves the underlying stored file.
        """
        record = get_owned_document_for_mutation(doc_id, user)
        new_filename = DocumentService._safe_filename(new_filename)

        old_ext = os.path.splitext(record["filename"])[1].lower()
        new_ext = os.path.splitext(new_filename)[1].lower()
        if new_ext != old_ext:
            raise HTTPException(
                status_code=400,
                detail=f"Can't change a document's file type on rename (still '{old_ext}').",
            )

        if filename_exists_elsewhere(new_filename, exclude_doc_id=doc_id):
            raise HTTPException(status_code=409, detail=f"'{new_filename}' is already in use by another document.")

        rename_file(record["filename"], new_filename)
        rename_document(doc_id, new_filename)
        return {"status": "renamed", "doc_id": doc_id, "filename": new_filename}

    @staticmethod
    def delete(doc_id: str, user: CurrentUser) -> Dict[str, Any]:
        """
        Removes the document row, its chunks/nodes/entities/edges, its
        stored file, and any response-cache entries scoped to it.
        Restricted to the caller's own uploads, same as rename() above.
        Conversations that already reference this doc_id are left as-is -
        retrieval for a doc_id with no remaining chunks just yields
        nothing for that document, the same as any other zero-chunk
        scope, rather than erroring.
        """
        record = get_owned_document_for_mutation(doc_id, user)
        delete_document_data(doc_id)
        delete_document_record(doc_id)
        delete_file(record["filename"])
        invalidate_doc_id(doc_id)
        invalidate_index_cache()
        return {"status": "deleted"}

    @staticmethod
    def reingest(doc_id: str, user: CurrentUser, background_tasks: BackgroundTasks) -> Dict[str, Any]:
        """
        Re-runs the ingestion pipeline against the already-stored file,
        bypassing prepare_ingest()'s hash-based "unchanged" short-circuit
        (force=True) since the point of this action is "redo this
        document's chunks/embeddings now", not "only if the bytes
        changed" - that path is what a plain re-upload already covers.
        Same background-task handoff as upload() so the request doesn't
        block on embedding calls.
        """
        record = get_owned_document_for_mutation(doc_id, user)
        file_path = get_source_path(record["filename"])
        if not file_path:
            raise HTTPException(status_code=404, detail="The stored file for this document is missing.")

        try:
            prep = prepare_ingest(file_path, record["filename"], user_id=user.id, force=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"File processing error: {str(e)}")
        finally:
            # get_source_path() downloads to a fresh temp file in supabase
            # mode (see its docstring) - parsing/chunking above is the only
            # thing that reads it, so it's safe to clean up right here,
            # unlike GET /source/{filename}'s use of the same function,
            # which still needs the path alive for FileResponse to stream.
            # Local mode's file_path IS the permanent stored file - must
            # not delete it.
            if settings.storage_mode == "supabase":
                os.remove(file_path)

        if prep["status"] == "empty":
            raise HTTPException(status_code=400, detail="The file content is empty or could not be chunked properly.")

        background_tasks.add_task(finish_ingest, prep["doc_id"], prep["chunks_data"])
        invalidate_index_cache()

        return {
            "status": "processing",
            "message": f"'{record['filename']}' is being re-indexed…",
            "doc_id": prep["doc_id"],
            "analytics": {"chunk_count": len(prep["chunks_data"])},
        }

    @staticmethod
    def get_status(doc_id: str, user: CurrentUser) -> Dict[str, Any]:
        """One-shot status read, used by the UI for the initial render
        before the SSE stream below takes over."""
        get_owned_document(doc_id, user)
        status = get_document_status(doc_id)
        if not status:
            raise HTTPException(status_code=404, detail="Document not found.")
        return status

    @staticmethod
    def status_stream(doc_id: str, user: CurrentUser):
        """Server-Sent Events generator for a document's indexing status -
        the production-grade replacement for polling get_status() on an
        interval. Ownership is asserted once, up front, before the
        long-lived generator starts."""
        get_owned_document(doc_id, user)
        return DocumentService._status_stream_generator(doc_id)

    @staticmethod
    def _status_stream_generator(doc_id: str):
        """
        Pushes a status event to the client whenever it changes, instead of the
        UI re-requesting on a timer - a single long-lived connection replaces
        what used to be a client-side setInterval poll loop. The server still
        re-reads the row on an interval under the hood (finish_ingest's progress
        writer runs on its own background thread with no event to subscribe to
        directly), but that cost is ours to pay once here rather than once per
        connected client re-fetching over and over.

        A plain generator (not async) because the rest of this API is sync for
        DB connection pooling - Starlette runs it in the threadpool, same as
        any other sync route.
        """
        last_payload = None
        while True:
            status = get_document_status(doc_id)
            if not status:
                yield f"event: error\ndata: {json.dumps({'detail': 'Document not found.'})}\n\n"
                return

            payload = json.dumps(status)
            if payload != last_payload:
                yield f"data: {payload}\n\n"
                last_payload = payload

            if status["status"] in ("ready", "failed"):
                return

            time.sleep(SSE_WATCH_INTERVAL_SECONDS)

    @staticmethod
    def resolve_source_path(filename: str, token: str) -> str:
        """
        Resolves an ingested source file's on-disk/storage path for the
        citation viewer, enforcing ownership via a short-lived signed
        `token` (src/security.py) rather than get_current_user - see
        api/routers/documents.py's serve_source_document() docstring for
        why that route can't require a bearer token.
        """
        safe_name = DocumentService._safe_filename(filename)

        user_id = verify_source_token(safe_name, token)
        if user_id is None:
            raise HTTPException(status_code=403, detail="Invalid or expired source link.")
        if not document_filename_accessible(safe_name, user_id):
            raise HTTPException(status_code=404, detail=f"Source file '{safe_name}' not found.")

        file_path = get_source_path(safe_name)
        if not file_path:
            raise HTTPException(status_code=404, detail=f"Source file '{safe_name}' not found.")

        return file_path

    @staticmethod
    def _safe_filename(filename: str) -> str:
        """Prevents path traversal (e.g. "../../etc/passwd") when serving
        files by name. Only allows the plain filename, no directory separators."""
        return os.path.basename(filename)
