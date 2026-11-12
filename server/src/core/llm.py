import json
import logging
import random
import time

import openai
import voyageai
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from src.core.config import settings
from typing import Any, Dict, Iterator, List, Optional

# Tracked so db.py can flag a change of embedding model, which would
# produce vectors of a different dimension than what's already indexed.
EMBEDDING_MODEL_NAME = settings.voyage_embedding_model

client = genai.Client(api_key=settings.gemini_api_key)
# Separate client/provider from chat generation above - embeddings and
# chat generation are independent calls in this pipeline (nothing
# downstream cares which provider produced either), so there's no
# requirement they come from the same vendor. See get_embedding()/
# get_embeddings_batch() below.
embedding_client = voyageai.Client(api_key=settings.voyage_api_key)

# Logs model-routing decisions (which candidate failed/was skipped and
# why, which one ultimately answered) through the standard logging
# module - same "inherits whatever handler the process entry point set
# up for the root logger" convention as observability.py's
# "evidence_rag.pipeline" logger, rather than returning this detail
# through every caller's return value (judge.py, graph.py, reranker.py,
# query_rewriter.py, query_pipeline.py all just want the generated text/
# dict back, not a routing trace).
logger = logging.getLogger("evidence_rag.llm")

# --------------------------------------------------------------------------- #
# Model routing / fallback (Gemini)
#
# generate_chat_response()/generate_structured_response() walk
# _CHAT_MODEL_CANDIDATES in order, trying the next one on any failure
# (API error, rate-limit, malformed response) - a same-provider cascade,
# not a retry loop or a multi-vendor abstraction (out of scope - see
# GitHub issue #12's non-goals). Whichever model succeeds returns through
# the exact same code path, so a fallback-model answer is indistinguishable
# to its caller from a primary-model one and still goes through whatever
# gates that caller applies - it isn't a bypass, just a different source
# for the same "generated text" value.
#
# The chain defaults to the 2-element (gemini_chat_model,
# gemini_fallback_chat_model) pair for backward compatibility, but
# settings.gemini_chat_model_chain (a comma-separated env var) can
# override it with an arbitrary-length list - each extra model is a
# separate free-tier quota bucket, directly multiplying the total request
# budget available before every candidate is exhausted. See
# scripts/list_available_models.py for discovering which model ids this
# API key can actually call right now, rather than guessing from a
# marketing-name list that may not match the real API model id.
#
# Neither generate_chat_response() nor generate_structured_response() backs
# any *active* call path anymore - this project's own Gemini quota
# repeatedly ran out during real use (every candidate in this chain
# exhausted, one after another, both for the final RAG answer and for the
# comparatively light judge/reranker/title-generation calls), so every
# call site that used to depend on this chain (query_pipeline.py's final
# answer, retrieval/query_rewriter.py's query expansion/decomposition,
# retrieval/reranker.py, evaluation/judge.py, conversation_service.py's
# title generation) moved to Cloudflare Workers AI - see the Cloudflare
# section below (generate_cloudflare_chat()/generate_cloudflare_chat_stream()/
# generate_cloudflare_json()). The two functions here are kept only for
# src/graph.py's entity-graph extraction (disabled by default via
# ENABLE_ENTITY_GRAPH, so this chain costs nothing while it's off) and
# scripts/test_connection.py's connectivity check - not deleted, since
# that dormant feature still needs a working implementation if it's ever
# re-enabled, but genuinely unused by any path that runs in normal use.
# --------------------------------------------------------------------------- #


def _build_chat_model_chain() -> List[str]:
    if settings.gemini_chat_model_chain.strip():
        chain = [m.strip() for m in settings.gemini_chat_model_chain.split(",") if m.strip()]
        if chain:
            return chain
    return [settings.gemini_chat_model, settings.gemini_fallback_chat_model]


_CHAT_MODEL_CANDIDATES = _build_chat_model_chain()


def _is_quota_or_rate_limit_error(exc: Exception) -> bool:
    """True for Gemini's actual quota/rate-limit signal (HTTP 429 /
    RESOURCE_EXHAUSTED), as opposed to some other failure (malformed
    request, transient network error, etc). Doesn't change the cascade
    behavior below - every failure still moves on to the next candidate
    regardless of cause - but lets the routing log say *why* a candidate
    was skipped, which is the detail #16's observability work is after:
    seeing "candidate #3 is absorbing most traffic" as an early warning
    before the whole chain is exhausted, rather than only finding out
    once every model in it fails at once."""
    if isinstance(exc, genai_errors.APIError):
        if exc.code == 429:
            return True
        if exc.status and "RESOURCE_EXHAUSTED" in str(exc.status).upper():
            return True
    return False


def _skip_reason(exc: Exception) -> str:
    return "quota/rate-limit" if _is_quota_or_rate_limit_error(exc) else "error"


def get_embedding(text: str) -> List[float]:
    """
    Generates a vector embedding for the provided text via the Voyage AI API.

    input_type="query": Voyage's embeddings are asymmetric - query text and
    document text are embedded slightly differently to improve retrieval
    quality, so a chat-time query embedding must use "query" here while
    get_embeddings_batch() below (ingestion-time document chunks) uses
    "document". Mixing these up doesn't break the dimension/shape, just
    degrades ranking quality, so there's no runtime check for it - this
    is the one place that matters.

    Retries once on the same model (no model-swap fallback, and
    deliberately no multi-model chain like the chat functions below have -
    a different embedding model would produce a vector of a different
    dimension/semantic space than what's already indexed; see
    settings.voyage_embedding_dimension's comment). Still raises on a
    second failure, same as before this retry was added - callers (e.g.
    query_pipeline.py, via api/routers/conversations.py's blanket exception
    handler) already treat an uncaught embedding failure as a pipeline
    failure to report honestly, not something to swallow here.

    Single-text only - a query embedding at chat time is always exactly
    one string. Bulk document ingestion uses get_embeddings_batch() below
    instead, which is the one that actually matters for throughput.
    """
    clean_text = text.replace("\n", " ")
    kwargs = dict(
        model=settings.voyage_embedding_model,
        input_type="query",
        output_dimension=settings.voyage_embedding_dimension,
    )
    try:
        result = embedding_client.embed([clean_text], **kwargs)
    except Exception:
        result = embedding_client.embed([clean_text], **kwargs)
    return result.embeddings[0]


def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Embeds many chunks in ONE Voyage API call instead of one call per
    chunk - see ingestion/pipeline.py's finish_ingest() docstring for why
    this is the actual indexing bottleneck (network round-trip latency per
    chunk, not embedding compute time): embed() accepts a list of texts
    directly.

    input_type="document" - see get_embedding()'s docstring for why
    ingestion-time chunks and chat-time queries use different input_type
    values for the same embed() call.

    Returns embeddings in the same order as `texts` - the embeddings API's
    documented ordering contract for a batch request - so callers can zip
    the result back against their own item list positionally.

    Retries the whole batch once on the same model, same policy as
    get_embedding() above. A batch that's too large (e.g. an oversized
    payload) will fail both attempts the same way - handled by the
    caller choosing a conservative EMBED_BATCH_SIZE, not by a runtime
    fallback to smaller batches here, so a persistent failure surfaces
    immediately instead of silently degrading to one-at-a-time.
    """
    clean_texts = [t.replace("\n", " ") for t in texts]
    kwargs = dict(
        model=settings.voyage_embedding_model,
        input_type="document",
        output_dimension=settings.voyage_embedding_dimension,
    )
    try:
        result = embedding_client.embed(clean_texts, **kwargs)
    except Exception:
        result = embedding_client.embed(clean_texts, **kwargs)
    return result.embeddings


def generate_chat_response(prompt: str, max_tokens: Optional[int] = None) -> str:
    """
    Sends the augmented prompt to Gemini and returns the response, walking
    _CHAT_MODEL_CANDIDATES (settings.gemini_chat_model_chain, or the
    2-element primary/fallback pair by default) until one succeeds.

    max_tokens: overrides settings.generation_max_tokens for this call.
    Useful for short, structured outputs (e.g. entity extraction JSON
    arrays, sub-query decomposition) where the default long-answer
    budget wastes tokens for no benefit.
    """
    config = types.GenerateContentConfig(
        temperature=settings.generation_temperature,
        max_output_tokens=max_tokens if max_tokens is not None else settings.generation_max_tokens,
    )
    errors: List[str] = []
    for model in _CHAT_MODEL_CANDIDATES:
        try:
            response = client.models.generate_content(
                model=model,
                contents=f"You are an intelligent AI assistant.\n\n{prompt}",
                config=config,
            )
            # response.text is Optional[str] - None (not a raised
            # exception) when a candidate has no text parts, e.g. the
            # model stopped on SAFETY/MAX_TOKENS. Treated as a failure
            # worth trying the fallback on too, same as
            # generate_structured_response()'s empty-response check below.
            if response.text:
                if model != _CHAT_MODEL_CANDIDATES[0]:
                    logger.warning("generate_chat_response: served by fallback candidate %r", model)
                return response.text
            errors.append(f"{model}: empty response")
            logger.warning("generate_chat_response: candidate %r returned an empty response, trying next", model)
        except Exception as e:
            errors.append(f"{model}: {e}")
            logger.warning("generate_chat_response: candidate %r failed (%s), trying next", model, _skip_reason(e))
    logger.error("generate_chat_response: every candidate in the chain failed: %s", "; ".join(errors))
    return f"Error during generation: {'; '.join(errors)}"


def generate_chat_response_stream(prompt: str, max_tokens: Optional[int] = None):
    """
    Same model-fallback chain as generate_chat_response(), but yields text
    chunks as they arrive from client.models.generate_content_stream()
    instead of returning the full response at once - used by the chat
    route's SSE path (api/services/conversation_service.py) to show the
    answer to the user as it's generated, instead of waiting for
    generation (the longest single call in process_chat_query()'s chain)
    plus the faithfulness judge call after it to both finish first.

    Once a candidate has produced at least one chunk, a later failure
    from that same candidate can't be silently retried on the next one -
    the caller has already shown that partial text - so this only falls
    back to the next candidate when a model fails before yielding
    anything (its initial request erroring/rate-limiting), the same
    failure mode generate_chat_response() recovers from.
    """
    config = types.GenerateContentConfig(
        temperature=settings.generation_temperature,
        max_output_tokens=max_tokens if max_tokens is not None else settings.generation_max_tokens,
    )
    errors: List[str] = []
    for model in _CHAT_MODEL_CANDIDATES:
        yielded_any = False
        try:
            stream = client.models.generate_content_stream(
                model=model,
                contents=f"You are an intelligent AI assistant.\n\n{prompt}",
                config=config,
            )
            for chunk in stream:
                if chunk.text:
                    yielded_any = True
                    yield chunk.text
            if yielded_any:
                if model != _CHAT_MODEL_CANDIDATES[0]:
                    logger.warning("generate_chat_response_stream: served by fallback candidate %r", model)
                return
            errors.append(f"{model}: empty response")
            logger.warning("generate_chat_response_stream: candidate %r returned an empty response, trying next", model)
        except Exception as e:
            if yielded_any:
                logger.error(
                    "generate_chat_response_stream: candidate %r failed mid-stream (%s)", model, _skip_reason(e)
                )
                return
            errors.append(f"{model}: {e}")
            logger.warning(
                "generate_chat_response_stream: candidate %r failed (%s), trying next", model, _skip_reason(e)
            )
    logger.error("generate_chat_response_stream: every candidate in the chain failed: %s", "; ".join(errors))
    yield f"Error during generation: {'; '.join(errors)}"


# --------------------------------------------------------------------------- #
# Chat generation (Cloudflare Workers AI) - the active provider for this app
#
# Every LLM call this app makes in normal use goes through one of the
# three functions below - generate_cloudflare_chat()/
# generate_cloudflare_chat_stream() (free text: query_pipeline.py's final
# RAG answer, retrieval/query_rewriter.py's query expansion/decomposition)
# and generate_cloudflare_json() (JSON-shaped: retrieval/reranker.py,
# evaluation/judge.py, conversation_service.py's title generation) -
# after this project's own Gemini quota repeatedly exhausted every
# candidate in _CHAT_MODEL_CANDIDATES during real use, for both the final
# answer and the comparatively light judge/reranker/title calls. Only
# src/graph.py's entity-graph extraction (disabled by default) and
# scripts/test_connection.py still use the Gemini functions above.
#
# generate_cloudflare_json() has no server-enforced schema the way
# generate_structured_response() did on Gemini - Cloudflare's OpenAI-
# compatible endpoint doesn't document reliable JSON-mode/structured-
# output support across models - so it works the way this project's own
# entity-graph extraction used to before generate_structured_response()
# existed: the prompt itself asks for JSON text, and the response is
# parsed defensively (first `{...}`/`[...]` block found, regex-extracted
# in case the model added stray text around it despite instructions,
# `None` on any parse failure so the caller can fall back gracefully
# rather than crash).
#
# Uses Cloudflare's OpenAI-compatible Chat Completions endpoint
# (https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)
# via the `openai` SDK pointed at Cloudflare's base_url, rather than a new
# bespoke HTTP client - Cloudflare's own docs recommend this path, and it
# avoids hand-rolling request/response parsing for a shape the `openai`
# package already models correctly (ChatCompletion/ChatCompletionChunk).
#
# Deliberately NOT a blind "try every candidate, every time" loop like
# the Gemini chain above - this project watched exactly that pattern burn
# several minutes retrying two already-exhausted Gemini models on every
# single call during ingestion (#entity-graph slowness, 2026-11-12).
# Instead: a single configured model (settings.cloudflare_model) with a
# process-local cooldown that activates on an HTTP 429 and is cleared
# instead of retried - see _cloudflare_cooldown_remaining()/
# _start_cloudflare_cooldown() below. A transient (non-429) failure - a
# timeout or connection reset - gets a small number of retries with
# exponential backoff + jitter, since those are the failures a brief
# retry can plausibly fix; a 429 never is, since the model is already
# known to be out of quota and retrying it immediately just burns another
# round trip for the same answer.
# --------------------------------------------------------------------------- #

CLOUDFLARE_RATE_LIMIT_COOLDOWN_DEFAULT_SECONDS = 60.0
CLOUDFLARE_MAX_TRANSIENT_RETRIES = 2

_cloudflare_client: Optional["openai.OpenAI"] = None
_cloudflare_cooldown_until = 0.0  # time.monotonic() timestamp; 0.0 = not cooling down


def _cloudflare_client_or_raise() -> "openai.OpenAI":
    """Lazily builds the Cloudflare client on first use rather than at
    import time, so the rest of the app (including every test in this
    repo) still boots and runs without CLOUDFLARE_ACCOUNT_ID/
    CLOUDFLARE_API_TOKEN set - only an actual call to
    generate_cloudflare_chat()/generate_cloudflare_chat_stream() needs them, and
    raises a clear, specific error here if they're missing rather than a
    generic auth failure from the HTTP layer."""
    global _cloudflare_client
    if _cloudflare_client is None:
        if not settings.cloudflare_account_id or not settings.cloudflare_api_token:
            raise RuntimeError(
                "Cloudflare Workers AI is not configured - set CLOUDFLARE_ACCOUNT_ID and "
                "CLOUDFLARE_API_TOKEN (see .env.example) before generate_cloudflare_chat()/"
                "generate_cloudflare_chat_stream() can be called."
            )
        _cloudflare_client = openai.OpenAI(
            api_key=settings.cloudflare_api_token,
            base_url=f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id}/ai/v1",
            timeout=30.0,
        )
    return _cloudflare_client


def _cloudflare_cooldown_remaining() -> float:
    return max(0.0, _cloudflare_cooldown_until - time.monotonic())


def _start_cloudflare_cooldown(seconds: float) -> None:
    global _cloudflare_cooldown_until
    _cloudflare_cooldown_until = time.monotonic() + seconds


def _cloudflare_retry_after_seconds(exc: "openai.RateLimitError") -> float:
    """Respects the 429 response's Retry-After header when Cloudflare
    sends one; falls back to a default cooldown + jitter when it
    doesn't, rather than assuming a fixed duration."""
    try:
        header = exc.response.headers.get("retry-after")
        if header:
            return float(header)
    except Exception:
        pass
    return CLOUDFLARE_RATE_LIMIT_COOLDOWN_DEFAULT_SECONDS + random.uniform(0, 5)


def _cloudflare_chat_completion(messages: List[Dict[str, str]], max_tokens: int, temperature: float, stream: bool):
    """
    One logical request to Cloudflare's Chat Completions endpoint for
    settings.cloudflare_model, with bounded retry+backoff for transient
    errors - see this module's Cloudflare section docstring for why a 429
    is handled differently (cooldown, not retry) from everything else.

    Raises RuntimeError immediately, without even attempting the request,
    if the model is already in cooldown from a previous 429 - this is
    what keeps a rate-limited model from being hit again on every
    subsequent call until the cooldown clears.
    """
    remaining = _cloudflare_cooldown_remaining()
    if remaining > 0:
        raise RuntimeError(f"Cloudflare Workers AI is cooling down after a rate limit - retry in {remaining:.0f}s.")

    http_client = _cloudflare_client_or_raise()
    last_error: Optional[Exception] = None
    for attempt in range(CLOUDFLARE_MAX_TRANSIENT_RETRIES + 1):
        start = time.perf_counter()
        try:
            response = http_client.chat.completions.create(
                model=settings.cloudflare_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=stream,
            )
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            logger.info(
                "cloudflare chat completion ok model=%r elapsed_ms=%s stream=%s",
                settings.cloudflare_model,
                elapsed_ms,
                stream,
            )
            return response
        except openai.RateLimitError as e:
            cooldown = _cloudflare_retry_after_seconds(e)
            _start_cloudflare_cooldown(cooldown)
            logger.warning(
                "cloudflare chat completion rate-limited (model=%r), cooling down for %.0fs",
                settings.cloudflare_model,
                cooldown,
            )
            raise
        except (openai.APIConnectionError, openai.APITimeoutError) as e:
            last_error = e
            if attempt < CLOUDFLARE_MAX_TRANSIENT_RETRIES:
                backoff = (0.5 * (2**attempt)) + random.uniform(0, 0.5)
                logger.warning(
                    "cloudflare chat completion transient failure (%s), retrying in %.1fs (attempt %d/%d)",
                    e,
                    backoff,
                    attempt + 1,
                    CLOUDFLARE_MAX_TRANSIENT_RETRIES,
                )
                time.sleep(backoff)
                continue
            logger.error("cloudflare chat completion failed after %d retries: %s", CLOUDFLARE_MAX_TRANSIENT_RETRIES, e)
            raise
    raise last_error  # pragma: no cover - loop always returns or raises above


def generate_cloudflare_chat(prompt: str, max_tokens: Optional[int] = None) -> str:
    """
    Generates free text via Cloudflare Workers AI - query_pipeline.py's
    final RAG answer and retrieval/query_rewriter.py's query expansion/
    decomposition. See this module's Cloudflare section docstring for
    why this is the active chat-generation provider, not Gemini.

    Mirrors generate_chat_response()'s honest-failure contract exactly:
    returns "Error during generation: ..." on any failure rather than
    raising, since query_pipeline.py's generation_failed check keys off
    that exact substring regardless of which provider produced it.
    """
    try:
        response = _cloudflare_chat_completion(
            messages=[{"role": "user", "content": f"You are an intelligent AI assistant.\n\n{prompt}"}],
            max_tokens=max_tokens if max_tokens is not None else settings.generation_max_tokens,
            temperature=settings.generation_temperature,
            stream=False,
        )
        text = response.choices[0].message.content if response.choices else None
        if text:
            if response.usage:
                logger.info(
                    "generate_cloudflare_chat: prompt_tokens=%s completion_tokens=%s",
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                )
            return text
        logger.warning("generate_cloudflare_chat: Cloudflare returned an empty response")
        return "Error during generation: Cloudflare Workers AI returned an empty response"
    except Exception as e:
        logger.error("generate_cloudflare_chat: Cloudflare call failed: %s", e)
        return f"Error during generation: {e}"


def generate_cloudflare_chat_stream(prompt: str, max_tokens: Optional[int] = None) -> Iterator[str]:
    """
    Streaming counterpart to generate_cloudflare_chat() - see that function's
    docstring and this module's Cloudflare section docstring for scope.

    Once a chunk has actually been yielded, a later mid-stream failure is
    logged and simply ends the stream rather than appending the
    "Error during generation: ..." sentinel after real partial text -
    same reasoning as generate_chat_response_stream()'s equivalent case.
    """
    yielded_any = False
    try:
        stream = _cloudflare_chat_completion(
            messages=[{"role": "user", "content": f"You are an intelligent AI assistant.\n\n{prompt}"}],
            max_tokens=max_tokens if max_tokens is not None else settings.generation_max_tokens,
            temperature=settings.generation_temperature,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yielded_any = True
                yield delta
    except Exception as e:
        if yielded_any:
            logger.error("generate_cloudflare_chat_stream: Cloudflare call failed mid-stream: %s", e)
            return
        logger.error("generate_cloudflare_chat_stream: Cloudflare call failed before any output: %s", e)
        yield f"Error during generation: {e}"
        return

    if not yielded_any:
        logger.warning("generate_cloudflare_chat_stream: Cloudflare returned an empty response")
        yield "Error during generation: Cloudflare Workers AI returned an empty response"


def _extract_json_block(text: str) -> Optional[str]:
    """
    Finds the first balanced {...} or [...] block in `text`, respecting
    string literals so a brace/bracket inside a quoted string doesn't
    throw off the depth count - a plain non-greedy regex (`\\{.*?\\}`)
    breaks on any nested structure (e.g. reranker.py's response shape,
    {"scores": [{"index": 1, ...}, ...]}), stopping at the first inner
    closing brace instead of the real end of the object. Tolerates stray
    text around the JSON despite the prompt asking for nothing else - the
    same real-world small-model behavior src/graph.py's pre-
    generate_structured_response() entity extraction had to handle.
    """
    start = next((i for i, ch in enumerate(text) if ch in "{["), None)
    if start is None:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def generate_cloudflare_json(prompt: str, max_tokens: Optional[int] = None, temperature: float = 0.0) -> Optional[dict]:
    """
    Generates a JSON-shaped result via Cloudflare Workers AI, for callers
    that need a reliably parseable structured output but can't lean on a
    server-enforced schema the way generate_structured_response() did on
    Gemini (see this module's Cloudflare section docstring) -
    retrieval/reranker.py's relevance scores, evaluation/judge.py's
    faithfulness score, conversation_service.py's title generation. The
    prompt passed in must itself instruct the model to output JSON in
    the expected shape; this only parses whatever comes back.

    Returns the parsed dict/list, or None on any failure (API error,
    cooldown, no JSON block found, invalid JSON) so callers fall back
    gracefully - same "best-effort enrichment, never breaks the main
    response" posture as generate_structured_response() had.
    """
    try:
        response = _cloudflare_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens if max_tokens is not None else settings.generation_max_tokens,
            temperature=temperature,
            stream=False,
        )
        raw_text = response.choices[0].message.content if response.choices else None
        if not raw_text:
            logger.warning("generate_cloudflare_json: Cloudflare returned an empty response")
            return None

        block = _extract_json_block(raw_text)
        if block is None:
            logger.warning("generate_cloudflare_json: no JSON block found in the response")
            return None

        return json.loads(block)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("generate_cloudflare_json: response was not valid JSON: %s", e)
        return None
    except Exception as e:
        logger.error("generate_cloudflare_json: Cloudflare call failed: %s", e)
        return None


VISION_TRANSCRIPTION_PROMPT = """This is a scanned page from a technical/industrial document with no extractable text layer. Transcribe its content as plain text, preserving structure:
- Put section headings on their own line, formatted like "5.1 Emergency Stop" if a number/title is visible.
- Prefix safety callouts exactly as printed, e.g. "WARNING: ..." or "NOTE: ...".
- Preserve paragraph breaks as blank lines.
- If there's a diagram or photo, describe it in one line prefixed with "Figure:".
Output only the transcription, no commentary."""


def transcribe_page_image(image_bytes: bytes) -> str:
    """
    Sends a rendered PDF page image to Gemini for OCR/transcription, used as
    a fallback for scanned pages that pdfplumber's text extraction can't
    read (see ingestion/parsers/pdf.py). Best-effort: returns "" on any
    failure so ingestion can fall back to a placeholder node instead of
    crashing the whole document.
    """
    try:
        response = client.models.generate_content(
            model=settings.gemini_chat_model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                VISION_TRANSCRIPTION_PROMPT,
            ],
            config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=2000),
        )
        return response.text or ""
    except Exception:
        return ""


def generate_structured_response(
    prompt: str,
    response_schema: Dict[str, Any],
    max_tokens: Optional[int] = None,
    temperature: float = 0.0,
) -> Optional[dict]:
    """
    Sends a prompt to Gemini constrained to a JSON schema (via
    response_mime_type="application/json" + response_schema) and returns
    the parsed dict, instead of free text that has to be regex-scraped
    for a JSON blob.

    Only used by src/graph.py's entity-graph extraction now (disabled by
    default via ENABLE_ENTITY_GRAPH - see this module's Gemini section
    comment) - reranking, faithfulness judging, and title generation
    moved to generate_cloudflare_json() above, which has no server-
    enforced schema and parses the same way graph.py's extraction used
    to before this function existed.

    Returns None on any failure (API error, non-JSON output, schema
    mismatch) so callers can fall back gracefully rather than crash -
    same "best-effort enrichment, never breaks the main response" pattern
    as the rest of this module. Walks the same _CHAT_MODEL_CANDIDATES
    chain as generate_chat_response().
    """
    config = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_tokens if max_tokens is not None else settings.generation_max_tokens,
        response_mime_type="application/json",
        response_schema=response_schema,
    )
    for model in _CHAT_MODEL_CANDIDATES:
        try:
            response = client.models.generate_content(model=model, contents=prompt, config=config)
            raw_text = response.text
            if not raw_text:
                logger.warning("generate_structured_response: candidate %r returned an empty response", model)
                continue
            parsed = json.loads(raw_text)
            if model != _CHAT_MODEL_CANDIDATES[0]:
                logger.warning("generate_structured_response: served by fallback candidate %r", model)
            return parsed
        except Exception as e:
            logger.warning(
                "generate_structured_response: candidate %r failed (%s), trying next", model, _skip_reason(e)
            )
    logger.error("generate_structured_response: every candidate in the chain failed")
    return None
