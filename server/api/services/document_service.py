import os
import time
import json
from typing import Any, Dict

from fastapi import BackgroundTasks, HTTPException, UploadFile

from api.authz import get_owned_document
from api.deps import CurrentUser
from src.ingestion.pipeline import prepare_ingest, finish_ingest, SUPPORTED_EXTENSIONS
from src.security import verify_source_token
from src.storage.database import (
    document_filename_accessible,
    filename_in_use_by_other,
    get_document_status,
    list_documents,
)
from src.storage.files import get_source_path, save_upload

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
