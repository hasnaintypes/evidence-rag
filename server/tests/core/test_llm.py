"""Tests for src/core/llm.py's same-provider model fallback (issue #12) -
a simulated primary-model failure must not crash or silently degrade the
caller; the configured fallback model should be tried instead, and total
failure across both models must still report honestly rather than raise."""

from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest
from google.genai import errors as genai_errors

import src.core.llm as llm
from src.core.config import settings


@pytest.fixture(autouse=True)
def _reset_cloudflare_module_state():
    """_cloudflare_client/_cloudflare_cooldown_until are process-global
    (see llm.py's Cloudflare section) so a cooldown or cached client set
    by one test must never leak into another."""
    llm._cloudflare_client = None
    llm._cloudflare_cooldown_until = 0.0
    yield
    llm._cloudflare_client = None
    llm._cloudflare_cooldown_until = 0.0


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


# --- generate_chat_response_stream -------------------------------------------


def test_generate_chat_response_stream_yields_each_chunk_in_order():
    def fake_stream(model, contents, config):
        return iter([_FakeResponse("Hello "), _FakeResponse("world")])

    with patch.object(llm.client.models, "generate_content_stream", side_effect=fake_stream):
        result = list(llm.generate_chat_response_stream("some prompt"))

    assert result == ["Hello ", "world"]


def test_generate_chat_response_stream_falls_back_when_the_primary_yields_nothing():
    calls = []

    def fake_stream(model, contents, config):
        calls.append(model)
        if model == settings.gemini_chat_model:
            return iter([])
        return iter([_FakeResponse("fallback answer")])

    with patch.object(llm.client.models, "generate_content_stream", side_effect=fake_stream):
        result = list(llm.generate_chat_response_stream("some prompt"))

    assert result == ["fallback answer"]
    assert calls == [settings.gemini_chat_model, settings.gemini_fallback_chat_model]


def test_generate_chat_response_stream_falls_back_when_the_primary_raises_before_yielding():
    calls = []

    def fake_stream(model, contents, config):
        calls.append(model)
        if model == settings.gemini_chat_model:
            raise RuntimeError("simulated primary model failure")
        return iter([_FakeResponse("fallback answer")])

    with patch.object(llm.client.models, "generate_content_stream", side_effect=fake_stream):
        result = list(llm.generate_chat_response_stream("some prompt"))

    assert result == ["fallback answer"]
    assert calls == [settings.gemini_chat_model, settings.gemini_fallback_chat_model]


def test_generate_chat_response_stream_stops_on_a_mid_stream_failure_without_a_fallback():
    """Once the primary has already yielded partial text, a later failure
    from that same candidate must not retry on the next one - the caller
    has already shown the partial text, so silently swapping models would
    mean a different model finishing a sentence it never started."""

    def fake_stream(model, contents, config):
        def generator():
            yield _FakeResponse("Hello ")
            raise RuntimeError("dropped mid-stream")

        return generator()

    with patch.object(llm.client.models, "generate_content_stream", side_effect=fake_stream):
        result = list(llm.generate_chat_response_stream("some prompt"))

    assert result == ["Hello "]


def test_generate_chat_response_stream_reports_honest_failure_when_both_models_fail():
    with patch.object(llm.client.models, "generate_content_stream", side_effect=RuntimeError("both down")):
        result = list(llm.generate_chat_response_stream("some prompt"))

    assert len(result) == 1
    assert "error during generation" in result[0].lower()


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


def test_get_embedding_uses_query_input_type():
    captured = {}

    def fake_embed(texts, **kwargs):
        captured.update(kwargs)
        captured["texts"] = texts
        result = MagicMock()
        result.embeddings = [[0.1, 0.2, 0.3]]
        return result

    with patch.object(llm.embedding_client, "embed", side_effect=fake_embed):
        result = llm.get_embedding("some text")

    assert result == [0.1, 0.2, 0.3]
    assert captured["texts"] == ["some text"]
    assert captured["input_type"] == "query"


def test_get_embedding_retries_once_on_the_same_model_before_raising():
    call_count = {"n": 0}

    def fake_embed(texts, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("transient failure")
        result = MagicMock()
        result.embeddings = [[0.1, 0.2, 0.3]]
        return result

    with patch.object(llm.embedding_client, "embed", side_effect=fake_embed):
        result = llm.get_embedding("some text")

    assert result == [0.1, 0.2, 0.3]
    assert call_count["n"] == 2


def test_get_embedding_still_raises_if_both_attempts_fail():
    with patch.object(llm.embedding_client, "embed", side_effect=RuntimeError("down")):
        with pytest.raises(RuntimeError):
            llm.get_embedding("some text")


def test_get_embeddings_batch_uses_document_input_type_and_sends_one_call():
    captured = {}

    def fake_embed(texts, **kwargs):
        captured.update(kwargs)
        captured["texts"] = texts
        result = MagicMock()
        result.embeddings = [[i, i + 1] for i in range(len(texts))]
        return result

    with patch.object(llm.embedding_client, "embed", side_effect=fake_embed) as mock:
        result = llm.get_embeddings_batch(["a", "b", "c"])

    assert mock.call_count == 1
    assert captured["texts"] == ["a", "b", "c"]
    assert captured["input_type"] == "document"
    assert result == [[0, 1], [1, 2], [2, 3]]


def test_get_embeddings_batch_retries_once_on_the_same_model_before_raising():
    call_count = {"n": 0}

    def fake_embed(texts, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("transient failure")
        result = MagicMock()
        result.embeddings = [[0.1, 0.2], [0.3, 0.4]]
        return result

    with patch.object(llm.embedding_client, "embed", side_effect=fake_embed):
        result = llm.get_embeddings_batch(["x", "y"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    assert call_count["n"] == 2


def test_get_embeddings_batch_still_raises_if_both_attempts_fail():
    with patch.object(llm.embedding_client, "embed", side_effect=RuntimeError("down")):
        with pytest.raises(RuntimeError):
            llm.get_embeddings_batch(["x", "y"])


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


# --- generate_cloudflare_chat / generate_cloudflare_chat_stream (Cloudflare Workers AI) ---
# query_pipeline.py's final RAG answer generation only - see llm.py's
# Cloudflare section docstring. Everything else (query rewriting,
# reranking, judging, entity graph, titling) stays on Gemini and is
# covered by the tests above.


def _fake_completion(text, usage=None):
    message = MagicMock(content=text)
    choice = MagicMock(message=message)
    response = MagicMock(choices=[choice], usage=usage)
    return response


def _fake_stream_chunks(*texts):
    for text in texts:
        delta = MagicMock(content=text)
        choice = MagicMock(delta=delta)
        yield MagicMock(choices=[choice])


def _configure_cloudflare(monkeypatch):
    monkeypatch.setattr(settings, "cloudflare_account_id", "test-account")
    monkeypatch.setattr(settings, "cloudflare_api_token", "test-token")


def test_generate_cloudflare_chat_returns_an_honest_error_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "cloudflare_account_id", "")
    monkeypatch.setattr(settings, "cloudflare_api_token", "")
    result = llm.generate_cloudflare_chat("some prompt")
    assert "error during generation" in result.lower()
    assert "not configured" in result.lower()


def test_generate_cloudflare_chat_returns_the_model_text_on_success(monkeypatch):
    _configure_cloudflare(monkeypatch)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_completion("the answer")

    with patch.object(llm, "_cloudflare_client_or_raise", return_value=fake_client):
        result = llm.generate_cloudflare_chat("some prompt")

    assert result == "the answer"
    call_kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == settings.cloudflare_model
    assert call_kwargs["stream"] is False


def test_generate_cloudflare_chat_reports_an_empty_response_honestly(monkeypatch):
    _configure_cloudflare(monkeypatch)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_completion(None)

    with patch.object(llm, "_cloudflare_client_or_raise", return_value=fake_client):
        result = llm.generate_cloudflare_chat("some prompt")

    assert "error during generation" in result.lower()


def test_generate_cloudflare_chat_starts_a_cooldown_on_a_429_and_reports_honestly(monkeypatch):
    _configure_cloudflare(monkeypatch)
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(429, headers={"retry-after": "5"}, request=request)
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = openai.RateLimitError(
        "rate limited", response=response, body=None
    )

    with patch.object(llm, "_cloudflare_client_or_raise", return_value=fake_client):
        result = llm.generate_cloudflare_chat("some prompt")

    assert "error during generation" in result.lower()
    assert llm._cloudflare_cooldown_remaining() > 0


def test_generate_cloudflare_chat_skips_the_request_entirely_during_a_cooldown(monkeypatch):
    _configure_cloudflare(monkeypatch)
    llm._start_cloudflare_cooldown(30.0)
    fake_client = MagicMock()

    with patch.object(llm, "_cloudflare_client_or_raise", return_value=fake_client):
        result = llm.generate_cloudflare_chat("some prompt")

    assert "error during generation" in result.lower()
    assert "cooling down" in result.lower()
    fake_client.chat.completions.create.assert_not_called()


def test_generate_cloudflare_chat_retries_a_transient_failure_before_succeeding(monkeypatch):
    _configure_cloudflare(monkeypatch)
    monkeypatch.setattr(llm, "CLOUDFLARE_MAX_TRANSIENT_RETRIES", 1)
    request = httpx.Request("POST", "https://example.com")
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        openai.APIConnectionError(request=request),
        _fake_completion("recovered answer"),
    ]

    with patch.object(llm, "_cloudflare_client_or_raise", return_value=fake_client), patch("time.sleep"):
        result = llm.generate_cloudflare_chat("some prompt")

    assert result == "recovered answer"
    assert fake_client.chat.completions.create.call_count == 2


def test_generate_cloudflare_chat_stream_yields_each_chunk_in_order(monkeypatch):
    _configure_cloudflare(monkeypatch)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_stream_chunks("Hello ", "world")

    with patch.object(llm, "_cloudflare_client_or_raise", return_value=fake_client):
        result = list(llm.generate_cloudflare_chat_stream("some prompt"))

    assert result == ["Hello ", "world"]
    assert fake_client.chat.completions.create.call_args.kwargs["stream"] is True


def test_generate_cloudflare_chat_stream_reports_honest_failure_before_any_output(monkeypatch):
    _configure_cloudflare(monkeypatch)
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = RuntimeError("boom")

    with patch.object(llm, "_cloudflare_client_or_raise", return_value=fake_client):
        result = list(llm.generate_cloudflare_chat_stream("some prompt"))

    assert len(result) == 1
    assert "error during generation" in result[0].lower()


def test_generate_cloudflare_chat_stream_does_not_append_an_error_after_partial_output():
    """Once real text has streamed, a later failure must not glue a
    fabricated error sentinel onto the end of it."""

    def fake_stream(*args, **kwargs):
        yield MagicMock(choices=[MagicMock(delta=MagicMock(content="partial text"))])
        raise RuntimeError("dropped mid-stream")

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_stream()

    with patch.object(llm, "_cloudflare_client_or_raise", return_value=fake_client):
        result = list(llm.generate_cloudflare_chat_stream("some prompt"))

    assert result == ["partial text"]


# --- generate_cloudflare_json / _extract_json_block --------------------------
# Used by reranker.py, judge.py, and conversation_service.py's title
# generation now that none of them get a server-enforced schema from
# Cloudflare - the prompt asks for JSON in text, this parses it back out.


def test_extract_json_block_finds_a_simple_object():
    assert llm._extract_json_block('{"a": 1}') == '{"a": 1}'


def test_extract_json_block_handles_nested_structures():
    """A naive non-greedy regex (\\{.*?\\}) would stop at the first inner
    closing brace - this must return the whole, correctly-balanced block."""
    text = '{"scores": [{"index": 1, "relevance": 0.5}, {"index": 2, "relevance": 0.9}]}'
    assert llm._extract_json_block(text) == text


def test_extract_json_block_ignores_braces_inside_string_literals():
    text = '{"title": "A chat about {braces} and [brackets]"}'
    assert llm._extract_json_block(text) == text


def test_extract_json_block_strips_stray_text_around_the_json():
    text = 'Sure, here you go:\n{"title": "A Title"}\nHope that helps!'
    assert llm._extract_json_block(text) == '{"title": "A Title"}'


def test_extract_json_block_returns_none_when_no_json_present():
    assert llm._extract_json_block("no json here at all") is None


def test_generate_cloudflare_json_returns_the_parsed_dict_on_success(monkeypatch):
    _configure_cloudflare(monkeypatch)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_completion('{"score": 0.8, "unsupported_claims": []}')

    with patch.object(llm, "_cloudflare_client_or_raise", return_value=fake_client):
        result = llm.generate_cloudflare_json("some prompt")

    assert result == {"score": 0.8, "unsupported_claims": []}


def test_generate_cloudflare_json_parses_json_with_stray_text_around_it(monkeypatch):
    _configure_cloudflare(monkeypatch)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_completion(
        'Here is the result:\n{"title": "A Title"}\nLet me know if you need anything else.'
    )

    with patch.object(llm, "_cloudflare_client_or_raise", return_value=fake_client):
        result = llm.generate_cloudflare_json("some prompt")

    assert result == {"title": "A Title"}


def test_generate_cloudflare_json_returns_none_on_an_empty_response(monkeypatch):
    _configure_cloudflare(monkeypatch)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_completion(None)

    with patch.object(llm, "_cloudflare_client_or_raise", return_value=fake_client):
        result = llm.generate_cloudflare_json("some prompt")

    assert result is None


def test_generate_cloudflare_json_returns_none_when_no_json_block_is_found(monkeypatch):
    _configure_cloudflare(monkeypatch)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_completion("I'm not sure how to answer that.")

    with patch.object(llm, "_cloudflare_client_or_raise", return_value=fake_client):
        result = llm.generate_cloudflare_json("some prompt")

    assert result is None


def test_generate_cloudflare_json_returns_none_on_invalid_json(monkeypatch):
    _configure_cloudflare(monkeypatch)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_completion('{"score": 0.8,}')

    with patch.object(llm, "_cloudflare_client_or_raise", return_value=fake_client):
        result = llm.generate_cloudflare_json("some prompt")

    assert result is None


def test_generate_cloudflare_json_returns_none_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "cloudflare_account_id", "")
    monkeypatch.setattr(settings, "cloudflare_api_token", "")
    result = llm.generate_cloudflare_json("some prompt")
    assert result is None
