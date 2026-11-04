import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# This file lives at server/src/config.py, so two levels up is the repo
# root - used to locate docs/ regardless of the process's cwd (the app is
# normally launched with cwd=server/, but docs/ lives one level above
# server/, so a plain relative path would look in the wrong place).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS_DIR = os.path.join(_REPO_ROOT, "docs")
SAMPLE_DOCS_DIR = os.path.join(DOCS_DIR, "sample_docs")
EVAL_SET_PATH = os.path.join(DOCS_DIR, "eval_set.json")
EVAL_REPORT_PATH = os.path.join(DOCS_DIR, "eval_report.md")
# Machine-readable sibling of eval_report.md - CI diffs this against
# eval_baseline.json to catch retrieval/prompt regressions (see
# scripts/compare_eval.py and .github/workflows/eval.yml).
EVAL_METRICS_PATH = os.path.join(DOCS_DIR, "eval_metrics.json")
EVAL_BASELINE_PATH = os.path.join(DOCS_DIR, "eval_baseline.json")


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

    # --- Entity graph (opt-in, adds one LLM call per document section) ---
    enable_entity_graph: bool = False

    # --- Retrieval-confidence abstention (advanced_mode only - naive mode
    # never computes a cross-encoder rerank_score, so it has no confidence
    # signal to gate on) ---
    # Minimum rerank_score the best retrieved chunk must clear, after
    # grading/compression/the follow-up hop, for the pipeline to attempt an
    # answer at all. Below this, process_chat_query() reports insufficient
    # evidence instead of generating a plausible-but-weakly-grounded
    # answer. Matches retrieval/grader.py's RERANK_SCORE_THRESHOLD (the
    # same "positive score = relevant cluster" cutoff for this
    # cross-encoder) by default - tune against docs/eval_set.json rather
    # than hardcoding a different number in code.
    retrieval_confidence_threshold: float = 0.0

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
