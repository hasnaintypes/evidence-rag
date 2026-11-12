from typing import Any, Dict, List, Optional

from src.core.llm import generate_cloudflare_json

# --------------------------------------------------------------------------- #
# Answer faithfulness scoring (LLM-as-judge)
#
# Retrieval metrics (Precision@K/Recall@K/MRR, see scripts/run_eval.py) only
# say whether the right chunks were *retrieved* - they say nothing about
# whether the *generated answer* actually sticks to what those chunks say.
# A system can retrieve the correct source and still hallucinate or
# misstate it. This module runs a second, cheap Cloudflare call as a judge:
# given the generated answer and the exact chunks it was allowed to use,
# score whether every claim in the answer is supported by them. No server-
# enforced JSON schema here (see src/core/llm.py's generate_cloudflare_json()
# docstring) - the prompt below asks for the exact {score, unsupported_claims}
# shape in text instead.
# --------------------------------------------------------------------------- #

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

Score the answer now. Output ONLY a JSON object of this exact shape, no \
other text before or after it:
{{"score": <0.0-1.0>, "unsupported_claims": [<short quotes/paraphrases of unsupported claims, empty list if fully supported>]}}"""


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
    cheap Cloudflare call, with the JSON shape asked for in the prompt and
    parsed defensively (see generate_cloudflare_json()'s docstring).

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

    result = generate_cloudflare_json(prompt, max_tokens=500)
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
