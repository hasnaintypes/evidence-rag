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

from unittest.mock import MagicMock, patch

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
