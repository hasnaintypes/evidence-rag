import json
import logging
import threading
import time
from typing import Dict, Any, Optional

from src.core.config import settings
from src.storage.database import get_db_connection

logger = logging.getLogger("evidence_rag.telemetry")

# --------------------------------------------------------------------------- #
# query_log retention sweep (#29)
#
# QUERY_LOG_RETENTION_DAYS (src/config.py) wasn't actually enforced until
# something calls scripts/purge_query_log.py, and nothing did - no cron, no
# scheduled GitHub Action, no pg_cron job. The right dedicated-scheduler
# mechanism depends on deployment specifics (a GitHub Action can reach a
# supabase-mode Postgres directly, but can't touch a local-mode SQLite
# file that only exists on whatever machine runs the server; that machine
# might not support cron either, e.g. Render's free web_service plan).
# Rather than hardcode one of those, this piggybacks the sweep on real
# request traffic - the same "check on every Nth real call instead of
# running a dedicated scheduler" pattern as rate_limiter.py's periodic
# sweep, gated by wall-clock time here (not call count) so it actually
# tracks "about once a day" regardless of traffic volume. In-memory/
# per-process state, same accepted limitation as the rate limiter/
# response cache/retrieval index cache elsewhere in this codebase - a
# process restart (e.g. Render's free-tier spin-down-on-idle) just means
# the next logged query re-triggers one, which is safe since
# purge_query_log() is idempotent either way.
# --------------------------------------------------------------------------- #

PURGE_CHECK_INTERVAL_SECONDS = 24 * 60 * 60

_purge_lock = threading.Lock()
_last_purge_attempt = 0.0


def _run_sweep() -> None:
    """The actual purge work, run off the request thread - see
    _maybe_run_retention_sweep()'s docstring for why. Never raises: a
    purge failure must not break the chat response whose request
    triggered it, but it is logged (not silently swallowed, per #29's
    acceptance criteria), unlike log_query_event()'s own insert failures
    above."""
    try:
        deleted = purge_query_log(settings.query_log_retention_days)
        if deleted:
            logger.info(
                "query_log retention sweep deleted %d row(s) older than %d days",
                deleted,
                settings.query_log_retention_days,
            )
    except Exception:
        logger.exception("query_log retention sweep failed")


def _maybe_run_retention_sweep() -> None:
    """Called at the end of every log_query_event() - a no-op unless at
    least PURGE_CHECK_INTERVAL_SECONDS have passed since the last attempt
    (successful or not).

    Dispatches the actual purge onto a background thread rather than
    running it inline: purge_query_log() deletes in batches of 1000,
    each its own get_db_connection()/DELETE/commit round trip, precisely
    because a first run (or any day with a large backlog) can mean
    clearing a lot of rows - see its own docstring. Running that
    synchronously inside log_query_event() would mean whichever real
    user's chat request happens to log the query that trips the daily
    gate pays that latency in their response time. A plain daemon
    thread, not FastAPI's BackgroundTasks, since log_query_event() is
    called from query_pipeline.py as a plain function, not from a route
    handler with a BackgroundTasks instance in scope."""
    global _last_purge_attempt
    now = time.time()
    with _purge_lock:
        if now - _last_purge_attempt < PURGE_CHECK_INTERVAL_SECONDS:
            return
        _last_purge_attempt = now

    threading.Thread(target=_run_sweep, daemon=True).start()


def reset_retention_sweep_state() -> None:
    """Test-only reset so one test's sweep doesn't suppress another's -
    same role as rate_limiter.py's clear_rate_limits()."""
    global _last_purge_attempt
    with _purge_lock:
        _last_purge_attempt = 0.0


# --------------------------------------------------------------------------- #
# Structured request logging
#
# Previously, telemetry was just an in-memory dict built manually inside
# rag_pipeline.py and returned to the UI - useful for the current request,
# but nothing was persisted. This adds a query_log table so past requests
# (latency per stage, chunk counts, hop counts, success/failure) can be
# inspected after the fact. Stage-level timing is now measured by
# src/observability.py's traced_stage() (also logs each stage's
# start/completion/failure under a per-request correlation id, not just
# this table's end-of-run row - see #16) - that module owns per-stage
# timing/tracing now, this one owns persisting the finished result.
# --------------------------------------------------------------------------- #


def init_telemetry_table() -> None:
    """Creates the query_log table if it doesn't exist. Safe to call on
    every startup alongside db.init_db(). No-op for storage_mode=supabase -
    query_log is created once by scripts/supabase_schema.sql instead."""
    if settings.storage_mode == "supabase":
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS query_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            query TEXT NOT NULL,
            advanced_mode INTEGER DEFAULT 1,
            hop_count INTEGER,
            chunk_count INTEGER,
            top_rerank_score REAL,
            generation_failed INTEGER DEFAULT 0,
            telemetry_json TEXT,
            faithfulness_score REAL,
            unsupported_claims_json TEXT,
            user_id TEXT
        )
    """)

    # Migration for query_log tables created before faithfulness scoring /
    # user_id were added - CREATE TABLE IF NOT EXISTS above is a no-op on
    # an existing table, so older DBs need these columns added explicitly.
    existing_columns = {row[1] for row in cursor.execute("PRAGMA table_info(query_log)").fetchall()}
    if "faithfulness_score" not in existing_columns:
        cursor.execute("ALTER TABLE query_log ADD COLUMN faithfulness_score REAL")
    if "unsupported_claims_json" not in existing_columns:
        cursor.execute("ALTER TABLE query_log ADD COLUMN unsupported_claims_json TEXT")
    if "user_id" not in existing_columns:
        cursor.execute("ALTER TABLE query_log ADD COLUMN user_id TEXT")

    # timestamp: scripts/purge_query_log.py's DELETE filters on this column
    # every run. user_id: for a future per-user export/delete query.
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_query_log_timestamp ON query_log(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_query_log_user ON query_log(user_id)")

    conn.commit()
    conn.close()


def log_query_event(
    query: str,
    telemetry: Dict[str, Any],
    advanced_mode: bool = True,
    hop_count: Optional[int] = None,
    chunk_count: Optional[int] = None,
    top_rerank_score: Optional[float] = None,
    generation_failed: bool = False,
    faithfulness_score: Optional[float] = None,
    unsupported_claims: Optional[list] = None,
    user_id: Optional[str] = None,
) -> None:
    """
    Persists one query's outcome to query_log. Called at the end of
    process_chat_query() so past requests can be inspected later
    (e.g. to spot queries that repeatedly fail generation, stages that
    are consistently slow, or answers that keep coming back unfaithful
    to their retrieved context) without needing external log aggregation.

    user_id ties a row to the caller (None for pipeline calls that don't
    have one, e.g. scripts/run_eval.py) - this is what retention/export
    tooling keys off (see scripts/purge_query_log.py and
    QUERY_LOG_RETENTION_DAYS in src/config.py).

    Failures here are swallowed rather than raised - telemetry logging
    must never break the actual chat response.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        unsupported_claims_json = json.dumps(unsupported_claims or [])
        if settings.storage_mode == "supabase":
            cursor.execute(
                """
                INSERT INTO query_log
                    (query, advanced_mode, hop_count, chunk_count, top_rerank_score, generation_failed,
                     telemetry_json, faithfulness_score, unsupported_claims_json, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    query,
                    int(advanced_mode),
                    hop_count,
                    chunk_count,
                    top_rerank_score,
                    int(generation_failed),
                    json.dumps(telemetry),
                    faithfulness_score,
                    unsupported_claims_json,
                    user_id,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO query_log
                    (query, advanced_mode, hop_count, chunk_count, top_rerank_score, generation_failed,
                     telemetry_json, faithfulness_score, unsupported_claims_json, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    query,
                    int(advanced_mode),
                    hop_count,
                    chunk_count,
                    top_rerank_score,
                    int(generation_failed),
                    json.dumps(telemetry),
                    faithfulness_score,
                    unsupported_claims_json,
                    user_id,
                ),
            )
        conn.commit()
        conn.close()
    except Exception:
        pass  # telemetry logging must never break the chat response

    _maybe_run_retention_sweep()


def get_recent_queries(limit: int = 50) -> list:
    """Returns the most recent logged queries - useful for a future
    admin/debug view or for run_eval.py to compare historical runs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = "%s" if settings.storage_mode == "supabase" else "?"
    cursor.execute(f"SELECT * FROM query_log ORDER BY timestamp DESC LIMIT {placeholder}", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def purge_query_log(retention_days: int, batch_size: int = 1000) -> int:
    """
    Deletes query_log rows older than retention_days (see
    QUERY_LOG_RETENTION_DAYS in src/config.py), in batches, and returns the
    total number deleted. Used by scripts/purge_query_log.py.

    retention_days must be positive: a non-positive value would otherwise
    produce opposite, both-wrong outcomes per backend - on Postgres,
    `now() - (0 || ' days')::interval` matches every row (wipes the whole
    table); on SQLite, `datetime('now', '-0 days')` or a malformed negative
    modifier either matches everything or silently matches nothing,
    depending on the exact string. Validating here means every caller gets
    the same protection, not just the one script that currently exists.

    Deletes in batches (DELETE ... WHERE id IN (SELECT ... LIMIT N), valid
    standard SQL on both backends - no DELETE...LIMIT extension needed)
    rather than one unbounded statement, since a first run after this
    shipped could be clearing months of backlog in one call; a single huge
    transaction would hold the row lock (and, on supabase, a connection
    from the bounded ThreadedConnectionPool) for an unpredictable amount
    of time against a table the live app is concurrently writing to.
    """
    if retention_days <= 0:
        raise ValueError(f"retention_days must be positive, got {retention_days}.")

    total_deleted = 0
    while True:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            if settings.storage_mode == "supabase":
                cursor.execute(
                    """
                    DELETE FROM query_log WHERE id IN (
                        SELECT id FROM query_log WHERE timestamp < now() - (%s || ' days')::interval LIMIT %s
                    )
                    """,
                    (retention_days, batch_size),
                )
            else:
                cursor.execute(
                    """
                    DELETE FROM query_log WHERE id IN (
                        SELECT id FROM query_log WHERE timestamp < datetime('now', ?) LIMIT ?
                    )
                    """,
                    (f"-{retention_days} days", batch_size),
                )
            deleted = cursor.rowcount
            conn.commit()
        finally:
            conn.close()

        total_deleted += deleted
        if deleted < batch_size:
            return total_deleted
