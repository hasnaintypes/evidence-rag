"""Tests for the query_log retention sweep added in #29 -
telemetry.py's log_query_event() piggybacks a time-gated call to
purge_query_log() onto real request traffic instead of depending on an
external scheduler. isolated_retention_sweep (tests/conftest.py) resets
the module-level gate before/after every test."""

import logging
from unittest.mock import patch

import src.telemetry as telemetry
from src.telemetry import log_query_event


def _log_once():
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
            log_query_event(query="q", telemetry={})  # must not raise

    assert "retention sweep failed" in caplog.text


def test_no_log_line_when_nothing_was_deleted(caplog):
    with patch("src.telemetry.purge_query_log", return_value=0):
        with caplog.at_level(logging.INFO, logger="evidence_rag.telemetry"):
            _log_once()

    assert "deleted" not in caplog.text
