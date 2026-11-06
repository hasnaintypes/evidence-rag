import logging
import time
import uuid
from contextlib import contextmanager
from typing import Dict, Optional

# --------------------------------------------------------------------------- #
# Stage-level tracing
#
# query_log (src/telemetry.py) already records a per-stage timing
# breakdown, but only as one row written at the very end of a successful
# or failed pipeline run - there's no way to see, from the outside, which
# stage a request is currently in, or which stage actually raised if the
# whole call blew up (api/routers/conversations.py's send_message_endpoint
# wraps process_chat_query() in one broad except, so today every failure
# looks identical from the logs: "An error occurred: <message>").
#
# This gives every call to process_chat_query() a short correlation id
# and emits one structured log line per stage (start, completion with
# elapsed ms, or failure with the exception) through Python's logging
# module - not print - via the "evidence_rag.pipeline" logger. That
# logger has no handlers of its own and propagates to the root logger, so
# it inherits whatever format/destination uvicorn (or any other process
# entry point - scripts/run_eval.py, scripts/ingest.py) already configured
# for the root logger, rather than fighting over handler setup here.
#
# No new DB table: the request_id is folded into the existing telemetry
# dict (see query_pipeline.py), so it's still persisted to query_log's
# telemetry_json for correlating a specific logged request with its
# stage-level log lines after the fact - stage timings themselves already
# have a home there; this module is what makes mid-request failures and
# container-log debugging possible, which query_log alone couldn't do.
# --------------------------------------------------------------------------- #

logger = logging.getLogger("evidence_rag.pipeline")


def new_request_id() -> str:
    """Short correlation id for one process_chat_query() call - 12 hex
    chars is enough to grep for in logs without the visual noise of a
    full UUID."""
    return uuid.uuid4().hex[:12]


@contextmanager
def traced_stage(
    request_id: str,
    stage: str,
    telemetry: Optional[Dict] = None,
    user_id: Optional[str] = None,
):
    """
    Wraps one pipeline stage: logs its start, then either its completion
    (with elapsed ms) or its failure (with the exception, before
    re-raising so the caller's own error handling is unaffected).

    When `telemetry` is given, also records `telemetry[f"{stage}_time_ms"]`
    on success - matching the key naming query_pipeline.py's phases
    already used before this module existed (e.g. "embedding_time_ms" for
    stage "embedding"), so this replaces the old manual
    time.perf_counter()/round() boilerplate without changing what ends up
    in query_log.
    """
    start = time.perf_counter()
    logger.info("stage_start request_id=%s stage=%s", request_id, stage)
    try:
        yield
    except Exception:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.error(
            "stage_failed request_id=%s stage=%s elapsed_ms=%s user_id=%s",
            request_id,
            stage,
            elapsed_ms,
            user_id,
            exc_info=True,
        )
        raise
    else:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        if telemetry is not None:
            telemetry[f"{stage}_time_ms"] = elapsed_ms
        logger.info(
            "stage_complete request_id=%s stage=%s elapsed_ms=%s",
            request_id,
            stage,
            elapsed_ms,
        )
