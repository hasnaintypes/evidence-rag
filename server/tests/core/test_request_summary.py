"""Unit tests for src/core/request_summary.py's end-of-request summary."""

import logging

import pytest

from src.core.config import settings
from src.core.logging_config import configure_logging, reset_logging_config_for_tests
from src.core.request_summary import build_request_summary, log_request_summary


@pytest.fixture
def _stdlib_routed_structlog(monkeypatch):
    """See test_ai_tracker.py's fixture of the same name - request_summary.py
    also logs through structlog.get_logger(), which needs configure_logging()
    to have run at least once in this process before caplog (a stdlib
    logging.Handler) can observe anything it logs."""
    monkeypatch.setattr(settings, "log_to_console", False)
    monkeypatch.setattr(settings, "log_to_file", False)
    reset_logging_config_for_tests()
    configure_logging()
    yield
    reset_logging_config_for_tests()


def test_build_request_summary_sums_stage_breakdown_into_total_duration():
    telemetry = {"embedding_time_ms": 10.0, "retrieval_time_ms": 5.0, "generation_time_ms": 100.0}
    summary = build_request_summary("req-1", telemetry, outcome="success")
    assert summary["total_duration_ms"] == 115.0
    assert summary["stage_breakdown_ms"] == telemetry


def test_build_request_summary_aggregates_ai_calls_by_provider_and_operation():
    telemetry = {
        "ai_calls": [
            {
                "invocation_id": "a",
                "provider": "cloudflare",
                "model": "m",
                "operation": "answer_generation",
                "parent_stage": None,
                "duration_ms": 10.0,
                "attempts": 1,
                "is_fallback": False,
                "outcome": "success",
                "input_tokens": 100,
                "output_tokens": 20,
            },
            {
                "invocation_id": "b",
                "provider": "cloudflare",
                "model": "m",
                "operation": "answer_generation",
                "parent_stage": None,
                "duration_ms": 10.0,
                "attempts": 3,
                "is_fallback": False,
                "outcome": "error",
                "input_tokens": None,
                "output_tokens": None,
            },
            {
                "invocation_id": "c",
                "provider": "voyage",
                "model": "m2",
                "operation": "embedding",
                "parent_stage": None,
                "duration_ms": 5.0,
                "attempts": 1,
                "is_fallback": True,
                "outcome": "success",
                "input_tokens": 50,
                "output_tokens": None,
            },
        ]
    }
    summary = build_request_summary("req-1", telemetry, outcome="success")

    assert summary["ai_invocations"] == 3
    assert summary["ai_http_attempts"] == 1 + 3 + 1
    assert summary["ai_retries"] == 2  # only the 3-attempt call contributes retries (3 - 1)
    assert summary["ai_fallbacks"] == 1
    assert summary["ai_errors"] == 1
    assert summary["input_tokens"] == 150
    assert summary["output_tokens"] == 20

    by_key = summary["ai_calls_by_provider_operation"]
    assert by_key["cloudflare:answer_generation"]["count"] == 2
    assert by_key["cloudflare:answer_generation"]["errors"] == 1
    assert by_key["voyage:embedding"]["count"] == 1


def test_no_ai_calls_means_zero_everywhere_not_missing_fields():
    summary = build_request_summary("req-1", {}, outcome="cache_hit")
    assert summary["ai_invocations"] == 0
    assert summary["ai_retries"] == 0
    assert summary["ai_fallbacks"] == 0
    assert summary["input_tokens"] is None
    assert summary["output_tokens"] is None


def test_log_request_summary_emits_failed_event_for_a_failed_outcome(caplog, _stdlib_routed_structlog):
    summary = build_request_summary("req-1", {}, outcome="failed")
    with caplog.at_level(logging.INFO, logger="evidence_rag.chat"):
        log_request_summary(summary)
    messages = [r.getMessage() for r in caplog.records]
    assert any("chat.request.failed" in m for m in messages)


def test_log_request_summary_emits_completed_event_for_a_success_outcome(caplog, _stdlib_routed_structlog):
    summary = build_request_summary("req-1", {}, outcome="success")
    with caplog.at_level(logging.INFO, logger="evidence_rag.chat"):
        log_request_summary(summary)
    messages = [r.getMessage() for r in caplog.records]
    assert any("chat.request.completed" in m for m in messages)


def test_log_request_summary_respects_the_log_chat_summaries_setting(caplog, monkeypatch, _stdlib_routed_structlog):
    from src.core.config import settings

    monkeypatch.setattr(settings, "log_chat_summaries", False)
    summary = build_request_summary("req-1", {}, outcome="success")
    with caplog.at_level(logging.INFO, logger="evidence_rag.chat"):
        log_request_summary(summary)
    assert caplog.records == []
