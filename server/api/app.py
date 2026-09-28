import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# server/src and server/scripts are siblings, not packages under each
# other - add server/ itself so "from src...."/"from scripts...." resolve
# regardless of the process's working directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings
from src.storage.database import init_db
from src.telemetry import init_telemetry_table
from api.routers import health, documents, conversations, graph

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(conversations.router)
app.include_router(graph.router)


@app.on_event("startup")
async def startup_event():
    """Ensures the schema exists before the first request, mirroring
    scripts/ingest.py's init_db() call so /upload never hits a missing table."""
    init_db()
    init_telemetry_table()  # creates query_log table if it doesn't exist


if __name__ == "__main__":
    uvicorn.run("api.app:app", host="127.0.0.1", port=8000, reload=True)
