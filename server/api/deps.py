import jwt
from fastapi import Header, HTTPException

from src.config import settings

# Cached JWKS client - fetches and caches Supabase's public signing keys
# from its well-known endpoint, so verification never needs a shared
# secret stored on this server (keys rotate on Supabase's side automatically).
_jwks_client: "jwt.PyJWKClient | None" = None


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        if not settings.supabase_url:
            raise HTTPException(status_code=500, detail="SUPABASE_URL is not configured on the server.")
        _jwks_client = jwt.PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json")
    return _jwks_client


class CurrentUser:
    def __init__(self, id: str, email: str | None):
        self.id = id
        self.email = email


def get_current_user(authorization: str = Header(...)) -> CurrentUser:
    """
    Verifies the JWT Supabase Auth issues to a signed-in user and returns
    their id/email, using Supabase's public JWKS endpoint (asymmetric
    signing keys) rather than a shared secret - nothing sensitive is
    stored server-side for this, and Supabase can rotate keys without any
    config change here.

    Auth is required on every route that uses this dependency; there's no
    STORAGE_MODE=local bypass, since Auth is a separate Supabase product
    from Postgres/Storage.
    """
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")

    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired - please sign in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token.")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token is missing a subject claim.")

    return CurrentUser(id=user_id, email=payload.get("email"))
