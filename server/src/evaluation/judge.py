from typing import Any, Dict, List, Optional

from src.llm import generate_structured_response

# --------------------------------------------------------------------------- #
# Answer faithfulness scoring (LLM-as-judge)
#
# Retrieval metrics (Precision@K/Recall@K/MRR, see scripts/run_eval.py) only
# say whether the right chunks were *retrieved* - they say nothing about
# whether the *generated answer* actually sticks to what those chunks say.
# A system can retrieve the correct source and still hallucinate or
# misstate it. This module runs a second, cheap Gemini call as a judge:
# given the generated answer and the exact chunks it was allowed to use,
# score whether every claim in the answer is supported by them.
# --------------------------------------------------------------------------- #

# 0.0 = answer is entirely unsupported by the provided chunks (pure
# hallucination), 1.0 = every claim is directly supported. Judge is
# instructed to score fractionally when only some claims are unsupported.
FAITHFULNESS_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "score": {
            "type": "number",
            "description": "0.0-1.0 fraction of the answer's claims that are supported by the provided chunks.",
        },
        "unsupported_claims": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short quotes/paraphrases of claims in the answer that are NOT supported by the chunks. Empty if the answer is fully supported.",
        },
    },
    "required": ["score", "unsupported_claims"],
}

FAITHFULNESS_JUDGE_PROMPT = """You are a strict fact-checking judge. You will be given a set of \
document chunks and an answer that was generated from them. Your job is to \
determine whether the answer is faithful to the chunks - i.e. whether every \
factual claim in the answer is actually supported by the text in the chunks.

Rules:
- Do NOT use outside knowledge. A claim is only "supported" if it is stated \
or directly implied by the chunks below, even if the claim is true in \
the real world.
- An honest "I don't have enough information" style answer is fully \
faithful (score 1.0, no unsupported claims) - it makes no unsupported claims.
- Score is the fraction of the answer's distinct factual claims that are \
supported (1.0 = fully supported, 0.0 = none of it is supported).
- List each unsupported claim as a short quote or close paraphrase from the \
answer. If fully supported, output an empty list.

DOCUMENT CHUNKS:
{context}

GENERATED ANSWER:
{answer}

Score the answer now."""


def _format_chunks_for_judge(context_chunks: List[Dict[str, Any]]) -> str:
    parts = []
    for idx, chunk in enumerate(context_chunks):
        source = chunk.get("source_file", "unknown")
        page = chunk.get("page_number", "?")
        text = (chunk.get("chunk_text") or "").strip()
        parts.append(f"--- CHUNK {idx + 1} (Source: {source}, Page: {page}) ---\n{text}")
    return "\n\n".join(parts)


def score_faithfulness(answer: str, context_chunks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Judges whether `answer` is faithful to `context_chunks` using a second,
    cheap Gemini call with a structured JSON schema output (so the score
    is reliably parseable, not free text that needs regex-scraping).

    Returns {"faithfulness_score": float, "unsupported_claims": List[str]},
    or None if the judge call fails/returns something unusable - callers
    should treat that as "faithfulness unknown for this response" rather
    than assume good or bad faith, since this is a best-effort enrichment
    step and must never break the main chat response.
    """
    if not answer or not answer.strip():
        return None
    if not context_chunks:
        # Nothing to check the answer against - can't judge faithfulness.
        return None

    context_text = _format_chunks_for_judge(context_chunks)
    prompt = FAITHFULNESS_JUDGE_PROMPT.format(context=context_text, answer=answer.strip())

    result = generate_structured_response(prompt, response_schema=FAITHFULNESS_RESPONSE_SCHEMA, max_tokens=500)
    if not isinstance(result, dict):
        return None

    score = result.get("score")
    unsupported_claims = result.get("unsupported_claims")

    if not isinstance(score, (int, float)):
        return None
    if not isinstance(unsupported_claims, list):
        unsupported_claims = []

    score = max(0.0, min(1.0, float(score)))
    unsupported_claims = [str(c).strip() for c in unsupported_claims if str(c).strip()]

    return {"faithfulness_score": round(score, 3), "unsupported_claims": unsupported_claims}
