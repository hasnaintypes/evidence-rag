"""Tests for the query_log retention sweep added in #29 -
telemetry.py's log_query_event() piggybacks a time-gated call to
purge_query_log() onto real request traffic instead of depending on an
external scheduler. isolated_retention_sweep (tests/conftest.py) resets
the module-level gate before/after every test.

The actual purge runs on a background thread (see
_maybe_run_retention_sweep()'s docstring - deliberately off the request
thread), so every test here patches threading.Thread with a stand-in
that runs its target immediately/synchronously instead of on a real
thread, keeping assertions deterministic without a real race."""

import logging
from unittest.mock import patch

import src.telemetry as telemetry
from src.telemetry import log_query_event


class _ImmediateThread:
    """threading.Thread stand-in that runs its target synchronously on
    .start() instead of spawning a real thread."""

    def __init__(self, target, daemon=None):
        self._target = target

    def start(self):
        self._target()


def _log_once():
    with patch("src.telemetry.threading.Thread", _ImmediateThread):
        log_query_event(query="q", telemetry={})


def test_sweep_runs_on_the_first_logged_query(caplog):
    with patch("src.telemetry.purge_query_log", return_value=3) as mock_purge:
        with caplog.at_level(logging.INFO, logger="evidence_rag.telemetry"):
            _log_once()

    mock_purge.assert_called_once()
    assert "deleted 3" in caplog.text


def test_sweep_does_not_run_again_within_the_interval():
    with patch("src.telemetry.purge_query_log", return_value=0) as mock_purge:
        _log_once()
        _log_once()
        _log_once()

    mock_purge.assert_called_once()


def test_sweep_runs_again_once_the_interval_has_elapsed():
    with patch("src.telemetry.purge_query_log", return_value=0) as mock_purge:
        _log_once()
        telemetry._last_purge_attempt -= telemetry.PURGE_CHECK_INTERVAL_SECONDS + 1
        _log_once()

    assert mock_purge.call_count == 2


def test_a_purge_failure_is_logged_not_raised(caplog):
    with patch("src.telemetry.purge_query_log", side_effect=RuntimeError("db unavailable")):
        with caplog.at_level(logging.ERROR, logger="evidence_rag.telemetry"):
            _log_once()  # must not raise

    assert "retention sweep failed" in caplog.text


def test_no_log_line_when_nothing_was_deleted(caplog):
    with patch("src.telemetry.purge_query_log", return_value=0):
        with caplog.at_level(logging.INFO, logger="evidence_rag.telemetry"):
            _log_once()

    assert "deleted" not in caplog.text


def test_the_sweep_does_not_run_on_the_calling_thread():
    """A real production call must dispatch the purge onto a background
    thread, not run it inline - a slow purge (batched deletes, see
    purge_query_log()'s own docstring) must never add to a real chat
    request's response time. Uses the real threading.Thread (no
    _ImmediateThread stand-in); the mocked purge blocks until released
    so the spawned thread is still alive when we inspect it, instead of
    racing a near-instant mock to completion."""
    import threading

    release = threading.Event()
    calling_thread_id = threading.get_ident()
    purge_thread_id = None

    def _slow_purge(*args, **kwargs):
        nonlocal purge_thread_id
        purge_thread_id = threading.get_ident()
        release.wait(timeout=2)
        return 0

    with patch("src.telemetry.purge_query_log", side_effect=_slow_purge):
        log_query_event(query="q", telemetry={})
        # The call above only dispatches the thread; give it a moment to
        # actually start running _slow_purge before asserting.
        for _ in range(100):
            if purge_thread_id is not None:
                break
            threading.Event().wait(0.01)
        release.set()

    assert purge_thread_id is not None
    assert purge_thread_id != calling_thread_id
