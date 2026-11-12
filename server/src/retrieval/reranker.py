from typing import Any, Dict, List

from src.core.llm import generate_cloudflare_json

# --------------------------------------------------------------------------- #
# LLM-based reranking (Cloudflare Workers AI), replacing a locally-hosted
# cross-encoder
#
# This used to load sentence-transformers' CrossEncoder("BAAI/bge-reranker-base")
# in-process. That model's weights plus torch pushed the server's memory
# footprint past Render's free-tier 512MB limit - the process was getting
# OOM-killed during startup (before serving a single request) on every
# deploy from 2026-11-03 onward, confirmed via Render's deploy logs
# ("Out of memory (used over 512Mi)"). See GitHub issue #20.
#
# Rather than host a second (even if smaller) local model, this reuses
# whichever provider already backs every other LLM step in this
# pipeline (query rewriting, generation, faithfulness judging - all
# Cloudflare now, see src/core/llm.py's Cloudflare section docstring for
# why it replaced Gemini here) - for one batched relevance-scoring call
# per rerank_chunks() invocation, scoring every candidate chunk in a
# single request rather than one call per chunk. This removes sentence-
# transformers/torch from the dependency tree entirely.
#
# No server-enforced JSON schema (generate_cloudflare_json() - the
# prompt below asks for the exact {"scores": [...]} shape in text, then
# the response is regex/balanced-bracket parsed, same defensive handling
# generate_structured_response() used to make unnecessary on Gemini).
#
# Score scale changed from the old cross-encoder's raw logits
# (roughly -10..+10, clustering positive for relevant pairs) to a
# 0.0-1.0 relevance score, consistent with the rest of this pipeline's
# 0-1 conventions (e.g. evaluation/judge.py's faithfulness score).
# Every downstream threshold tuned to the old logit scale was
# recalibrated accordingly - see grader.py's RERANK_SCORE_THRESHOLD and
# query_pipeline.py's adaptive chunk-budget thresholds. Like
# FAITHFULNESS_GATE_THRESHOLD, these are a first-pass recalibration
# (reasoned from the new scale's semantics), not yet tuned against a full
# run_eval.py pass - revisit alongside #24 once free-tier quota allows it.
# --------------------------------------------------------------------------- #

RERANK_PROMPT = """You are scoring how relevant each document chunk is to a search query, for a \
retrieval pipeline deciding which chunks to keep. Score each chunk from 0.0 \
(not relevant / off-topic) to 1.0 (directly answers the query), based only on \
whether the chunk's content could help answer the query - not its writing \
style, length, or formatting.

QUERY:
{query}

CHUNKS:
{chunks_block}

Score every chunk listed above, one entry per chunk index - do not skip any.

Output ONLY a JSON object of this exact shape, no other text before or after it:
{{"scores": [{{"index": <1-based CHUNK number>, "relevance": <0.0-1.0>}}, ...]}}"""


def _format_chunks_for_scoring(chunks: List[Dict[str, Any]]) -> str:
    parts = []
    for idx, chunk in enumerate(chunks):
        text = (chunk.get("chunk_text") or "").strip()
        parts.append(f"--- CHUNK {idx + 1} ---\n{text}")
    return "\n\n".join(parts)


def rerank_chunks(query: str, chunks: List[Dict[str, Any]], top_n: int = 4) -> List[Dict[str, Any]]:
    """
    Re-scores and re-ranks retrieved chunks by relevance to `query`, via a
    single batched Cloudflare call (see module docstring for why this
    isn't a local cross-encoder anymore).

    On any failure (API error, malformed/incomplete JSON) every chunk
    falls back to a 0.0 relevance score - since Python's sort is stable,
    scoring everything identically preserves retrieval's original relative
    order rather than scrambling it, the same "degrade gracefully, never
    break the chat response" pattern every other best-effort enrichment in
    this pipeline follows (see e.g. evaluation/judge.py).  A chunk the
    model's response simply omits an entry for gets the same 0.0 fallback,
    rather than crashing on a missing index.
    """
    if not chunks:
        return []

    prompt = RERANK_PROMPT.format(query=query, chunks_block=_format_chunks_for_scoring(chunks))
    # Output is small per chunk (an int + a float), but a large fused
    # candidate set (several expanded query tracks x top_k each, deduped)
    # can still run to 20+ chunks - sized with headroom rather than the
    # ~500-800 token budget other JSON calls in this codebase use for a
    # handful of fields.
    result = generate_cloudflare_json(prompt, max_tokens=2000)

    scores_by_index: Dict[int, float] = {}
    if isinstance(result, dict) and isinstance(result.get("scores"), list):
        for entry in result["scores"]:
            if not isinstance(entry, dict):
                continue
            idx = entry.get("index")
            relevance = entry.get("relevance")
            if isinstance(idx, int) and isinstance(relevance, (int, float)):
                scores_by_index[idx] = max(0.0, min(1.0, float(relevance)))

    for position, chunk in enumerate(chunks):
        chunk["rerank_score"] = scores_by_index.get(position + 1, 0.0)

    reranked_chunks = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
    return reranked_chunks[:top_n]
