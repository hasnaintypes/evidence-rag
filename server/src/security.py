import secrets
import time
from typing import Optional

import jwt

from src.config import settings

# How long a citation link stays valid after being generated in a chat/graph
# response - long enough to open it from that response, short enough to
# limit exposure if a link leaks (e.g. pasted somewhere public).
SOURCE_LINK_TTL_SECONDS = 600

# Falls back to a random secret generated once per process start, rather
# than reusing settings.gemini_api_key, so this internal auth boundary
# isn't coupled to an unrelated external API credential (leaking one
# shouldn't let someone forge the other, and rotating the Gemini key
# shouldn't silently invalidate every outstanding citation link). The
# tradeoff: a restart invalidates in-flight tokens, which is fine given
# the short TTL - set SOURCE_LINK_SECRET explicitly in any multi-process
# or multi-worker deployment, where each worker would otherwise mint
# tokens the others can't verify.
_fallback_secret = secrets.token_hex(32)


def _secret() -> str:
    return settings.source_link_secret or _fallback_secret


def generate_source_token(filename: str, user_id: str, ttl_seconds: int = SOURCE_LINK_TTL_SECONDS) -> str:
    """
    Issues a short-lived JWT scoping a /source/{filename} link to the user
    it was generated for. GET /source/{filename} can't require a bearer
    token (see src/config.py's source_link_secret comment), so this is the
    substitute: the signature ties the token to one exact filename and
    user, and the expiry claim makes a leaked link self-expiring.
    """
    payload = {"filename": filename, "sub": user_id, "exp": int(time.time()) + ttl_seconds}
    return jwt.encode(payload, _secret(), algorithm="HS256")


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
        payload = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None

    if payload.get("filename") != filename:
        return None
    return payload.get("sub")
