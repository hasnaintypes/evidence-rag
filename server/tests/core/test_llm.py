"""Tests for src/llm.py's same-provider model fallback (issue #12) -
a simulated primary-model failure must not crash or silently degrade the
caller; the configured fallback model should be tried instead, and total
failure across both models must still report honestly rather than raise."""

from unittest.mock import MagicMock, patch

import pytest
from google.genai import errors as genai_errors

import src.core.llm as llm
from src.core.config import settings


class _FakeResponse:
    def __init__(self, text):
        self.text = text


def test_generate_chat_response_falls_back_to_the_secondary_model_on_failure():
    calls = []

    def fake_generate_content(model, contents, config):
        calls.append(model)
        if model == settings.gemini_chat_model:
            raise RuntimeError("simulated primary model failure")
        return _FakeResponse("fallback answer")

    with patch.object(llm.client.models, "generate_content", side_effect=fake_generate_content):
        result = llm.generate_chat_response("some prompt")

    assert result == "fallback answer"
    assert calls == [settings.gemini_chat_model, settings.gemini_fallback_chat_model]


def test_generate_chat_response_reports_honest_failure_when_both_models_fail():
    with patch.object(llm.client.models, "generate_content", side_effect=RuntimeError("both down")):
        result = llm.generate_chat_response("some prompt")

    # query_pipeline.py's generation_failed detection depends on this
    # exact substring - changing it without updating that check would
    # silently stop every honest-failure branch from firing.
    assert "error during generation" in result.lower()


def test_generate_chat_response_falls_back_on_an_empty_primary_response():
    """response.text is Optional[str] - None/empty isn't a raised
    exception (e.g. the model stopped on SAFETY/MAX_TOKENS with no text
    parts), so the primary model "succeeding" with nothing useful must
    still trigger the fallback, not be returned as-is."""
    calls = []

    def fake_generate_content(model, contents, config):
        calls.append(model)
        if model == settings.gemini_chat_model:
            return _FakeResponse(None)
        return _FakeResponse("fallback answer")

    with patch.object(llm.client.models, "generate_content", side_effect=fake_generate_content):
        result = llm.generate_chat_response("some prompt")

    assert result == "fallback answer"
    assert calls == [settings.gemini_chat_model, settings.gemini_fallback_chat_model]


def test_generate_chat_response_failure_message_preserves_both_models_errors():
    """Overwriting a single last_error variable across the loop would
    discard the primary model's often-more-diagnosable error (e.g. a
    quota message) once the fallback fails for an unrelated reason."""

    def fake_generate_content(model, contents, config):
        if model == settings.gemini_chat_model:
            raise RuntimeError("quota exceeded for primary")
        raise RuntimeError("fallback misconfigured")

    with patch.object(llm.client.models, "generate_content", side_effect=fake_generate_content):
        result = llm.generate_chat_response("some prompt")

    assert "quota exceeded for primary" in result
    assert "fallback misconfigured" in result


def test_generate_chat_response_does_not_call_the_fallback_when_the_primary_succeeds():
    calls = []

    def fake_generate_content(model, contents, config):
        calls.append(model)
        return _FakeResponse("primary answer")

    with patch.object(llm.client.models, "generate_content", side_effect=fake_generate_content):
        result = llm.generate_chat_response("some prompt")

    assert result == "primary answer"
    assert calls == [settings.gemini_chat_model]


def test_generate_structured_response_falls_back_to_the_secondary_model_on_failure():
    calls = []

    def fake_generate_content(model, contents, config):
        calls.append(model)
        if model == settings.gemini_chat_model:
            raise RuntimeError("simulated primary model failure")
        return _FakeResponse('{"score": 1.0, "unsupported_claims": []}')

    with patch.object(llm.client.models, "generate_content", side_effect=fake_generate_content):
        result = llm.generate_structured_response("judge prompt", response_schema={})

    assert result == {"score": 1.0, "unsupported_claims": []}
    assert calls == [settings.gemini_chat_model, settings.gemini_fallback_chat_model]


def test_generate_structured_response_returns_none_when_both_models_fail():
    with patch.object(llm.client.models, "generate_content", side_effect=RuntimeError("both down")):
        result = llm.generate_structured_response("judge prompt", response_schema={})

    assert result is None


def test_generate_structured_response_tries_the_fallback_on_an_empty_primary_response():
    calls = []

    def fake_generate_content(model, contents, config):
        calls.append(model)
        if model == settings.gemini_chat_model:
            return _FakeResponse("")
        return _FakeResponse('{"score": 0.5, "unsupported_claims": ["x"]}')

    with patch.object(llm.client.models, "generate_content", side_effect=fake_generate_content):
        result = llm.generate_structured_response("judge prompt", response_schema={})

    assert result == {"score": 0.5, "unsupported_claims": ["x"]}
    assert calls == [settings.gemini_chat_model, settings.gemini_fallback_chat_model]


def test_get_embedding_retries_once_on_the_same_model_before_raising():
    call_count = {"n": 0}

    def fake_embed_content(model, contents):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("transient failure")
        embedding = MagicMock()
        embedding.values = [0.1, 0.2, 0.3]
        result = MagicMock()
        result.embeddings = [embedding]
        return result

    with patch.object(llm.client.models, "embed_content", side_effect=fake_embed_content):
        result = llm.get_embedding("some text")

    assert result == [0.1, 0.2, 0.3]
    assert call_count["n"] == 2


def test_get_embedding_still_raises_if_both_attempts_fail():
    with patch.object(llm.client.models, "embed_content", side_effect=RuntimeError("down")):
        with pytest.raises(RuntimeError):
            llm.get_embedding("some text")


# --- Configurable chat model chain (GEMINI_CHAT_MODEL_CHAIN) ---------------


def test_build_chat_model_chain_falls_back_to_the_two_field_default(monkeypatch):
    monkeypatch.setattr(settings, "gemini_chat_model_chain", "")
    assert llm._build_chat_model_chain() == [settings.gemini_chat_model, settings.gemini_fallback_chat_model]


def test_build_chat_model_chain_parses_an_arbitrary_length_comma_separated_list(monkeypatch):
    monkeypatch.setattr(
        settings, "gemini_chat_model_chain", "gemini-2.5-flash, gemini-2.0-flash ,gemini-2.0-flash-lite"
    )
    assert llm._build_chat_model_chain() == ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]


def test_build_chat_model_chain_treats_whitespace_only_as_unset(monkeypatch):
    monkeypatch.setattr(settings, "gemini_chat_model_chain", "   ")
    assert llm._build_chat_model_chain() == [settings.gemini_chat_model, settings.gemini_fallback_chat_model]


def test_generate_chat_response_walks_a_longer_configured_chain(monkeypatch):
    monkeypatch.setattr(llm, "_CHAT_MODEL_CANDIDATES", ["model-a", "model-b", "model-c"])
    calls = []

    def fake_generate_content(model, contents, config):
        calls.append(model)
        if model == "model-c":
            return _FakeResponse("third model answered")
        raise RuntimeError(f"{model} down")

    with patch.object(llm.client.models, "generate_content", side_effect=fake_generate_content):
        result = llm.generate_chat_response("some prompt")

    assert result == "third model answered"
    assert calls == ["model-a", "model-b", "model-c"]


# --- Quota/rate-limit error classification ----------------------------------


def _quota_error() -> genai_errors.ClientError:
    return genai_errors.ClientError(429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "quota exceeded"}})


def test_is_quota_or_rate_limit_error_detects_a_429():
    assert llm._is_quota_or_rate_limit_error(_quota_error()) is True


def test_is_quota_or_rate_limit_error_detects_resource_exhausted_status_without_code_429():
    exc = genai_errors.APIError(400, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "quota"}})
    assert llm._is_quota_or_rate_limit_error(exc) is True


def test_is_quota_or_rate_limit_error_false_for_an_unrelated_error():
    assert llm._is_quota_or_rate_limit_error(RuntimeError("network blip")) is False
    assert llm._is_quota_or_rate_limit_error(genai_errors.APIError(500, {"error": {"status": "INTERNAL"}})) is False


def test_generate_chat_response_logs_the_quota_skip_reason(monkeypatch, caplog):
    monkeypatch.setattr(llm, "_CHAT_MODEL_CANDIDATES", ["model-a", "model-b"])

    def fake_generate_content(model, contents, config):
        if model == "model-a":
            raise _quota_error()
        return _FakeResponse("answer")

    with patch.object(llm.client.models, "generate_content", side_effect=fake_generate_content):
        with caplog.at_level("WARNING", logger="evidence_rag.llm"):
            result = llm.generate_chat_response("some prompt")

    assert result == "answer"
    assert any("quota/rate-limit" in record.message for record in caplog.records)
