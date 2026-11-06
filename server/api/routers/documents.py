from fastapi import APIRouter, BackgroundTasks, Depends, Response, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse

from api.deps import get_current_user, get_rate_limited_upload_user, CurrentUser
from api.schemas import DocumentRename
from api.services.document_service import DocumentService

router = APIRouter()


@router.get("/documents")
def documents_endpoint(user: CurrentUser = Depends(get_current_user)):
    return DocumentService.list_for_user(user)


@router.post("/upload")
def upload_file_endpoint(
    response: Response,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_rate_limited_upload_user),
):
    result = DocumentService.upload(file, user, background_tasks)
    # Only the "processing" case actually schedules a background task -
    # "unchanged" (hash-based dedup short-circuit) did no work, so it
    # keeps the default 200 rather than always claiming 202 (#56).
    if result["status"] == "processing":
        response.status_code = 202
    return result


@router.patch("/documents/{doc_id}")
def rename_document_endpoint(doc_id: str, body: DocumentRename, user: CurrentUser = Depends(get_current_user)):
    return DocumentService.rename(doc_id, body.filename, user)


@router.delete("/documents/{doc_id}")
def delete_document_endpoint(doc_id: str, user: CurrentUser = Depends(get_current_user)):
    return DocumentService.delete(doc_id, user)


@router.post("/documents/{doc_id}/reingest", status_code=202)
def reingest_document_endpoint(
    doc_id: str, background_tasks: BackgroundTasks, user: CurrentUser = Depends(get_rate_limited_upload_user)
):
    return DocumentService.reingest(doc_id, user, background_tasks)


@router.get("/documents/{doc_id}/status")
def document_status_endpoint(doc_id: str, user: CurrentUser = Depends(get_current_user)):
    return DocumentService.get_status(doc_id, user)


@router.get("/documents/{doc_id}/events")
def document_status_events(doc_id: str, user: CurrentUser = Depends(get_current_user)):
    """Server-Sent Events stream of a document's indexing status - see
    DocumentService.status_stream()."""
    return StreamingResponse(
        DocumentService.status_stream(doc_id, user),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/source/{filename}")
def serve_source_document(filename: str, token: str):
    """
    Serves an ingested source file for the citation viewer. The UI links
    to this with a #page=N fragment, which browser-native PDF viewers
    (Chrome, Firefox, Edge) honor to jump straight to that page - no
    PDF.js integration needed for this simple version.

    Intentionally NOT behind get_current_user: the frontend opens this via
    a plain <a href> / new-tab navigation (citation links), which can't
    attach a custom Authorization header. Ownership is instead enforced
    via a short-lived signed `token` (src/core/security.py) inside
    DocumentService.resolve_source_path() - see that method's docstring.
    """
    file_path = DocumentService.resolve_source_path(filename, token)
    return FileResponse(file_path)
