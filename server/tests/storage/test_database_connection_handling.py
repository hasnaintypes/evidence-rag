"""
Regression coverage for #55: every function in src/storage/database.py
used to acquire a connection and close it with a bare
`conn = get_db_connection(); ...; conn.close()` sequence, with no
try/finally. Any exception raised between acquire and that final line
(a constraint violation, a malformed query, anything) skipped conn.close()
entirely - which, in storage_mode="supabase", means the connection never
goes back to the pool (ThreadedConnectionPool.putconn() is never called).
With maxconn=10, as few as 10 such exceptions across the process's
lifetime fully exhausts the pool - the suspected cause of #55's "pool
exhausted" during an eval run that hits far fewer than 10 concurrent
requests.

Every function now wraps its body in try/finally with conn.close() in
the finally - these tests prove that holds by making a representative
sample of functions raise mid-body and asserting close() still ran.
"""

import time
from unittest.mock import MagicMock, patch

import psycopg2
import pytest

import src.storage.database as db
from src.core.config import settings


@pytest.fixture(autouse=True)
def supabase_mode(monkeypatch):
    # The connection-acquire/release pattern is identical in local mode
    # (plain sqlite3.Connection.close()) - this fixture isn't required
    # for the fix to apply, but it keeps these tests pointed at the mode
    # #55 actually symptomed in (a real ThreadedConnectionPool).
    monkeypatch.setattr(settings, "storage_mode", "supabase")


def _fake_conn_that_raises_on_execute():
    fake_cursor = MagicMock()
    fake_cursor.execute.side_effect = RuntimeError("simulated query failure")
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    return fake_conn


@pytest.mark.parametrize(
    "call",
    [
        lambda: db.get_document_hash("doc-1"),
        lambda: db.get_document_record("doc-1"),
        lambda: db.list_documents(),
        lambda: db.delete_document_data("doc-1"),
        lambda: db.get_conversation("conv-1"),
        lambda: db.mark_document_failed("doc-1"),
    ],
)
def test_connection_is_closed_even_when_the_query_raises(call):
    fake_conn = _fake_conn_that_raises_on_execute()
    with patch("src.storage.database.get_db_connection", return_value=fake_conn):
        with pytest.raises(RuntimeError):
            call()

    fake_conn.close.assert_called_once()


def _fake_connection(alive: bool):
    """A fake psycopg2 connection whose SELECT 1 liveness ping
    (_is_alive()) succeeds or fails depending on `alive`."""
    fake_cursor = MagicMock()
    fake_cursor.__enter__ = MagicMock(return_value=fake_cursor)
    fake_cursor.__exit__ = MagicMock(return_value=False)
    if not alive:
        fake_cursor.execute.side_effect = psycopg2.OperationalError("SSL connection has been closed unexpectedly")
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    # Real _TrackedConnection instances default this to 0.0 (never
    # verified) - MagicMock has no such default, so set it explicitly or
    # _is_alive()'s "checked recently enough, skip the round trip"
    # fast-path would compare against another MagicMock instead of 0.0.
    fake_conn.last_verified_at = 0.0
    return fake_conn


def test_get_db_connection_discards_a_dead_pooled_connection_and_retries():
    """Regression for #57: a connection the server dropped while idle
    (Supabase pooler recycling it mid-eval-run) doesn't set conn.closed -
    psycopg2 only finds out the socket is dead on the next real query.
    get_db_connection() must ping with SELECT 1 on checkout, discard a
    dead connection (close=True back to the pool), and retry with a
    fresh one - rather than handing the dead one to the caller, whose
    first real query would then fail with
    `OperationalError: SSL connection has been closed unexpectedly`."""
    dead_conn = _fake_connection(alive=False)
    live_conn = _fake_connection(alive=True)
    fake_pool = MagicMock()
    fake_pool.getconn.side_effect = [dead_conn, live_conn]

    with patch("src.storage.database._get_supabase_pool", return_value=fake_pool):
        result = db.get_db_connection()

    assert fake_pool.getconn.call_count == 2
    fake_pool.putconn.assert_called_once_with(dead_conn, close=True)
    assert result._conn is live_conn


def test_get_db_connection_bounds_the_retry_when_multiple_stale_connections_are_pooled():
    """Regression for a gap caught in code review: ThreadedConnectionPool
    .getconn() pops from its own idle-connection list, so a second
    getconn() after discarding one dead connection can just as easily
    hand back ANOTHER already-stale one, not necessarily a fresh
    connection. The retry must be bounded
    (_MAX_LIVENESS_CHECKOUT_ATTEMPTS), not a single fixed attempt - this
    drains up to that many stale connections before giving up and
    returning whatever it has (a real "the whole pool is bad" outage is
    then the caller's own query's problem to surface, not an infinite
    retry loop here)."""
    dead_conn_1 = _fake_connection(alive=False)
    dead_conn_2 = _fake_connection(alive=False)
    live_conn = _fake_connection(alive=True)
    fake_pool = MagicMock()
    fake_pool.getconn.side_effect = [dead_conn_1, dead_conn_2, live_conn]

    with patch("src.storage.database._get_supabase_pool", return_value=fake_pool):
        result = db.get_db_connection()

    assert fake_pool.getconn.call_count == 3
    assert fake_pool.putconn.call_count == 2
    assert result._conn is live_conn


def test_get_db_connection_gives_up_after_the_bounded_number_of_stale_attempts():
    all_dead = [_fake_connection(alive=False) for _ in range(db._MAX_LIVENESS_CHECKOUT_ATTEMPTS)]
    fake_pool = MagicMock()
    fake_pool.getconn.side_effect = all_dead

    with patch("src.storage.database._get_supabase_pool", return_value=fake_pool):
        result = db.get_db_connection()

    assert fake_pool.getconn.call_count == db._MAX_LIVENESS_CHECKOUT_ATTEMPTS
    # The last attempt is returned as-is rather than retried indefinitely -
    # still dead, but that's the caller's real query's problem now, not an
    # infinite loop here.
    assert result._conn is all_dead[-1]


def test_get_db_connection_skips_the_retry_when_the_first_connection_is_alive():
    live_conn = _fake_connection(alive=True)
    fake_pool = MagicMock()
    fake_pool.getconn.side_effect = [live_conn]

    with patch("src.storage.database._get_supabase_pool", return_value=fake_pool):
        result = db.get_db_connection()

    assert fake_pool.getconn.call_count == 1
    fake_pool.putconn.assert_not_called()
    assert result._conn is live_conn


def test_is_alive_skips_the_round_trip_for_a_recently_verified_connection():
    """Regression for a performance concern caught in code review:
    get_db_connection() is called dozens of times per request across
    database.py/telemetry.py/hybrid.py - pinging every single checkout
    unconditionally would re-add the per-call round-trip cost pooling
    was introduced to avoid. A connection verified within
    _LIVENESS_CHECK_INTERVAL_SECONDS must skip the SELECT 1 entirely."""
    conn = _fake_connection(alive=True)
    conn.last_verified_at = time.monotonic()

    assert db._is_alive(conn) is True
    conn.cursor.assert_not_called()


def test_add_document_to_conversation_closes_on_a_business_rule_raise():
    """add_document_to_conversation() raises ValueError/LookupError as
    part of its normal control flow (duplicate/cap/not-found), not just
    on a genuine query failure - these must close the connection too,
    not only the unexpected-exception path above."""
    fake_cursor = MagicMock()
    fake_cursor.fetchone.return_value = None  # conversation "not found"
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    with patch("src.storage.database.get_db_connection", return_value=fake_conn):
        with pytest.raises(LookupError):
            db.add_document_to_conversation("does-not-exist", doc_id="doc-1")

    fake_conn.close.assert_called_once()
