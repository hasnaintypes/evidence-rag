"""
Regression coverage for a connection-pool leak found in telemetry.py
while re-running the #57 eval harness after #55's fix - that fix only
covered get_db_connection() call sites inside src/storage/database.py.
telemetry.py calls get_db_connection() directly too (log_query_event(),
get_recent_queries()), and log_query_event()'s own broad
`try: ... except Exception: pass` (by design - telemetry must never
break a chat response) meant a mid-query exception there skipped
conn.close() AND was silently swallowed, with no trace that a
connection had just leaked from the supabase pool.
"""

from unittest.mock import MagicMock, patch

import pytest

import src.core.telemetry as telemetry


def _fake_conn_that_raises_on_execute():
    fake_cursor = MagicMock()
    fake_cursor.execute.side_effect = RuntimeError("simulated query failure")
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    return fake_conn


def test_log_query_event_closes_the_connection_even_when_the_insert_raises():
    fake_conn = _fake_conn_that_raises_on_execute()

    with (
        patch("src.core.telemetry.get_db_connection", return_value=fake_conn),
        # Isolates this assertion to log_query_event()'s own connection -
        # the retention sweep it also piggybacks (#29) would otherwise
        # make its own get_db_connection()/close() call against this same
        # patch, double-counting close() for an unrelated reason.
        patch("src.core.telemetry._maybe_run_retention_sweep"),
    ):
        # log_query_event() never raises by design (telemetry must never
        # break the chat response) - the regression under test is purely
        # whether conn.close() still ran despite the swallowed exception.
        telemetry.log_query_event(query="q", telemetry={})

    fake_conn.close.assert_called_once()


def test_get_recent_queries_closes_the_connection_even_when_the_query_raises():
    fake_conn = _fake_conn_that_raises_on_execute()

    with patch("src.core.telemetry.get_db_connection", return_value=fake_conn):
        with pytest.raises(RuntimeError):
            telemetry.get_recent_queries()

    fake_conn.close.assert_called_once()
