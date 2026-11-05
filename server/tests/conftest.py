import os
import sys

# server/ itself (not server/tests/) needs to be on sys.path for "from
# src...."/"from api...." imports to resolve, same requirement as api/app.py.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# src/config.py's Settings() requires GEMINI_API_KEY with no default, and is
# instantiated at import time - CI has no server/.env file, so this has to
# be set before any test file imports anything under src/. A placeholder is
# fine: every test here mocks the Gemini call sites directly rather than
# hitting the real API.
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-a-real-credential")

import pytest  # noqa: E402

from src.config import settings  # noqa: E402
import src.storage.database as db  # noqa: E402
import src.response_cache as response_cache  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_sqlite_db(tmp_path, monkeypatch):
    """
    Forces storage_mode="local" and points DB_PATH at a fresh temp SQLite
    file for every test, regardless of what STORAGE_MODE/SUPABASE_DB_URL
    are set to in the developer's own server/.env - tests must never touch
    a real (local dev or Supabase) database, and must not leak state
    between tests.
    """
    monkeypatch.setattr(settings, "storage_mode", "local")
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    yield db


@pytest.fixture(autouse=True)
def isolated_response_cache():
    """
    response_cache.py's cache is a module-level dict, shared process-wide
    by design (same pattern as hybrid.py's in-memory index) - but that
    means it would otherwise leak between tests, letting an earlier
    test's cached pipeline result silently answer a later, unrelated
    test's query. Cleared before and after every test.
    """
    response_cache.clear_cache()
    yield
    response_cache.clear_cache()


@pytest.fixture
def app():
    from api.app import app as fastapi_app

    return fastapi_app


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def override_current_user(app, user_id: str, email: str = "test@example.com"):
    """Replaces get_current_user's real JWT/JWKS verification with a fixed
    identity for a test - auth verification itself is covered separately
    in test_auth_deps.py; route-level tests only need a *known* identity to
    then assert ownership behavior against."""
    from api.deps import get_current_user, CurrentUser

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=user_id, email=email)
