import os
import sys

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

# server/src and server/scripts are siblings, not packages under each
# other - add server/ itself so "from src...."/"from scripts...." resolve
# regardless of the process's working directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.query_pipeline import process_chat_query
from src.storage.database import init_db, list_documents, get_graph_data
from src.ingestion.pipeline import ingest_file, SUPPORTED_EXTENSIONS
from src.storage.files import save_upload, get_source_path
import uvicorn

from src.telemetry import init_telemetry_table
from src.config import settings

app = FastAPI(title=settings.app_name)

@app.get("/graph")
async def graph_endpoint(doc_id: str = None):
    """Returns entity co-occurrence graph data for visualization.
    Pass ?doc_id=... to scope to one document, omit for the full graph."""
    return get_graph_data(doc_id)

@app.on_event("startup")
async def startup_event():
    """Ensures the schema exists before the first request, mirroring
    scripts/ingest.py's init_db() call so /upload never hits a missing table."""
    init_db()
    init_telemetry_table()  # creates query_log table if it doesn't exist


class ChatRequest(BaseModel):
    message: str
    advanced_mode: bool = True  # was silently ignored before - UI already sends this field


@app.get("/health")
async def health_check():
    """Checks system availability and active pipeline models."""
    return {
        "status": "ok",
        "storage_mode": settings.storage_mode,
        "chat_model": settings.gemini_chat_model,
    }


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Main RAG pipeline entrypoint for answering technical user queries."""
    try:
        result = process_chat_query(request.message, advanced_mode=request.advanced_mode)
        return result
    except Exception as e:
        return {
            "reply": f"An error occurred: {str(e)}",
            "thinking": "Pipeline failure.",
            "telemetry": {},
            "chunks_matrix": [],
            "sources": [],
            "faithfulness": {"score": None, "unsupported_claims": []},
        }


@app.get("/documents")
async def documents_endpoint():
    """Returns the ingestion registry, used by the UI sidebar to show
    what's actually indexed instead of a hardcoded example list."""
    return {"documents": list_documents()}


# --- DYNAMIC DOCUMENT INGESTION (UPLOAD ENDPOINT) ---
@app.post("/upload")
async def upload_file_endpoint(file: UploadFile = File(...)):
    """
    Saves, parses, chunks, embeds, and indexes an uploaded document.

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

    try:
        with save_upload(filename, file.file) as file_path:
            result = ingest_file(file_path, filename)

        if result["status"] == "unchanged":
            return {
                "status": "unchanged",
                "message": f"'{filename}' is identical to the already-indexed version - skipped.",
                "analytics": {"chunk_count": 0},
            }

        if result["status"] == "empty":
            raise HTTPException(status_code=400, detail="The file content is empty or could not be chunked properly.")

        return {
            "status": "success",
            "message": f"'{filename}' successfully indexed into {result['chunk_count']} chunks.",
            "analytics": {"chunk_count": result["chunk_count"]},
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


@app.get("/source/{filename}")
async def serve_source_document(filename: str):
    """
    Serves an ingested source file for the citation viewer. The UI links
    to this with a #page=N fragment, which browser-native PDF viewers
    (Chrome, Firefox, Edge) honor to jump straight to that page - no
    PDF.js integration needed for this simple version.
    """
    safe_name = _safe_filename(filename)
    file_path = get_source_path(safe_name)

    if not file_path:
        raise HTTPException(status_code=404, detail=f"Source file '{safe_name}' not found.")

    return FileResponse(file_path)

if __name__ == "__main__":
    uvicorn.run("api.app:app", host="127.0.0.1", port=8000, reload=True)
