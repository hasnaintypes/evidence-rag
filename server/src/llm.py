import json

from google import genai
from google.genai import types
from src.config import settings
from typing import Any, Dict, List, Optional

# Tracked so db.py can flag a change of embedding model, which would
# produce vectors of a different dimension than what's already indexed.
EMBEDDING_MODEL_NAME = settings.gemini_embedding_model

client = genai.Client(api_key=settings.gemini_api_key)


def get_embedding(text: str) -> List[float]:
    """
    Generates a vector embedding for the provided text via the Gemini API.
    """
    clean_text = text.replace("\n", " ")
    result = client.models.embed_content(model=settings.gemini_embedding_model, contents=clean_text)
    return result.embeddings[0].values


def generate_chat_response(prompt: str, max_tokens: Optional[int] = None) -> str:
    """
    Sends the augmented prompt to Gemini and returns the response.

    max_tokens: overrides settings.generation_max_tokens for this call.
    Useful for short, structured outputs (e.g. entity extraction JSON
    arrays, sub-query decomposition) where the default long-answer
    budget wastes tokens for no benefit.
    """
    try:
        response = client.models.generate_content(
            model=settings.gemini_chat_model,
            contents=f"You are an intelligent AI assistant.\n\n{prompt}",
            config=types.GenerateContentConfig(
                temperature=settings.generation_temperature,
                max_output_tokens=max_tokens if max_tokens is not None else settings.generation_max_tokens,
            ),
        )
        return response.text
    except Exception as e:
        return f"Error during generation: {str(e)}"


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
    as the rest of this module.
    """
    try:
        response = client.models.generate_content(
            model=settings.gemini_chat_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens if max_tokens is not None else settings.generation_max_tokens,
                response_mime_type="application/json",
                response_schema=response_schema,
            ),
        )
        raw_text = response.text
        if not raw_text:
            return None
        return json.loads(raw_text)
    except Exception:
        return None
