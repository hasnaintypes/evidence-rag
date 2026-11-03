import base64
import hashlib
import hmac
import time
from typing import Optional

from src.config import settings

# How long a citation link stays valid after being generated in a chat/graph
# response - long enough to open it from that response, short enough to
# limit exposure if a link leaks (e.g. pasted somewhere public).
SOURCE_LINK_TTL_SECONDS = 600


def _secret() -> bytes:
    return (settings.source_link_secret or settings.gemini_api_key).encode()


def generate_source_token(filename: str, user_id: str, ttl_seconds: int = SOURCE_LINK_TTL_SECONDS) -> str:
    """
    Issues a short-lived token scoping a /source/{filename} link to the
    user it was generated for. GET /source/{filename} can't require a
    bearer token (see src/config.py's source_link_secret comment), so this
    is the substitute: the signature ties the token to one exact filename
    and user, and the embedded expiry makes a leaked link self-expiring.
    """
    expiry = int(time.time()) + ttl_seconds
    payload = f"{filename}:{user_id}:{expiry}"
    signature = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    raw = f"{user_id}:{expiry}:{signature}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def verify_source_token(filename: str, token: str) -> Optional[str]:
    """
    Returns the user_id a token was issued to, or None if it's missing,
    doesn't match this exact filename, has been tampered with, or expired.
    Callers must still separately check that user_id can actually access
    `filename` (see storage.database.document_filename_accessible) -
    verifying the token only proves it was issued to this user, not that
    the document the link points at belongs to them.
    """
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        user_id, expiry_str, signature = raw.split(":", 2)
        expiry = int(expiry_str)
    except Exception:
        return None

    payload = f"{filename}:{user_id}:{expiry}"
    expected_signature = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return None
    if time.time() > expiry:
        return None
    return user_id
