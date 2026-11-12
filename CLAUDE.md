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
cp .env.example .env            # set GEMINI_API_KEY, VOYAGE_API_KEY, STORAGE_MODE, SUPABASE_URL at minimum
python scripts/ingest.py        # index docs/fixtures/sample_docs/ as shared (user_id NULL) documents
uvicorn api.app:app --reload    # http://127.0.0.1:8000/docs for interactive API docs
```

```bash
pytest tests/ -v                    # auth, ownership/authz, and chat-pipeline failure-path tests -
                                     # everything mocked (no real Gemini/Supabase calls), isolated
                                     # temp SQLite DB per test (see tests/conftest.py)
python scripts/run_eval.py       # Precision@5 / Recall@5 / MRR / faithfulness over docs/eval/eval_set.json
python scripts/compare_eval.py   # diffs the fresh run against docs/eval/eval_baseline.json, writes server/eval_status.txt
python scripts/test_connection.py  # quick Gemini API connectivity check
python scripts/reset_data.py       # wipe local SQLite/file storage
python scripts/purge_query_log.py  # delete query_log rows older than QUERY_LOG_RETENTION_DAYS
                                    # (default 30) immediately/on demand - the same purge also runs
                                    # automatically (src/core/telemetry.py, gated to ~once/day on real
                                    # request traffic, see #29), so this script is for a forced run

ruff check .                        # lint (pyflakes rules only - see pyproject.toml)
ruff format .                       # format (format .--check to verify without writing)
```

CI (`.github/workflows/ci.yml`) runs `ruff check`/`ruff format --check` and the pytest suite above
on every PR/push, gating every merge - unlike the eval harness below, this isn't path-filtered,
since auth/authz/pipeline-failure-path correctness tests must gate regardless of which files
changed. `.github/workflows/eval.yml` runs the retrieval-quality eval harness, but only on
PRs/pushes touching `server/src/retrieval/**`, `server/src/ingestion/**`,
`server/src/query_pipeline.py`, or `docs/eval/eval_set.json`. It auto-commits `docs/eval/eval_baseline.json`
on merges to `main`. `tests/api/test_documents_upload.py`/`test_documents_status.py`/`test_graph.py`
cover the upload→background-ingestion→status flow and the entity graph (previously untested).

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
(`retrieval/hybrid.py`) → LLM-based reranking (`retrieval/reranker.py`, one batched call scoring every
candidate chunk's relevance 0.0-1.0 — not a locally-hosted cross-encoder; see that module's docstring
and #20) → relevance grading + Jaccard dedup (`retrieval/grader.py`) → context compression +
parent-section reconstruction (`retrieval/compression.py`) → an adaptive context budget (2/4/5 blocks
based on top score) → a **confidence gate**: below `RETRIEVAL_CONFIDENCE_THRESHOLD` the pipeline
abstains instead of generating, returning the closest chunks as `sources` with no synthesized claim →
if confident but a follow-up looks warranted, **one bounded additional retrieval hop** (never an
open-ended loop) → grounded generation (`generate_cloudflare_chat()`/`generate_cloudflare_chat_stream()`,
`server/src/core/llm.py`) → faithfulness scoring (`evaluation/judge.py`, a second cheap LLM call
checking the answer against its own cited chunks) → **faithfulness hard gate**: below
`FAITHFULNESS_GATE_THRESHOLD` the generated answer is withheld and replaced with an explicit "did not
pass the faithfulness check" message (still listing sources/unsupported claims) rather than returned
as-is → telemetry (`telemetry.py`) logs every stage's latency. The retrieval-confidence gate only runs
in "advanced mode" — naive mode skips reranking entirely and always attempts an answer — but the
faithfulness gate runs in both modes, since the judge call doesn't depend on reranking.

**Every LLM call in this flow — query rewriting, reranking, judging, and the final answer — runs on
Cloudflare Workers AI, not Gemini.** Gemini's free-tier quota repeatedly exhausted every candidate in
its own fallback chain during real use (both for the final answer and for the comparatively light
judge/reranker/title calls), so the whole active call surface moved to Cloudflare's free tier (300 RPM,
10,000 Neurons/day, no payment method required). The only code that still calls Gemini is `src/graph.py`'s
entity-graph extraction (**disabled by default** via `ENABLE_ENTITY_GRAPH` — see below) and
`scripts/test_connection.py`'s connectivity check; `GEMINI_API_KEY` is still a required setting but only
needs to be any non-empty placeholder string if entity graph stays off, since `google-genai`'s client
validates non-emptiness (not validity) at construction and the key is never sent to Google unless that
feature is turned on. `FAITHFULNESS_GATE_THRESHOLD` (default 0.7, see `config.py`) was set from a small
probe against real `docs/eval/eval_set.json` content rather than a full `run_eval.py` pass, due to the
free-tier quota limits that motivated this migration in the first place — revisit once issue #24 is
resolved.

Every stage above runs inside `src/core/observability.py`'s `traced_stage()`, which logs that stage's
start/completion (with elapsed ms)/failure through the standard `logging` module under a per-request
correlation id (`request_id`, generated once per `process_chat_query()` call and folded into
`telemetry`) — this is what makes "which stage failed/was slow for request X" answerable from
container logs, not just from the single row `query_log` gets at the end of a run (see #16).
That same row-write is also what enforces `QUERY_LOG_RETENTION_DAYS` in practice: `log_query_event()`
piggybacks a retention sweep (`purge_query_log()`) onto real request traffic, gated to roughly once a
day, rather than depending on an external scheduler whose right shape (cron, a scheduled GitHub
Action, `pg_cron`) depends on deployment specifics this project doesn't hardcode (#29).
`POST /conversations/{id}/messages` and `POST /upload` additionally sit behind
`src/core/rate_limiter.py`'s per-user sliding-window limiter (`api/deps.py`'s
`get_rate_limited_chat_user`/`get_rate_limited_upload_user`), so a single client can't exhaust the
app's Cloudflare quota through repeated requests (#15). Both are in-memory/per-process, same
limitation as `response_cache.py`/`hybrid.py`'s index cache below.

`src/core/llm.py` has three Cloudflare functions covering every active call path:
`generate_cloudflare_chat()`/`generate_cloudflare_chat_stream()` for free text (the final RAG answer,
query rewriting/decomposition) and `generate_cloudflare_json()` for JSON-shaped output (reranking,
judging, title generation). The latter has no server-enforced schema — Cloudflare's OpenAI-compatible
endpoint doesn't document reliable JSON-mode support across models — so the prompt itself asks for
JSON text and the response is parsed defensively (`_extract_json_block()`: the first balanced
`{...}`/`[...]` block, tolerant of stray text around it, `None` on any parse failure so the caller
degrades gracefully). All three share one call path (`_cloudflare_chat_completion()`) with a
process-local cooldown that activates on an HTTP 429 (honoring `Retry-After` when Cloudflare sends
one) and is cleared, not retried, until it expires — deliberately not a blind "retry every candidate
every time" loop, since this project watched exactly that pattern burn several minutes retrying two
already-exhausted Gemini models on every single call during a reingest. A transient (non-429) failure
gets a small number of retries with exponential backoff + jitter instead. Lazily configured (no error
at import time without credentials) so the rest of the app, including every test in this repo, boots
and runs without `CLOUDFLARE_ACCOUNT_ID`/`CLOUDFLARE_API_TOKEN` set — only an actual call raises, with
a specific "not configured" message, if they're missing.

The Gemini-backed functions above these (`generate_chat_response()`/`generate_structured_response()`)
still exist, walking a configured chat-model chain until one succeeds (`GEMINI_CHAT_MODEL`/
`GEMINI_FALLBACK_CHAT_MODEL`, or `GEMINI_CHAT_MODEL_CHAIN` for an arbitrary-length override —
`scripts/list_available_models.py` lists which model ids a given key can actually call right now,
filtered by name heuristic to exclude TTS/image/music/agent-product models), but only `src/graph.py`'s
entity-graph extraction (disabled by default) and `scripts/test_connection.py` call them.
Embedding calls retry the same model instead (no chain), since `document_chunks.embedding` is a
fixed-width pgvector column tied to one embedding model's output dimension.

Document chunks are untrusted content (any signed-in user can upload a document) that gets embedded
verbatim into the generation prompt — `src/core/guardrails.py`'s `scan_for_injection_patterns()` flags
(never blocks/strips) chunks matching common prompt-injection heuristics into
`telemetry["injection_flags"]`, and the generation prompt itself carries explicit
instruction-hierarchy framing telling the model to treat chunk content as data, never as
instructions. Treat both as partial, iterative defenses, not a one-shot fix — see issue #13.

`src/core/response_cache.py` caches a fully-successful pipeline result (never a generation failure or a
gated/abstained one) keyed by `(doc_ids, advanced_mode)` and matched by cosine similarity against the
query embedding, so a near-duplicate question can skip query rewriting, generation, and faithfulness
judging entirely. Only consulted/populated on a conversation's first turn (no prior `history`) — a
follow-up depends on prior turns, so caching it under the bare query embedding risks serving a
stale/wrong-context answer. In-memory/per-process, same as `retrieval/hybrid.py`'s index cache — not
shared across workers or persisted across a restart.

### Observability: structured logging, AI-call tracking, chat-request summaries

`src/core/logging_config.py` wraps the stdlib `logging` module (every existing
`logging.getLogger("evidence_rag.*")` call site — `observability.py`'s `traced_stage()`, `llm.py`,
`telemetry.py` — keeps working unchanged) with `structlog`, so every log line, old call sites and new
structured ones alike, renders as one JSON event: UTC ISO-8601 `timestamp`, `level`, `service`,
`environment`, `logger`, `event`, plus whatever structured fields a call site added. `LOG_FORMAT`
controls `console` (colorized, for local dev) vs `json` rendering; file output (`LOG_TO_FILE`) is
routed by logger name into `logs/application/app.jsonl` (everything else), `logs/ai/invocations.jsonl`
(`evidence_rag.ai`), `logs/chat/requests.jsonl` (`evidence_rag.chat`), and `logs/errors/errors.jsonl`
(a deliberate mirror of any ERROR+ line, from any category) — rotated via `concurrent-log-handler`
(safe across multiple OS processes, unlike stdlib's plain `RotatingFileHandler`) and swept for
rotated-backup age (`LOG_RETENTION_DAYS`) once at startup. `logs/` is gitignored; only its four
category `.gitkeep` files are committed.

`src/core/ai_tracker.py`'s `track_ai_call()` wraps every real AI/embedding call site in `llm.py`
(Voyage's `get_embedding()`/`get_embeddings_batch()`, the shared Cloudflare transport
`_cloudflare_chat_completion()` behind `generate_cloudflare_chat()`/`_stream()`/`_json()`, and the
dormant Gemini `generate_chat_response()`/`generate_structured_response()` chain) with one
`ai.invocation.*` event per *logical* call, tagged with an `operation` string each caller passes
explicitly (`"answer_generation"`, `"query_rewriting"`, `"reranking"`, `"faithfulness_judging"`,
`"title_generation"`, `"entity_extraction"`, `"document_ingestion"`, …) — this is what distinguishes
otherwise-identical-looking Cloudflare calls in the log. A separate `ai.http_attempt` event fires per
*actual* outbound HTTP attempt (every retry in `_cloudflare_chat_completion()`'s bounded backoff loop,
every candidate in the Gemini fallback chain), so "1 logical invocation → N HTTP attempts" is visible
instead of collapsed into a single pass/fail line. Token usage is only ever reported from a provider's
own response (`response.usage`) — never estimated or fabricated; Voyage's `embed()` doesn't return
token counts today, so embedding invocations simply omit the field. `summarize_messages()` is the only
thing ever logged about a request payload — message count/roles/char length/system-prompt presence,
never message content — so no raw prompt, document content, or credential ever reaches a log line.

`src/core/request_summary.py`'s `build_request_summary()`/`log_request_summary()` reduce one request's
accumulated `telemetry` dict (per-stage `traced_stage()` timings, `cache_hit`, `injection_flags`, and
the `ai_calls` list `track_ai_call(telemetry=...)` appends to) into exactly one `chat.request.*` event
— success, early-return (cache hit/empty retrieval/confidence-gate abstention), faithfulness-gated,
cancelled (SSE client disconnected mid-stream), or failed — logged once per `process_chat_query()`/
`process_chat_query_stream()` call, never per stage or per retry. `chat_session_id` is bound via
`structlog.contextvars.bound_contextvars()` in `api/services/conversation_service.py` around the
pipeline call, so it — and every AI invocation logged during that call — carries the conversation id
automatically without `query_pipeline.py` needing to know about conversations at all.

`scripts/inspect_logs.py` (`chats --last N`, `session <id>`, `request <id>`, `stats [--today]`,
`errors --last N [--verbose]`) reads the JSONL files directly — no new dependency — to answer "how
many AI calls did this chat message make, and why" without hand-grepping raw log lines.

**Production log export**: disabled by default. Setting `BETTER_STACK_SOURCE_TOKEN` adds a
`QueueHandler`/`QueueListener`-backed exporter (`logging_config.py`'s `_maybe_add_better_stack_handler()`)
that ships the same JSON lines to Better Stack's Logs ingestion endpoint on a background thread — a
request thread only ever enqueues a string, never waits on the network, and any export failure is
swallowed (never breaks a chat response). Better Stack was chosen over Grafana Cloud/Sentry for this
project's scale: free tier is 3GB logs/traces retained for 3 days (verify current numbers at
betterstack.com/pricing before relying on them — this was last checked 2026-11-12), no payment method
required to start, native structured-JSON ingestion, and a dashboard that needs no separate
OpenTelemetry Collector to stand up first. To enable: create a Logs source in the Better Stack
dashboard (Telemetry → Sources → Connect source), set `BETTER_STACK_SOURCE_TOKEN` to its token, and
redeploy — nothing else in the app changes.

### Storage is swappable, pipeline logic is not

`STORAGE_MODE` (`local` vs `supabase`) only changes `server/src/storage/{database,files}.py` — SQLite
vs. Postgres+pgvector for the DB, local disk vs. Supabase Storage for raw files. Parsing, chunking,
reranking, and the entity graph run identically regardless of backend. `documents.user_id`
is nullable: `NULL` means a shared/demo document visible to all signed-in users (the `docs/fixtures/sample_docs/`
corpus, indexed via `scripts/ingest.py`); non-null means a private upload via `POST /upload`, scoped to
that uploader. `make_doc_id(filename, user_id)` in `ingestion/pipeline.py` exists specifically so two
different users' same-named upload don't collide on one `doc_id`.

One exception to "pipeline logic is identical regardless of backend": `retrieval/hybrid.py`'s dense
(semantic) retrieval layer differs by `STORAGE_MODE`. In `local` mode it still computes cosine
similarity against an in-memory, L2-normalized embedding matrix built from the full corpus. In
`supabase` mode it instead calls `src/storage/database.py`'s `dense_ann_search()`, a real
approximate-nearest-neighbor SQL query against `document_chunks.embedding` that uses
`scripts/supabase_schema.sql`'s `idx_chunks_embedding` HNSW index (#17) — built on
`(embedding::halfvec(N))` with `halfvec_cosine_ops` (`N` = `VOYAGE_EMBEDDING_DIMENSION`, 1024 by
default), not on `embedding` directly, since pgvector's HNSW index caps at 2000 dimensions for the
plain `vector` type (`halfvec` raises that to 4000 — relevant if `N` is ever raised above 2000, e.g.
Voyage's `voyage-3-large` at 2048); every query against the index (including `dense_ann_search()`)
must apply the identical `::halfvec(N)` cast on both sides of `<=>`, or the planner silently falls
back to a full sequential scan instead of using the index. Embeddings are Voyage AI's (`get_embedding()`/
`get_embeddings_batch()` in `src/core/llm.py`, asymmetric `input_type="query"` vs `"document"`), kept
independent of chat generation (still Gemini) — swapping either provider doesn't require touching the
other, though an embedding-model/dimension change needs `scripts/supabase_schema.sql` re-applied and
every document reingested from scratch (`get_indexed_embedding_models()` in `database.py` exists to
flag exactly this kind of mismatch). `dense_ann_search()` also filters by `doc_ids` directly in SQL (`WHERE doc_id = ANY(...)`)
rather than post-filtering a full-corpus ranking. The sparse/BM25 layer is scoped the same way now
too (#27, closed): whenever `doc_ids` is given (every real chat request — conversations are always
scoped to 1-5 documents), `retrieval/hybrid.py` builds its BM25 index (and, in local/SQLite mode, the
dense matrix) from `database.py`'s `get_chunks_for_sparse_by_doc_ids()` (`WHERE doc_id IN (...)`)
instead of the full-corpus cache, so per-query latency/memory scales with the conversation's own
document set, not the total system-wide corpus. That scoped index is itself cached per doc_ids scope
(`_get_scoped_index()`, LRU-bounded) so a conversation's repeated turns against the same documents
don't rebuild it every message. The full-corpus cache (`_build_index()`/`_get_index()`) still exists
for the one remaining `doc_ids=None` caller, `scripts/run_eval.py`'s full-corpus eval search.

### Routers are thin; `api/services/` holds the logic; `api/authz.py` holds ownership checks

`api/routers/{documents,conversations,graph}.py` just parse the request and call into
`api/services/{document,conversation,graph}_service.py` — `DocumentService`, `ConversationService`,
`GraphService`. Each service method loads the resource, asserts ownership, then acts; routers no
longer touch `src/storage/database.py` or `src/ingestion`/`src/query_pipeline` directly (#18, applying
`02-Architecture.md`'s previously-proposed services layer).

Ownership checks themselves live in `api/authz.py` (`get_owned_document()`, `get_owned_conversation()`,
`get_owned_graph_scope()`), not scattered per-router — this is what the 2026-11-03 authz fixes (#22)
originally established ad hoc (`api/deps.py`'s `require_document_access()`,
`conversations.py`'s `_get_owned_conversation()`) and #18 centralized. Every one of them 404s (not 403s)
for a resource that doesn't exist or belongs to someone else (see `server/tests/api/test_authz.py` for
the unit-level coverage and `server/tests/api/test_ownership.py` for the integration-level cross-user
coverage).
`GET /source/{filename}` has no bearer-auth check (by design, for citation links — see
`DocumentService.resolve_source_path()`'s docstring), but is instead gated by a short-lived signed
token (`src/core/security.py`). A new resource-scoped route should add a service method that calls the
matching `api/authz.py` helper (adding one if the resource type is new) rather than trusting a
caller-supplied id directly.

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
vault at `~/Vaults/Main/Projects/EvidenceRAG/`, not in this repo. `docs/` here is split into
`docs/fixtures/` (the `sample_docs/` demo corpus) and `docs/eval/` (eval harness I/O —
`eval_set.json`, `eval_baseline.json`, `eval_report.md`, `eval_metrics.json`) — see GitHub issue #19
and `06-Roadmap.md` in the vault.
