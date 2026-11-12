import os
import sys

# server/ itself (not server/tests/) needs to be on sys.path for "from
# src...."/"from api...." imports to resolve, same requirement as api/app.py.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# src/core/config.py's Settings() requires GEMINI_API_KEY and VOYAGE_API_KEY
# with no default, and is instantiated at import time - CI has no
# server/.env file, so these have to be set before any test file imports
# anything under src/. Placeholders are fine: every test here mocks the
# Gemini/Voyage call sites directly rather than hitting the real APIs.
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-a-real-credential")
os.environ.setdefault("VOYAGE_API_KEY", "test-key-not-a-real-credential")

import pytest  # noqa: E402

from src.core.config import settings  # noqa: E402
import src.storage.database as db  # noqa: E402
import src.core.response_cache as response_cache  # noqa: E402
import src.core.rate_limiter as rate_limiter  # noqa: E402
import src.core.telemetry as telemetry  # noqa: E402
import src.retrieval.hybrid as hybrid  # noqa: E402


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


@pytest.fixture(autouse=True)
def isolated_rate_limiter():
    """
    rate_limiter.py's request-timestamp map is module-level/process-wide
    by the same design as response_cache.py's cache - cleared before and
    after every test so one test's simulated requests don't push a later,
    unrelated test over the limit.
    """
    rate_limiter.clear_rate_limits()
    yield
    rate_limiter.clear_rate_limits()


@pytest.fixture(autouse=True)
def isolated_retention_sweep():
    """
    telemetry.py's query_log retention sweep gate (#29) is module-level/
    process-wide by the same design as the fixtures above - reset before
    and after every test so one test's logged queries don't suppress (or
    force) another, unrelated test's sweep attempt.
    """
    telemetry.reset_retention_sweep_state()
    yield
    telemetry.reset_retention_sweep_state()


@pytest.fixture(autouse=True)
def isolated_retrieval_index_cache():
    """
    retrieval/hybrid.py's global full-corpus cache and per-scope cache
    (#27) are both module-level/process-wide by the same design as the
    fixtures above. Each test gets a fresh temp SQLite DB
    (isolated_sqlite_db), but the caches themselves aren't reset between
    tests - without this, a later test's doc_ids scope (e.g. "doc-1")
    could reuse an earlier, unrelated test's cached chunks/bm25/matrix
    for that same scope key if the two happen to have the same chunk
    count, silently serving stale/wrong results.
    """
    hybrid.invalidate_index_cache()
    yield
    hybrid.invalidate_index_cache()


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
