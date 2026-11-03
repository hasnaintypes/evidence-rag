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

There is no test suite (`pytest`/`httpx` are listed in `requirements.txt` but unused). The only
verification tooling is the retrieval eval harness:

```bash
python scripts/run_eval.py       # Precision@5 / Recall@5 / MRR / faithfulness over docs/eval_set.json
python scripts/compare_eval.py   # diffs the fresh run against docs/eval_baseline.json, writes server/eval_status.txt
python scripts/test_connection.py  # quick Gemini API connectivity check
python scripts/reset_data.py       # wipe local SQLite/file storage
python scripts/purge_query_log.py  # delete query_log rows older than QUERY_LOG_RETENTION_DAYS
                                    # (default 30) - run on a schedule in production, not ad hoc
ruff check .                        # lint (pyflakes rules only - see pyproject.toml)
ruff format .                       # format (format .--check to verify without writing)
```

CI (`.github/workflows/ci.yml`) runs `ruff check`/`ruff format --check`, gating every PR/push.
`.github/workflows/eval.yml` runs the eval harness above, but only on PRs/pushes touching
`server/src/retrieval/**`, `server/src/ingestion/**`, `server/src/query_pipeline.py`, or
`docs/eval_set.json`. It auto-commits `docs/eval_baseline.json` on merges to `main`.

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
against its own cited chunks) → telemetry (`telemetry.py`) logs every stage's latency. This gate only
runs in "advanced mode" — naive mode skips the cross-encoder entirely and always attempts an answer.
**Faithfulness score is currently advisory only** (logged/returned, not enforced as a gate) — do not
assume a low score blocks a response unless you've checked `query_pipeline.py` has changed.

### Storage is swappable, pipeline logic is not

`STORAGE_MODE` (`local` vs `supabase`) only changes `server/src/storage/{database,files}.py` — SQLite
vs. Postgres+pgvector for the DB, local disk vs. Supabase Storage for raw files. Parsing, chunking,
retrieval, reranking, and the entity graph run identically regardless of backend. `documents.user_id`
is nullable: `NULL` means a shared/demo document visible to all signed-in users (the `docs/sample_docs/`
corpus, indexed via `scripts/ingest.py`); non-null means a private upload via `POST /upload`, scoped to
that uploader. `make_doc_id(filename, user_id)` in `ingestion/pipeline.py` exists specifically so two
different users' same-named upload don't collide on one `doc_id`.

### Known gap: authorization is not fully route-scoped

Conversations are correctly scoped per-user, but `GET /documents/{id}/status`,
`GET /documents/{id}/events` (SSE), `GET /graph`, and `GET /graph/section/{id}` do not currently check
that the requesting user owns the referenced document — any authenticated caller can access another
user's document metadata by guessing an id. `GET /source/{filename}` has no auth check at all (by
design, for citation links, but currently with no mitigating control). Treat this as a known, tracked
issue rather than a precedent to follow in new routes — new routes should enforce per-user ownership.

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
