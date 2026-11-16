# Evaluation

The retrieval pipeline is evaluated against a naive dense-retrieval baseline on a labeled dataset
(`docs/eval/eval_set.json`), Top-5 setting, source-file-level ground truth:

| Pipeline | Precision@5 | Recall@5 | MRR |
|:--|--:|--:|--:|
| Naive dense retrieval | 0.857 | 0.857 | 0.857 |
| **Advanced pipeline** | **0.893** (+4.2%) | **1.000** (+16.7%) | **0.905** (+5.6%) |

Every query is also scored for **answer faithfulness**: a second, cheap LLM call acts as a judge
given the generated answer and its cited chunks, returning a 0–1 support score plus any
unsupported claims (`src/evaluation/judge.py`) — this catches the case retrieval metrics can't: the
right document was found, but the answer still misstated what it says. Below
`FAITHFULNESS_GATE_THRESHOLD` (0.7), the generated answer is withheld entirely rather than returned
as-is — faithfulness is a hard gate, not just a reported score.

Full detail: [`eval/eval_report.md`](./eval/eval_report.md).

## System Numbers

Concrete, source-checked figures rather than vague claims — each one points at where it's enforced
or was measured:

| Metric | Value | Where |
|:--|--:|:--|
| Automated tests passing | **299 / 299** | `server/tests/` (`pytest`) |
| Retrieval confidence gate | 0.5 | `RETRIEVAL_CONFIDENCE_THRESHOLD`, `config.py` |
| Faithfulness hard gate | 0.7 | `FAITHFULNESS_GATE_THRESHOLD`, `config.py` |
| Max retrieval hops | 2 (initial + 1 bounded follow-up) | `MAX_HOPS`, `query_pipeline.py` |
| Chunk size / overlap | 200 / 40 tokens | `chunk_size_tokens` / `chunk_overlap_tokens`, `config.py` |
| Embedding dimensions | 1024 | `voyage-3.5`, `VOYAGE_EMBEDDING_DIMENSION` |
| Embedding concurrency speedup | ~4.6x (6 workers vs. sequential) | `EMBED_CONCURRENCY`, `ingestion/pipeline.py` |
| Scoped vs. full-corpus retrieval latency | ~2–5ms flat (5–10k+ chunks) vs. ~250ms at 10k chunks | `retrieval/hybrid.py`, [#27](../../../issues/27) |
| pgvector HNSW ANN query latency | ~5ms at 15k rows (Supabase mode) | `idx_chunks_embedding`, [#17](../../../issues/17) |
| Response cache | 0.97 cosine similarity match, 3600s TTL, 200 entries/scope cap | `response_cache.py` |
| Rate limits | 20 chat msgs / 5 uploads per 60s per user | `rate_limiter.py` |
| Conversation document cap | 5 documents per conversation | `ConversationCreate` schema |
| Upload size cap | 50MB per file | `document_service.py` |

## Hardening history

A ground-up hardening pass across 5 GitHub milestones (security/authz, faithfulness as a hard
gate, a real test suite, model routing/guardrails, ops hardening) is complete — the System Numbers
above are what that bought. Follow-up review rounds have surfaced further gaps since, all filed
and closed. See [milestones](../../../milestones) and [issues](../../../issues) for current status.
