# Configuration Reference

Every setting the server reads (`server/src/core/config.py`'s `Settings`, loaded from
`server/.env`) and the three variables the web app reads at build/runtime
(`web/.env`). `server/.env.example` and `web/.env.example` are the actual templates to copy — this
page explains what each one does and groups settings that `.env.example`'s inline comments spread
across the file. A few constants mentioned below (`MAX_HOPS`, `EMBED_CONCURRENCY`,
`MAX_CONVERSATION_DOCS`) are **not** environment variables — they're hardcoded in the module that
uses them, called out here only so you don't go looking for an env var that doesn't exist.

## Storage

| Variable | Default | Notes |
|:--|:--|:--|
| `STORAGE_MODE` | `local` | `local` = SQLite + local disk. `supabase` = Postgres+pgvector + Supabase Storage. |
| `SUPABASE_DB_URL` | — | Direct Postgres connection string. Use the **pooler** string (port 6543) if your network has no IPv6 route — the direct `db.<ref>.supabase.co` host is IPv6-only on many projects. |
| `SUPABASE_URL` | — | Project API URL. Required regardless of `STORAGE_MODE` — Auth is always Supabase. |
| `SUPABASE_KEY` | — | Service key, used only for Storage (raw uploaded files) when `STORAGE_MODE=supabase`. |
| `SUPABASE_STORAGE_BUCKET` | `documents` | Bucket name for uploaded files in `supabase` mode. |

## LLM (chat generation, rewriting, reranking, judging, titling)

| Variable | Default | Notes |
|:--|:--|:--|
| `LLM_BASE_URL` | `""` | Base URL of an OpenAI-compatible Chat Completions server. Unset = these calls fail with a clear "not configured" error; the rest of the app still boots. |
| `LLM_API_KEY` | `""` | Key for that endpoint. |
| `LLM_MODEL` | `""` | Model id on that endpoint. |
| `LLM_GEMINI_THINKING_BUDGET` | `0` | Auto-applied **only** when `LLM_BASE_URL` points at `generativelanguage.googleapis.com` — caps Gemini 2.5's hidden "thinking" token spend, which otherwise eats into the same `max_tokens` budget as the visible answer. `0` disables thinking outright. |
| `GENERATION_MAX_TOKENS` | `1000` | Max tokens for the final generated answer. |
| `GENERATION_TEMPERATURE` | `0.3` | Sampling temperature for the final answer. |

See `docs/ARCHITECTURE.md` for why this is one configurable endpoint rather than a
provider-specific SDK call.

## Gemini (dormant unless the entity graph is on)

| Variable | Default | Notes |
|:--|:--|:--|
| `GEMINI_API_KEY` | *(required)* | Only needs to be **any non-empty string** if `ENABLE_ENTITY_GRAPH=false` — the `google-genai` client validates non-emptiness, not validity, at construction, and the key is never sent to Google unless entity graph is on. If `LLM_BASE_URL` points at Gemini's own OpenAI-compatible endpoint, reuse this same key there. |
| `GEMINI_CHAT_MODEL` | `gemini-2.5-flash` | Only used by the dormant native-SDK chain (`src/graph.py`, `scripts/test_connection.py`) — not the active `LLM_*` path above. |
| `GEMINI_FALLBACK_CHAT_MODEL` | `gemini-2.5-flash-lite` | Tried once if the primary model's call fails/rate-limits. Ignored if `GEMINI_CHAT_MODEL_CHAIN` is set. |
| `GEMINI_CHAT_MODEL_CHAIN` | `""` | Optional longer fallback chain, comma-separated, tried in order. Run `python scripts/list_available_models.py` to see which ids your key can actually call. |

## Voyage AI (embeddings)

| Variable | Default | Notes |
|:--|:--|:--|
| `VOYAGE_API_KEY` | — | From [dashboard.voyageai.com/api-keys](https://dashboard.voyageai.com/api-keys). |
| `VOYAGE_EMBEDDING_MODEL` | `voyage-3.5` | |
| `VOYAGE_EMBEDDING_DIMENSION` | `1024` | Must match the pgvector column width + HNSW index from `scripts/supabase_schema.sql` exactly. Changing this requires re-running that migration **and** reingesting every document from scratch. |

Embeddings are independent of the chat/LLM provider above — swapping one doesn't require touching
the other.

## Entity graph

| Variable | Default | Notes |
|:--|:--|:--|
| `ENABLE_ENTITY_GRAPH` | `false` | One Gemini call per document section during ingestion. Off by default — this was exhausting Gemini's free-tier quota and slowing ingestion down. Only turn it on if you specifically want the `/graph` visualization. |

## Retrieval & generation thresholds

| Variable | Default | Notes |
|:--|:--|:--|
| `TOP_K` | `3` | **Currently dead** — `query_pipeline.py` hardcodes its own retrieval width (`search_width = 8 if advanced_mode else 4`) instead of reading this setting. Listed here so nobody loses time tuning it expecting an effect. |
| `CHUNK_SIZE_TOKENS` | `200` | Target chunk size during ingestion. |
| `CHUNK_OVERLAP_TOKENS` | `40` | Overlap between adjacent chunks. |
| `RETRIEVAL_CONFIDENCE_THRESHOLD` | `0.5` | Advanced-mode only. Minimum rerank score the best chunk must clear before the pipeline attempts an answer at all. |
| `FAITHFULNESS_GATE_THRESHOLD` | `0.7` | Both modes. Below this LLM-as-judge score, the generated answer is withheld rather than returned as-is. |

## Response cache

In-memory/per-process — not shared across workers, not persisted across a restart.

| Variable | Default | Notes |
|:--|:--|:--|
| `RESPONSE_CACHE_ENABLED` | `true` | |
| `RESPONSE_CACHE_SIMILARITY_THRESHOLD` | `0.97` | Cosine similarity against the query embedding required for a cache hit. |
| `RESPONSE_CACHE_TTL_SECONDS` | `3600` | |
| `RESPONSE_CACHE_MAX_ENTRIES_PER_SCOPE` | `200` | Per `(doc_ids, advanced_mode)` scope. |

## Rate limiting

In-memory/per-process, per-user. Guards the two routes that spend LLM/embedding quota per call.

| Variable | Default | Notes |
|:--|:--|:--|
| `RATE_LIMIT_ENABLED` | `true` | |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | |
| `RATE_LIMIT_CHAT_MAX_REQUESTS` | `20` | `POST /conversations/{id}/messages`(`/stream`) |
| `RATE_LIMIT_UPLOAD_MAX_REQUESTS` | `5` | `POST /upload`, `POST /documents/{doc_id}/reingest` |

## Security

| Variable | Default | Notes |
|:--|:--|:--|
| `SOURCE_LINK_SECRET` | *(random per process)* | Signs the short-lived token `GET /source/{filename}` uses instead of a bearer token. A random per-process secret is fine for a single process; **set this explicitly** in any multi-worker/multi-process deployment, or every token-minting worker needs the same value or tokens minted by one won't validate on another. |

## Query log retention

| Variable | Default | Notes |
|:--|:--|:--|
| `QUERY_LOG_RETENTION_DAYS` | `30` | `purge_query_log()` runs automatically on real request traffic (gated to ~once/day); `scripts/purge_query_log.py` forces an immediate run. |

## CORS

| Variable | Default | Notes |
|:--|:--|:--|
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated origins allowed to call this API from a browser. |

## Logging & observability

See `docs/ARCHITECTURE.md`'s Observability section for the concepts; these are the knobs.

| Variable | Default | Notes |
|:--|:--|:--|
| `LOG_LEVEL` | `INFO` | Applies to the `evidence_rag` logger tree only; third-party loggers stay at `WARNING`. |
| `ENVIRONMENT` | `development` | Free-text label stamped on every log event — not used for branching logic. |
| `LOG_FORMAT` | `console` | `console` (colorized, human-readable) or `json` (what production should use). |
| `LOG_TO_CONSOLE` | `true` | |
| `LOG_TO_FILE` | `true` | |
| `LOG_DIRECTORY` | `./logs` | `logs/{application,ai,chat,errors}/*.jsonl`. Entirely gitignored. |
| `LOG_MAX_FILE_SIZE_MB` | `20` | Per-file rotation size. |
| `LOG_RETENTION_DAYS` | `7` | Rotated-backup age, swept once at startup. |
| `LOG_AI_INVOCATIONS` | `true` | Per-AI-call log (`logs/ai/invocations.jsonl`). |
| `LOG_CHAT_SUMMARIES` | `true` | One summary line per chat message (`logs/chat/requests.jsonl`). |
| `BETTER_STACK_SOURCE_TOKEN` | `""` | Unset = production log export disabled. Set to enable shipping logs to Better Stack — see `docs/ARCHITECTURE.md`. |
| `BETTER_STACK_INGESTING_HOST` | `in.logs.betterstack.com` | |

## Misc

| Variable | Default | Notes |
|:--|:--|:--|
| `APP_NAME` | `EvidenceRAG` | FastAPI app title, shown at `/docs`. |

## Hardcoded (not configurable via env)

| Constant | Value | Where |
|:--|:--|:--|
| `MAX_HOPS` | `2` | `query_pipeline.py` — initial retrieval pass + at most one follow-up hop. |
| `EMBED_CONCURRENCY` | `6` | `ingestion/pipeline.py` — parallel embedding batches during ingestion. |
| `MAX_CONVERSATION_DOCS` | `5` | `storage/database.py` — max documents attachable to one conversation. |
| `MAX_UPLOAD_SIZE_BYTES` | `50MB` | `api/services/document_service.py` — matches the Supabase bucket's own file size limit. |

## Web (`web/.env`)

| Variable | Notes |
|:--|:--|
| `NEXT_PUBLIC_API_URL` | Backend base URL (`http://127.0.0.1:8000` locally). |
| `NEXT_PUBLIC_SUPABASE_URL` | Same Supabase project as the server's `SUPABASE_URL`. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Anon key — safe to expose client-side by design. |
