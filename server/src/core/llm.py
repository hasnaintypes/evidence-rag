import json
import logging

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from src.core.config import settings
from typing import Any, Dict, List, Optional

# Tracked so db.py can flag a change of embedding model, which would
# produce vectors of a different dimension than what's already indexed.
EMBEDDING_MODEL_NAME = settings.gemini_embedding_model

client = genai.Client(api_key=settings.gemini_api_key)

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
# Model routing / fallback
#
# generate_chat_response()/generate_structured_response() walk
# _CHAT_MODEL_CANDIDATES in order, trying the next one on any failure
# (API error, rate-limit, malformed response) - a same-provider cascade,
# not a retry loop or a multi-vendor abstraction (out of scope - see
# GitHub issue #12's non-goals). Whichever model succeeds returns through
# the exact same code path, so a fallback-model answer is indistinguishable
# to query_pipeline.py from a primary-model one and still goes through the
# faithfulness/abstention gates there - it isn't a bypass, just a
# different source for the same "generated text" value.
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
    Generates a vector embedding for the provided text via the Gemini API.

    Retries once on the same model (no model-swap fallback, and
    deliberately no multi-model chain like the chat functions below have -
    a different embedding model would produce a vector of a different
    dimension/semantic space than what's already indexed; see
    settings.gemini_fallback_chat_model's comment). Still raises on a
    second failure, same as before this
    retry was added - callers (e.g. query_pipeline.py, via
    api/routers/conversations.py's blanket exception handler) already
    treat an uncaught embedding failure as a pipeline failure to report
    honestly, not something to swallow here.
    """
    clean_text = text.replace("\n", " ")
    try:
        result = client.models.embed_content(model=settings.gemini_embedding_model, contents=clean_text)
    except Exception:
        result = client.models.embed_content(model=settings.gemini_embedding_model, contents=clean_text)
    return result.embeddings[0].values


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
    for a JSON blob (see graph.py's entity extraction, which predates this
    and has to handle stray text around the array as a result).

    Used by callers that need a reliably parseable structured output -
    e.g. the faithfulness judge's {score, unsupported_claims} shape.

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
