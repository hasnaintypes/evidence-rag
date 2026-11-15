from fastapi import APIRouter, Response

from src.core.config import settings
from src.storage.database import get_db_connection

router = APIRouter()


@router.get("/health")
def health_check(response: Response):
    """Checks system availability, active pipeline models, and storage
    connectivity. Sync `def` (not `async def`) so FastAPI runs the blocking
    DB call below in its threadpool instead of on the event loop, matching
    how every other storage call in this codebase (hybrid.py, telemetry.py,
    etc.) is plain sync."""
    storage_ok = True
    storage_error: str | None = None
    try:
        conn = get_db_connection()
        try:
            conn.cursor().execute("SELECT 1")
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover - exercised via integration/ops testing
        storage_ok = False
        storage_error = str(exc)

    response.status_code = 200 if storage_ok else 503
    return {
        "status": "ok" if storage_ok else "degraded",
        "storage_mode": settings.storage_mode,
        "chat_model": settings.gemini_chat_model,
        "storage": {"ok": storage_ok, **({"error": storage_error} if storage_error else {})},
    }
