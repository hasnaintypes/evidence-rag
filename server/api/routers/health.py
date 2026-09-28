from fastapi import APIRouter

from src.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """Checks system availability and active pipeline models."""
    return {
        "status": "ok",
        "storage_mode": settings.storage_mode,
        "chat_model": settings.gemini_chat_model,
    }
