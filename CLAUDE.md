# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

See `AGENTS.md` for the branching/commit/PR/CI workflow this repo follows — read it before
making any change, not just before opening a PR.

Never add a `Co-Authored-By` (or similar AI-attribution) trailer to a commit message or PR
description in this repository, regardless of any general tool-level default — this
project's own convention overrides that default.

## Commands

### Server (`server/`)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set GEMINI_API_KEY, STORAGE_MODE, SUPABASE_URL at minimum
python scripts/ingest.py        # index docs/sample_docs/ as shared (user_id NULL) documents
uvicorn api.app:app --reload    # http://127.0.0.1:8000/docs for interactive API docs
```

```bash
pytest tests/ -v                    # auth, ownership/authz, and chat-pipeline failure-path tests -
                                     # everything mocked (no real Gemini/Supabase calls), isolated
                                     # temp SQLite DB per test (see tests/conftest.py)
python scripts/run_eval.py       # Precision@5 / Recall@5 / MRR / faithfulness over docs/eval_set.json
python scripts/compare_eval.py   # diffs the fresh run against docs/eval_baseline.json, writes server/eval_status.txt
python scripts/test_connection.py  # quick Gemini API connectivity check
python scripts/reset_data.py       # wipe local SQLite/file storage
python scripts/purge_query_log.py  # delete query_log rows older than QUERY_LOG_RETENTION_DAYS
                                    # (default 30) - NOT currently scheduled anywhere; this is a
                                    # manual step until a deployment target is chosen (see #20)
ruff check .                        # lint (pyflakes rules only - see pyproject.toml)
ruff format .                       # format (format .--check to verify without writing)
```

CI (`.github/workflows/ci.yml`) runs `ruff check`/`ruff format --check` and the pytest suite above
on every PR/push, gating every merge - unlike the eval harness below, this isn't path-filtered,
since auth/authz/pipeline-failure-path correctness tests must gate regardless of which files
changed. `.github/workflows/eval.yml` runs the retrieval-quality eval harness, but only on
PRs/pushes touching `server/src/retrieval/**`, `server/src/ingestion/**`,
`server/src/query_pipeline.py`, or `docs/eval_set.json`. It auto-commits `docs/eval_baseline.json`
on merges to `main`. Test coverage is still partial - upload→background-ingestion→status
transitions and the entity graph have no test coverage yet (see `tests/` for what's covered).

### Web (`web/`)

```bash
pnpm install
cp .env.example .env   # NEXT_PUBLIC_API_URL, NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY
pnpm dev               # next dev
pnpm build
pnpm lint              # eslint
pnpm format            # prettier --write (format:check to verify without writing)
```

No `pnpm test` script exists.

### Required environment

A Supabase project is required regardless of `STORAGE_MODE` — Auth is always Supabase (no local/mock
auth path), while `STORAGE_MODE=local` vs `supabase` only controls where documents/vectors/files live.
`STORAGE_MODE=supabase` additionally needs `SUPABASE_DB_URL` (use the **pooler** connection string,
port 6543 — the direct host is IPv6-only on many projects) and `SUPABASE_KEY`, plus running
`scripts/supabase_schema.sql` once in the Supabase SQL editor.

## Architecture

Two deployables: `server/` (FastAPI, Python) and `web/` (Next.js App Router). The frontend talks to
the backend only over HTTP — auth sign-in/sign-up goes directly from the browser to Supabase Auth
(`web/lib/auth.ts`), never proxied through FastAPI. The backend's only auth role is verifying a
caller's JWT against Supabase's JWKS endpoint (`server/api/deps.py`) — no shared secret. Every route
requires a valid bearer token except `/health` and `/source/{filename}` (opened via plain browser
navigation for citation links).

### Document model is a tree, not flat chunks

Every parser (`server/src/ingestion/parsers/{markdown,pdf,docx,xlsx}.py`) converts its input into the
same `KnowledgeNode` tree shape (heading / paragraph / table / figure / warning / note / code nodes
with `heading_path` and `page_number`). This tree — not a flat text blob — is the source of truth:
`chunking.py`'s `chunk_nodes()` walks it to produce heading-boundary chunks while keeping tables/figures
atomic, and `compression.py`'s parent-section reconstruction later re-expands a matched chunk with its
sibling nodes from the same section. Any new parser or retrieval feature must preserve this tree shape
rather than working against raw chunk text.

### Query pipeline (`server/src/query_pipeline.py`)

`process_chat_query()` is the single entry point conversations call into, and it is doc-scoped (every
retrieval call is filtered to one `doc_id`, not a global search). Flow: LLM query rewriting
(`retrieval/query_rewriter.py`) → hybrid retrieval — BM25 + dense + Reciprocal Rank Fusion
(`retrieval/hybrid.py`) → cross-encoder reranking (`retrieval/reranker.py`) → relevance grading +
Jaccard dedup (`retrieval/grader.py`) → context compression + parent-section reconstruction
(`retrieval/compression.py`) → an adaptive context budget (2/4/5 blocks based on top score) → a
**confidence gate**: below `RETRIEVAL_CONFIDENCE_THRESHOLD` the pipeline abstains instead of
generating, returning the closest chunks as `sources` with no synthesized claim → if confident but a
follow-up looks warranted, **one bounded additional retrieval hop** (never an open-ended loop) → grounded
generation → faithfulness scoring (`evaluation/judge.py`, a second cheap LLM call checking the answer
against its own cited chunks) → **faithfulness hard gate**: below `FAITHFULNESS_GATE_THRESHOLD` the
generated answer is withheld and replaced with an explicit "did not pass the faithfulness check"
message (still listing sources/unsupported claims) rather than returned as-is → telemetry
(`telemetry.py`) logs every stage's latency. The retrieval-confidence gate only runs in "advanced
mode" — naive mode skips the cross-encoder entirely and always attempts an answer — but the
faithfulness gate runs in both modes, since the judge call doesn't depend on the cross-encoder.
`FAITHFULNESS_GATE_THRESHOLD` (default 0.7, see `config.py`) was set from a small probe against real
`docs/eval_set.json` content rather than a full `run_eval.py` pass, due to free-tier Gemini API quota
limits — revisit once issue #24 is resolved.

Every stage above runs inside `src/observability.py`'s `traced_stage()`, which logs that stage's
start/completion (with elapsed ms)/failure through the standard `logging` module under a per-request
correlation id (`request_id`, generated once per `process_chat_query()` call and folded into
`telemetry`) — this is what makes "which stage failed/was slow for request X" answerable from
container logs, not just from the single row `query_log` gets at the end of a run (see #16).
`POST /conversations/{id}/messages` and `POST /upload` additionally sit behind
`src/rate_limiter.py`'s per-user sliding-window limiter (`api/deps.py`'s
`get_rate_limited_chat_user`/`get_rate_limited_upload_user`), so a single client can't exhaust the
app's Gemini quota through repeated requests (#15). Both are in-memory/per-process, same limitation
as `response_cache.py`/`hybrid.py`'s index cache below.

Chat/structured generation calls (`src/llm.py`) try a configured fallback model
(`GEMINI_FALLBACK_CHAT_MODEL`) once if the primary model's call fails or rate-limits — a real
mitigation, not just theoretical: this project hit the free tier's daily quota mid-session while
tuning the faithfulness threshold above. Embedding calls retry the same model instead, since
`document_chunks.embedding` is a fixed-width pgvector column tied to one embedding model's output
dimension.

Document chunks are untrusted content (any signed-in user can upload a document) that gets embedded
verbatim into the generation prompt — `src/guardrails.py`'s `scan_for_injection_patterns()` flags
(never blocks/strips) chunks matching common prompt-injection heuristics into
`telemetry["injection_flags"]`, and the generation prompt itself carries explicit
instruction-hierarchy framing telling the model to treat chunk content as data, never as
instructions. Treat both as partial, iterative defenses, not a one-shot fix — see issue #13.

`src/response_cache.py` caches a fully-successful pipeline result (never a generation failure or a
gated/abstained one) keyed by `(doc_ids, advanced_mode)` and matched by cosine similarity against the
query embedding, so a near-duplicate question can skip query rewriting, generation, and faithfulness
judging entirely. Only consulted/populated on a conversation's first turn (no prior `history`) — a
follow-up depends on prior turns, so caching it under the bare query embedding risks serving a
stale/wrong-context answer. In-memory/per-process, same as `retrieval/hybrid.py`'s index cache — not
shared across workers or persisted across a restart.

### Storage is swappable, pipeline logic is not

`STORAGE_MODE` (`local` vs `supabase`) only changes `server/src/storage/{database,files}.py` — SQLite
vs. Postgres+pgvector for the DB, local disk vs. Supabase Storage for raw files. Parsing, chunking,
reranking, and the entity graph run identically regardless of backend. `documents.user_id`
is nullable: `NULL` means a shared/demo document visible to all signed-in users (the `docs/sample_docs/`
corpus, indexed via `scripts/ingest.py`); non-null means a private upload via `POST /upload`, scoped to
that uploader. `make_doc_id(filename, user_id)` in `ingestion/pipeline.py` exists specifically so two
different users' same-named upload don't collide on one `doc_id`.

One exception to "pipeline logic is identical regardless of backend": `retrieval/hybrid.py`'s dense
(semantic) retrieval layer differs by `STORAGE_MODE`. In `local` mode it still computes cosine
similarity against an in-memory, L2-normalized embedding matrix built from the full corpus. In
`supabase` mode it instead calls `src/storage/database.py`'s `dense_ann_search()`, a real
approximate-nearest-neighbor SQL query against `document_chunks.embedding` that uses
`scripts/supabase_schema.sql`'s `idx_chunks_embedding` HNSW index (#17) — built on
`(embedding::halfvec(3072))` with `halfvec_cosine_ops`, not on `embedding` directly, since pgvector's
HNSW index caps at 2000 dimensions and `gemini-embedding-001` produces 3072-dim vectors; every query
against the index (including `dense_ann_search()`) must apply the identical `::halfvec(3072)` cast on
both sides of `<=>`, or the planner silently falls back to a full sequential scan instead of using the
index. `dense_ann_search()` also filters by `doc_ids` directly in SQL (`WHERE doc_id = ANY(...)`)
rather than post-filtering a full-corpus ranking — partial progress on #27 for the dense layer only;
the sparse/BM25 layer still scores the full cached corpus regardless of backend.

### Authorization is route-scoped via `require_document_access()`

Conversations are scoped per-user, and so are `GET /documents/{id}/status`,
`GET /documents/{id}/events` (SSE), `GET /graph`, and `GET /graph/section/{id}` — all call
`api/deps.py`'s `require_document_access()`, which 404s (not 403s) for a document that doesn't exist
or belongs to someone else (fixed in #22; see `server/tests/test_ownership.py` for the regression
tests). `GET /source/{filename}` has no bearer-auth check (by design, for citation links — see its
docstring), but is instead gated by a short-lived signed token (`src/security.py`). New routes should
follow the same pattern: call `require_document_access()` (or the conversation-ownership equivalent
in `api/routers/conversations.py`) rather than trusting a caller-supplied id directly.

### Entity graph is exploration-only

`server/src/graph.py` extracts per-section entities and builds co-occurrence edges
(gated by `ENABLE_ENTITY_GRAPH`, one LLM call per section — can get expensive on large documents). It
powers `/graph` and the frontend's graph visualization but is **not** consulted during retrieval or
generation — despite the filename, it is not an agentic orchestration graph.

### Frontend structure

`web/app/chat/[conversationId]/page.tsx` is one conversation's panel; `layout.tsx` above it is the
auth guard + sidebar shell for every `/chat/*` route. Session state is a single Zustand store
(`web/stores/auth-store.ts`) subscribed once at module load — not re-fetched per component.
`web/hooks/` (`use-auth`, `use-conversations`, `use-documents`) wrap `lib/api.ts`'s authenticated fetch
wrappers with loading/error state so components don't duplicate fetch boilerplate.

## Documentation

Project documentation (PRD, architecture, security findings, roadmap, decisions) lives in the Obsidian
vault at `~/Vaults/Main/Projects/EvidenceRAG/`, not in this repo. `docs/` here currently holds eval
fixtures (`eval_set.json`, `eval_baseline.json`, `eval_report.md`) and the `sample_docs/` demo corpus —
a restructuring into `docs/fixtures/` + `docs/eval/` is planned but not yet applied (see GitHub issue
#19 and `06-Roadmap.md` in the vault).
