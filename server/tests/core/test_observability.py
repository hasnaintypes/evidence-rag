"""Unit tests for src/core/observability.py's stage tracing."""

import logging

import pytest

from src.core.observability import new_request_id, traced_stage


def test_request_ids_are_short_and_unique():
    a, b = new_request_id(), new_request_id()
    assert a != b
    assert len(a) == 12


def test_a_successful_stage_records_its_elapsed_time_in_telemetry():
    telemetry = {}
    with traced_stage("req-1", "embedding", telemetry):
        pass
    assert "embedding_time_ms" in telemetry
    assert telemetry["embedding_time_ms"] >= 0.0


def test_a_failed_stage_re_raises_without_recording_a_timing():
    telemetry = {}
    with pytest.raises(ValueError):
        with traced_stage("req-1", "generation", telemetry):
            raise ValueError("boom")
    assert "generation_time_ms" not in telemetry


def test_stage_start_and_complete_are_logged_with_the_request_id(caplog):
    with caplog.at_level(logging.INFO, logger="evidence_rag.pipeline"):
        with traced_stage("req-42", "retrieval", {}):
            pass
    messages = [r.getMessage() for r in caplog.records]
    assert any("stage_start" in m and "req-42" in m and "retrieval" in m for m in messages)
    assert any("stage_complete" in m and "req-42" in m for m in messages)


def test_a_stage_failure_is_logged_as_an_error_with_the_exception(caplog):
    with caplog.at_level(logging.INFO, logger="evidence_rag.pipeline"):
        with pytest.raises(RuntimeError):
            with traced_stage("req-99", "generation", {}):
                raise RuntimeError("gemini is down")

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_records
    assert "req-99" in error_records[0].getMessage()
    assert error_records[0].exc_info is not None


def test_telemetry_is_optional():
    with traced_stage("req-1", "embedding", telemetry=None):
        pass  # must not raise just because telemetry wasn't passed
