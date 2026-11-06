import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# This file lives at server/src/core/config.py, so three levels up is the
# repo root - used to locate docs/ regardless of the process's cwd (the app
# is normally launched with cwd=server/, but docs/ lives one level above
# server/, so a plain relative path would look in the wrong place).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DOCS_DIR = os.path.join(_REPO_ROOT, "docs")
# docs/ is split into fixtures/ (the sample corpus) and eval/ (eval harness
# I/O) - see #19.
FIXTURES_DIR = os.path.join(DOCS_DIR, "fixtures")
EVAL_DIR = os.path.join(DOCS_DIR, "eval")
SAMPLE_DOCS_DIR = os.path.join(FIXTURES_DIR, "sample_docs")
EVAL_SET_PATH = os.path.join(EVAL_DIR, "eval_set.json")
EVAL_REPORT_PATH = os.path.join(EVAL_DIR, "eval_report.md")
# Machine-readable sibling of eval_report.md - CI diffs this against
# eval_baseline.json to catch retrieval/prompt regressions (see
# scripts/compare_eval.py and .github/workflows/eval.yml).
EVAL_METRICS_PATH = os.path.join(EVAL_DIR, "eval_metrics.json")
EVAL_BASELINE_PATH = os.path.join(EVAL_DIR, "eval_baseline.json")


class Settings(BaseSettings):
    # --- Storage backend switch: "local" (SQLite + local disk) or
    # "supabase" (Postgres+pgvector + Supabase Storage), see
    # src/storage/database.py ---
    storage_mode: str = "local"

    # --- App Settings ---
    app_name: str = "EvidenceRAG"
    top_k: int = 3
    chunk_size_tokens: int = 200
    chunk_overlap_tokens: int = 40
    # Comma-separated origins allowed to call this API from a browser (the
    # web/ Next.js dev server by default) - needed once the frontend sends
    # an Authorization header, since that requires an explicit CORS allowlist.
    cors_allowed_origins: str = "http://localhost:3000"

    # --- Generation Settings ---
    # NOTE: query_pipeline.py's prompt explicitly instructs "do not truncate"
    # for list/table synthesis answers, so this needs headroom - 500 was too
    # tight for multi-chunk technical answers and was silently cutting them off.
    generation_max_tokens: int = 1000
    generation_temperature: float = 0.3

    # --- Gemini (chat generation + embeddings) ---
    gemini_api_key: str
    gemini_chat_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    # Same-provider fallback used by generate_chat_response()/
    # generate_structured_response() (src/llm.py) when the primary chat
    # model's call fails or rate-limits - a different model is often on a
    # separate quota bucket, so this is a real mitigation for exactly the
    # failure this session hit while tuning #10's faithfulness threshold
    # (20-requests/day free-tier exhaustion), not just a theoretical one.
    # Not applied to embeddings - document_chunks.embedding is a fixed-
    # width pgvector column (vector(3072), matching gemini-embedding-001's
    # output dimension - see supabase_schema.sql's comment), so swapping
    # embedding models mid-request would produce a vector of the wrong
    # width for the already-indexed corpus. get_embedding() retries the
    # same model instead.
    gemini_fallback_chat_model: str = "gemini-2.5-flash-lite"

    # --- Entity graph (opt-in, adds one LLM call per document section) ---
    enable_entity_graph: bool = False

    # --- Retrieval-confidence abstention (advanced_mode only - naive mode
    # never computes a rerank_score, so it has no confidence signal to
    # gate on) ---
    # Minimum rerank_score the best retrieved chunk must clear, after
    # grading/compression/the follow-up hop, for the pipeline to attempt an
    # answer at all. Below this, process_chat_query() reports insufficient
    # evidence instead of generating a plausible-but-weakly-grounded
    # answer. rerank_score is a 0.0-1.0 Gemini-scored relevance value (see
    # retrieval/reranker.py's docstring) - matches retrieval/grader.py's
    # RERANK_SCORE_THRESHOLD (the same "more relevant than not" midpoint)
    # by default - tune against docs/eval/eval_set.json rather than hardcoding
    # a different number in code.
    retrieval_confidence_threshold: float = 0.5

    # --- Faithfulness hard gate (both modes - the judge call in
    # evaluation/judge.py doesn't depend on reranking, unlike the
    # retrieval-confidence gate above) ---
    # Below this score, process_chat_query() replaces the generated answer
    # with an explicit "did not pass the faithfulness check" flag instead
    # of returning it as-is - consistent with the retrieval-confidence
    # gate's "honest failure beats a plausible-but-wrong answer" policy.
    # score_faithfulness() scores by fraction of the answer's distinct
    # claims that are supported (see judge.py's prompt) - a probe against
    # real eval_set.json content (synthetic faithful/partially-hallucinated/
    # fully-hallucinated answers checked by the actual judge call, not
    # guessed) showed one unsupported claim out of two drops the score to
    # exactly 0.5, while a fully supported or honest-decline answer scores
    # 1.0. 0.7 sits below any observed good-answer score and above a
    # single-wrong-claim answer, erring toward flagging rather than
    # missing a hallucination. Full run_eval.py-based tuning across all of
    # docs/eval/eval_set.json (comparing gate firing against the known
    # negative-control/narrow-detail cases) is still open - it needs more
    # Gemini API quota than this probe could use without exhausting the
    # free tier's 20 requests/day, see GitHub issue #24. Revisit this
    # constant once that's run.
    faithfulness_gate_threshold: float = 0.7

    # --- Semantic response cache (src/response_cache.py) ----------------
    # Only consulted/populated for a conversation's first turn (no prior
    # history) and only for a fully-successful, non-gated result - see
    # response_cache.py's module docstring for why. In-memory/per-process,
    # not shared across workers.
    response_cache_enabled: bool = True
    # Cosine-similarity cutoff against a cached query's embedding for a
    # new query to count as "the same question" - 0.97 is deliberately
    # conservative (near-exact rewordings only), not tuned against a
    # labeled near-duplicate dataset. Err toward missing a cache hit
    # (falls through to a real pipeline run - same cost as today) rather
    # than serving an answer to a question that only superficially
    # resembles the cached one.
    response_cache_similarity_threshold: float = 0.97
    response_cache_ttl_seconds: int = 3600
    # Cap per (doc_ids, advanced_mode) scope, not a global cap - bounds
    # memory per scope regardless of how many distinct document sets
    # accumulate scopes over the process's lifetime.
    response_cache_max_entries_per_scope: int = 200

    # --- Per-user rate limiting (src/rate_limiter.py) --------------------
    # Guards the two routes that spend Gemini quota per call - chat
    # messages and uploads - against a single client exhausting the
    # app's quota through repeated requests. In-memory/per-process, not
    # shared across workers - see rate_limiter.py's module docstring.
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    # A chat turn costs several Gemini calls (query rewrite, embedding,
    # grading/compression, generation, faithfulness judging) - kept
    # tighter than upload's per-minute allowance for that reason.
    rate_limit_chat_max_requests: int = 20
    # An upload embeds one Gemini call per chunk, so a single large
    # document can already be a burst - the per-minute allowance here
    # limits how many separate uploads a user can kick off, not how many
    # chunks one upload embeds.
    rate_limit_upload_max_requests: int = 5

    # --- query_log retention (see scripts/purge_query_log.py) -----------
    # query_log stores raw query text indefinitely with no automatic
    # expiry today. Defaulted to 30 days as a reasonable starting policy -
    # this is a product decision, not just a code one, so revisit the
    # number itself; what matters structurally is that *some* bound
    # exists, not that 30 is the right number forever. Note this is only
    # enforced when scripts/purge_query_log.py is actually run - it is not
    # currently wired to any scheduler, so today it requires a manual run.
    query_log_retention_days: int = 30

    # --- Supabase (storage_mode="supabase") -----------------------------
    # supabase_db_url: direct Postgres connection string (Project Settings
    # -> Database -> Connection string), used by psycopg2 for the knowledge
    # tree / chunks / entities / query log.
    # supabase_url / supabase_key: project API URL + service key, used only
    # by the supabase-py client for Storage (raw uploaded files).
    supabase_db_url: Optional[str] = None
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None
    supabase_storage_bucket: str = "documents"

    # --- Signed source-citation links (see src/security.py) ---
    # GET /source/{filename} can't require an Authorization header (the
    # frontend opens it via plain <a href> navigation, which can't attach
    # one), so ownership is instead enforced via a short-lived signed JWT
    # embedded in the link. If unset, src/security.py falls back to a
    # random secret generated once per process start (fine for a single
    # process; set this explicitly in any multi-worker/multi-process
    # deployment, or every token-minting worker needs the same value).
    source_link_secret: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
