import json

from google import genai
from google.genai import types
from src.config import settings
from typing import Any, Dict, List, Optional

# Tracked so db.py can flag a change of embedding model, which would
# produce vectors of a different dimension than what's already indexed.
EMBEDDING_MODEL_NAME = settings.gemini_embedding_model

client = genai.Client(api_key=settings.gemini_api_key)

# --------------------------------------------------------------------------- #
# Model routing / fallback
#
# generate_chat_response()/generate_structured_response() call the primary
# model first, then settings.gemini_fallback_chat_model once on any
# failure (API error, rate-limit, malformed response) - a single same-
# provider fallback, not a retry loop or a multi-vendor abstraction (out
# of scope - see GitHub issue #12's non-goals). Whichever model succeeds
# returns through the exact same code path, so a fallback-model answer is
# indistinguishable to query_pipeline.py from a primary-model one and
# still goes through the faithfulness/abstention gates there - it isn't a
# bypass, just a different source for the same "generated text" value.
# --------------------------------------------------------------------------- #

_CHAT_MODEL_CANDIDATES = (settings.gemini_chat_model, settings.gemini_fallback_chat_model)


def get_embedding(text: str) -> List[float]:
    """
    Generates a vector embedding for the provided text via the Gemini API.

    Retries once on the same model (no model-swap fallback - a different
    embedding model would produce a vector of a different dimension than
    what's already indexed, see settings.gemini_fallback_chat_model's
    comment). Still raises on a second failure, same as before this
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
    Sends the augmented prompt to Gemini and returns the response, trying
    settings.gemini_fallback_chat_model once if the primary model's call
    fails for any reason (API error, rate-limit, etc).

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
                return response.text
            errors.append(f"{model}: empty response")
        except Exception as e:
            errors.append(f"{model}: {e}")
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
    as the rest of this module. Tries settings.gemini_fallback_chat_model
    once if the primary model's call fails, same as generate_chat_response().
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
                continue
            return json.loads(raw_text)
        except Exception:
            continue
    return None
