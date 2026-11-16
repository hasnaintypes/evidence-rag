from typing import Any, Dict

import structlog

from src.core.config import settings

# --------------------------------------------------------------------------- #
# End-of-request chat observability summary
#
# query_pipeline.py's `telemetry` dict already accumulates, over the
# course of one process_chat_query()/process_chat_query_stream() call:
# per-stage elapsed ms (observability.py's traced_stage(), keyed
# "<stage>_time_ms"), the response-cache hit flag, injection-pattern
# flags, and - via ai_tracker.py's track_ai_call(telemetry=...) - a list
# of every AI invocation made ("ai_calls"). build_request_summary()
# reduces that into the single structured line Phase 4 of the
# observability work asks for: total duration, AI invocations/attempts
# grouped by provider+operation, retries, fallbacks, cache hit/miss,
# token totals, per-stage breakdown, and the final outcome - logged
# exactly once per request (success, early-return, faithfulness-gated,
# cancelled, or failed - see query_pipeline.py's call sites), never per
# stage, so this never double-counts a nested span or a retry as a
# separate "request."
#
# total_duration_ms is the sum of every traced stage's elapsed_ms, not a
# separately-measured wall-clock span - today's pipeline stages run
# strictly sequentially (no stage overlaps another), so the sum already
# equals wall time to within logging overhead; if a future change makes
# stages genuinely concurrent, this approximation would need revisiting
# alongside the "Do not double-count ... parallel operations" note in
# the original observability request (doing a real wall-clock span now
# would require touching every call site that creates `telemetry` just
# to add one timestamp, for no benefit while nothing is actually
# parallel yet).
# --------------------------------------------------------------------------- #

logger = structlog.get_logger("evidence_rag.chat")


def build_request_summary(request_id: str, telemetry: Dict[str, Any], outcome: str) -> Dict[str, Any]:
    stage_breakdown = {k: v for k, v in telemetry.items() if k.endswith("_time_ms")}
    total_duration_ms = round(sum(stage_breakdown.values()), 1)

    ai_calls = telemetry.get("ai_calls", [])
    by_provider_operation: Dict[str, Dict[str, Any]] = {}
    total_attempts = 0
    total_retries = 0
    total_fallbacks = 0
    total_input_tokens = 0
    total_output_tokens = 0
    errors = 0

    for call in ai_calls:
        key = f"{call['provider']}:{call['operation']}"
        group = by_provider_operation.setdefault(key, {"count": 0, "attempts": 0, "errors": 0})
        group["count"] += 1
        group["attempts"] += call["attempts"]
        if call["outcome"] in ("error", "cancelled"):
            group["errors"] += 1
            errors += 1

        total_attempts += call["attempts"]
        if call["attempts"] > 1:
            total_retries += call["attempts"] - 1
        if call["is_fallback"]:
            total_fallbacks += 1
        total_input_tokens += call["input_tokens"] or 0
        total_output_tokens += call["output_tokens"] or 0

    return {
        "request_id": request_id,
        "outcome": outcome,
        "total_duration_ms": total_duration_ms,
        "stage_breakdown_ms": stage_breakdown,
        "ai_invocations": len(ai_calls),
        "ai_http_attempts": total_attempts,
        "ai_retries": total_retries,
        "ai_fallbacks": total_fallbacks,
        "ai_errors": errors,
        "ai_calls_by_provider_operation": by_provider_operation,
        "input_tokens": total_input_tokens or None,
        "output_tokens": total_output_tokens or None,
        "cache_hit": telemetry.get("cache_hit"),
        "injection_flags_count": len(telemetry.get("injection_flags", []) or []),
    }


def log_request_summary(summary: Dict[str, Any]) -> None:
    """Logs exactly one chat.request.* event per request, through the
    "evidence_rag.chat" logger - logging_config.py routes that logger to
    logs/chat/requests.jsonl. Gated by LOG_CHAT_SUMMARIES so a deployment
    that only wants per-stage/per-AI-call logs (not this aggregate line)
    can turn it off without touching LOG_LEVEL.

    chat_session_id is NOT a parameter here - it's bound via
    structlog.contextvars by api/services/conversation_service.py before
    process_chat_query()/process_chat_query_stream() is ever called (see
    that module), so it - and request_id/trace_id - are already merged
    into every log line emitted during this request, this one included,
    without query_pipeline.py having to know or pass a conversation id at
    all."""
    if not settings.log_chat_summaries:
        return

    outcome = summary["outcome"]
    event = {
        "success": "chat.request.completed",
        "early_return": "chat.request.completed",
        "faithfulness_gated": "chat.request.completed",
        "cache_hit": "chat.request.completed",
        "failed": "chat.request.failed",
        "cancelled": "chat.request.cancelled",
    }.get(outcome, "chat.request.completed")

    log_fn = logger.error if event == "chat.request.failed" else logger.info
    log_fn(event, **summary)
