"""Unit tests for src/core/ai_tracker.py's AI invocation tracking."""

import logging

import pytest

from src.core.ai_tracker import log_cache_event, summarize_messages, track_ai_call
from src.core.config import settings
from src.core.logging_config import configure_logging, reset_logging_config_for_tests


@pytest.fixture
def _stdlib_routed_structlog(monkeypatch):
    """ai_tracker.py logs through structlog.get_logger(), which - before
    logging_config.py's configure_logging() has ever run in this process -
    uses structlog's own default PrintLogger and never touches stdlib
    `logging` at all, so pytest's caplog (a stdlib logging handler) can't
    see it. Only the one test below that asserts on caplog needs this."""
    monkeypatch.setattr(settings, "log_to_console", False)
    monkeypatch.setattr(settings, "log_to_file", False)
    reset_logging_config_for_tests()
    configure_logging()
    yield
    reset_logging_config_for_tests()


def test_a_successful_call_is_recorded_in_telemetry():
    telemetry = {}
    with track_ai_call("cloudflare", "model-x", "answer_generation", telemetry=telemetry) as span:
        span.log_attempt(1, "success")
    calls = telemetry["ai_calls"]
    assert len(calls) == 1
    assert calls[0]["provider"] == "cloudflare"
    assert calls[0]["operation"] == "answer_generation"
    assert calls[0]["outcome"] == "success"
    assert calls[0]["attempts"] == 1
    assert calls[0]["is_fallback"] is False


def test_a_failed_call_re_raises_and_is_still_recorded():
    telemetry = {}
    with pytest.raises(RuntimeError):
        with track_ai_call("cloudflare", "model-x", "reranking", telemetry=telemetry) as span:
            span.log_attempt(1, "error", error_category="RuntimeError")
            raise RuntimeError("boom")
    calls = telemetry["ai_calls"]
    assert len(calls) == 1
    assert calls[0]["outcome"] == "error"


def test_multiple_attempts_are_tracked_on_one_invocation():
    telemetry = {}
    with track_ai_call("cloudflare", "model-x", "answer_generation", telemetry=telemetry) as span:
        span.log_attempt(1, "transient_failure", error_category="APIConnectionError")
        span.log_attempt(2, "success")
    calls = telemetry["ai_calls"]
    assert calls[0]["attempts"] == 2


def test_a_fallback_model_is_flagged():
    telemetry = {}
    with track_ai_call("gemini", "primary-model", "chat_generation", telemetry=telemetry) as span:
        span.model = "fallback-model"
        span.is_fallback = True
        span.log_attempt(1, "success")
    assert telemetry["ai_calls"][0]["is_fallback"] is True


def test_token_usage_is_never_fabricated_when_absent():
    telemetry = {}
    with track_ai_call("voyage", "voyage-3.5", "embedding", telemetry=telemetry) as span:
        span.log_attempt(1, "success")
    call = telemetry["ai_calls"][0]
    assert call["input_tokens"] is None
    assert call["output_tokens"] is None


def test_token_usage_is_recorded_when_the_provider_returns_it():
    telemetry = {}
    with track_ai_call("cloudflare", "model-x", "answer_generation", telemetry=telemetry) as span:
        span.record_tokens(input_tokens=100, output_tokens=25)
        span.log_attempt(1, "success")
    call = telemetry["ai_calls"][0]
    assert call["input_tokens"] == 100
    assert call["output_tokens"] == 25


def test_telemetry_is_optional_and_never_required():
    with track_ai_call("cloudflare", "model-x", "reranking") as span:
        span.log_attempt(1, "success")  # must not raise just because telemetry wasn't passed


def test_cooldown_skip_is_logged_as_a_distinct_outcome(caplog, _stdlib_routed_structlog):
    telemetry = {}
    with caplog.at_level(logging.INFO, logger="evidence_rag.ai"):
        with track_ai_call("cloudflare", "model-x", "answer_generation", telemetry=telemetry) as span:
            span.log_attempt(1, "cooldown_skipped", error_category="rate_limited")
    messages = [r.getMessage() for r in caplog.records]
    assert any("ai.http_attempt" in m for m in messages)


def test_summarize_messages_never_includes_raw_content():
    messages = [
        {"role": "system", "content": "secret system prompt"},
        {"role": "user", "content": "the user's actual question with sensitive detail"},
    ]
    summary = summarize_messages(messages)
    assert summary["message_count"] == 2
    assert summary["roles"] == ["system", "user"]
    assert summary["has_system_prompt"] is True
    assert isinstance(summary["approx_input_chars"], int)
    # The raw text must never leak into the summary dict's values.
    assert "secret system prompt" not in str(summary)
    assert "sensitive detail" not in str(summary)


def test_log_cache_event_does_not_raise_for_hit_or_miss():
    log_cache_event(hit=True, request_id="req-1")
    log_cache_event(hit=False, request_id="req-1")
