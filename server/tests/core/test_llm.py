"""Tests for src/llm.py's same-provider model fallback (issue #12) -
a simulated primary-model failure must not crash or silently degrade the
caller; the configured fallback model should be tried instead, and total
failure across both models must still report honestly rather than raise."""

from unittest.mock import MagicMock, patch

import pytest

import src.llm as llm
from src.config import settings


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
