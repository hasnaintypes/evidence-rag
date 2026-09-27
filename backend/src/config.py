import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# This file lives at backend/src/config.py, so two levels up is the repo
# root - used to locate docs/ regardless of the process's cwd (the app is
# normally launched with cwd=backend/, but docs/ lives one level above
# backend/, so a plain relative path would look in the wrong place).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS_DIR = os.path.join(_REPO_ROOT, "docs")
SAMPLE_DOCS_DIR = os.path.join(DOCS_DIR, "sample_docs")
EVAL_SET_PATH = os.path.join(DOCS_DIR, "eval_set.json")
EVAL_REPORT_PATH = os.path.join(DOCS_DIR, "eval_report.md")


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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()