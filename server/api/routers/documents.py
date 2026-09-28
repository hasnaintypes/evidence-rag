import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from api.deps import get_current_user, CurrentUser
from src.storage.database import list_documents
from src.storage.files import save_upload, get_source_path
from src.ingestion.pipeline import ingest_file, SUPPORTED_EXTENSIONS

router = APIRouter()

MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # matches the Supabase bucket's file size limit


@router.get("/documents")
async def documents_endpoint(user: CurrentUser = Depends(get_current_user)):
    """Returns the caller's own uploaded documents plus shared/demo
    documents (docs/sample_docs), used by the UI sidebar."""
    return {"documents": list_documents(user_id=user.id)}


@router.post("/upload")
async def upload_file_endpoint(file: UploadFile = File(...), user: CurrentUser = Depends(get_current_user)):
    """
    Saves, parses, chunks, embeds, and indexes an uploaded document,
    owned by the authenticated caller.

    Runs the exact same pipeline as scripts/ingest.py's per-file logic
    (tree-aware parsing for PDFs, hash-based dedup, doc_id tracking) so a
    file uploaded through the UI is indexed identically to one placed in
    docs/sample_docs and ingested via the CLI script.
    """
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Supported types: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the 50MB upload limit ({size / 1024 / 1024:.1f}MB)."
        )

    try:
        with save_upload(filename, file.file) as file_path:
            result = ingest_file(file_path, filename, user_id=user.id)

        if result["status"] == "unchanged":
            return {
                "status": "unchanged",
                "message": f"'{filename}' is identical to the already-indexed version - skipped.",
                "analytics": {"chunk_count": 0},
                "doc_id": result["doc_id"],
            }

        if result["status"] == "empty":
            raise HTTPException(status_code=400, detail="The file content is empty or could not be chunked properly.")

        return {
            "status": "success",
            "message": f"'{filename}' successfully indexed into {result['chunk_count']} chunks.",
            "analytics": {"chunk_count": result["chunk_count"]},
            "doc_id": result["doc_id"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File processing error: {str(e)}")


def _safe_filename(filename: str) -> str:
    """
    Prevents path traversal (e.g. "../../etc/passwd") when serving files
    by name. Only allows the plain filename, no directory separators.
    """
    return os.path.basename(filename)


@router.get("/source/{filename}")
async def serve_source_document(filename: str):
    """
    Serves an ingested source file for the citation viewer. The UI links
    to this with a #page=N fragment, which browser-native PDF viewers
    (Chrome, Firefox, Edge) honor to jump straight to that page - no
    PDF.js integration needed for this simple version.

    Intentionally NOT behind get_current_user: the frontend opens this via
    a plain <a href> / new-tab navigation (citation links), which can't
    attach a custom Authorization header. Filenames are sanitized against
    path traversal below; ownership isn't enforced here yet.
    """
    safe_name = _safe_filename(filename)
    file_path = get_source_path(safe_name)

    if not file_path:
        raise HTTPException(status_code=404, detail=f"Source file '{safe_name}' not found.")

    return FileResponse(file_path)
