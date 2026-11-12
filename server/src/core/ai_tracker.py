import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import structlog

from src.core.config import settings

# --------------------------------------------------------------------------- #
# AI invocation tracking
#
# Every real LLM/embedding call this app makes already runs through one of
# three functions in src/core/llm.py: get_embedding()/get_embeddings_batch()
# (Voyage), _cloudflare_chat_completion() (the shared transport behind
# generate_cloudflare_chat()/_stream()/_json() - query rewriting, reranking,
# judging, titling, the final answer), and generate_chat_response()/
# generate_structured_response() (Gemini, only src/graph.py's entity graph
# and scripts/test_connection.py). track_ai_call() wraps each of those call
# sites with one context manager that logs exactly one "ai.invocation.*"
# event per *logical* call, through the "evidence_rag.ai" logger -
# logging_config.py routes that logger to logs/ai/invocations.jsonl.
#
# "Logical invocation" vs "actual HTTP attempt" is a real distinction this
# app already has retry logic for: _cloudflare_chat_completion() loops up
# to CLOUDFLARE_MAX_TRANSIENT_RETRIES+1 times on a transient failure before
# giving up, and the Gemini functions walk a multi-model fallback chain.
# track_ai_call() yields an AICallSpan the caller marks every attempt on
# (log_attempt()) so one invocation_id can own several ai.http_attempt
# lines - never collapsed into a single "it worked" event that hides how
# many outbound requests actually happened.
#
# No token-usage field is ever invented here: callers only pass
# input_tokens/output_tokens when the provider's own response actually
# returned them (Cloudflare's OpenAI-compatible response.usage; Voyage's
# embed() does not return token counts today, so embedding invocations
# simply omit the field rather than estimate one).
# --------------------------------------------------------------------------- #

logger = structlog.get_logger("evidence_rag.ai")


def new_invocation_id() -> str:
    return uuid.uuid4().hex[:12]


def _log_ai_event(log_fn, event: str, **fields) -> None:
    """Gated by LOG_AI_INVOCATIONS - telemetry["ai_calls"] aggregation
    (what request_summary.py's chat.request.* line is built from) is
    never gated by this, only the per-call logs/ai/invocations.jsonl
    line itself, so turning this off loses call-by-call detail but not
    the end-of-request AI-usage summary."""
    if settings.log_ai_invocations:
        log_fn(event, **fields)


def summarize_messages(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    A safe-to-log stand-in for the actual request payload - message count,
    roles, and total character length, never the message content itself.
    Character length (not a token estimate) is reported honestly as
    `approx_input_chars`, not labeled as a token count, since only the
    provider's own response.usage is ever trusted as "tokens" (see this
    module's docstring).
    """
    return {
        "message_count": len(messages),
        "roles": [m.get("role", "unknown") for m in messages],
        "approx_input_chars": sum(len(m.get("content", "") or "") for m in messages),
        "has_system_prompt": any(m.get("role") == "system" for m in messages),
    }


class AICallSpan:
    """Mutable state for one logical AI invocation, returned by
    track_ai_call() for the caller to update before the `with` block
    exits. Everything set here ends up on the ai.invocation.completed/
    failed event and, if `telemetry` was passed to track_ai_call(), on
    telemetry["ai_calls"] for request_summary.py to aggregate."""

    def __init__(self, invocation_id: str, provider: str, model: str, operation: str, parent_stage: Optional[str]):
        self.invocation_id = invocation_id
        self.provider = provider
        self.model = model
        self.operation = operation
        self.parent_stage = parent_stage
        self.attempts = 0
        self.is_fallback = False
        self.http_status: Optional[int] = None
        self.error_category: Optional[str] = None
        self.input_tokens: Optional[int] = None
        self.output_tokens: Optional[int] = None
        self.rate_limit_remaining: Optional[str] = None
        self.request_summary: Optional[Dict[str, Any]] = None
        self.outcome = "success"

    def log_attempt(
        self,
        attempt: int,
        outcome: str,
        http_status: Optional[int] = None,
        error_category: Optional[str] = None,
    ) -> None:
        """One outbound HTTP attempt within this logical invocation -
        called for every retry iteration, not just the final one, so
        "1 invocation -> 3 HTTP attempts" is visible in the logs instead
        of collapsed into a single pass/fail line."""
        self.attempts = max(self.attempts, attempt)
        _log_ai_event(
            logger.info,
            "ai.http_attempt",
            invocation_id=self.invocation_id,
            provider=self.provider,
            model=self.model,
            operation=self.operation,
            attempt=attempt,
            outcome=outcome,
            http_status=http_status,
            error_category=error_category,
        )

    def record_tokens(self, input_tokens: Optional[int], output_tokens: Optional[int]) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def record_request(self, request_summary: Dict[str, Any]) -> None:
        self.request_summary = request_summary


@contextmanager
def track_ai_call(
    provider: str,
    model: str,
    operation: str,
    parent_stage: Optional[str] = None,
    request_id: Optional[str] = None,
    telemetry: Optional[Dict[str, Any]] = None,
):
    """
    Wraps one logical AI invocation (one get_embedding() call, one
    generate_cloudflare_chat() call, etc - regardless of how many HTTP
    attempts it takes underneath). Logs ai.invocation.started on entry and
    ai.invocation.completed/failed on exit (re-raising any exception
    unchanged), then - when `telemetry` is given - appends a summary dict
    to telemetry["ai_calls"] so request_summary.py can build the
    end-of-request AI-usage breakdown without re-deriving it from raw log
    lines.
    """
    span = AICallSpan(new_invocation_id(), provider, model, operation, parent_stage)
    start = time.perf_counter()
    _log_ai_event(
        logger.info,
        "ai.invocation.started",
        invocation_id=span.invocation_id,
        provider=provider,
        model=model,
        operation=operation,
        parent_stage=parent_stage,
        request_id=request_id,
    )
    try:
        yield span
    except GeneratorExit:
        # A streaming caller (generate_cloudflare_chat_stream()) whose
        # consumer disconnects mid-stream - the SSE client closed the
        # connection - unwinds this generator via GeneratorExit, not a
        # normal Exception. Logged as a distinct "cancelled" outcome
        # (not "error") so request_summary.py can tell a cancelled
        # streamed request apart from an actual provider failure.
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        _log_ai_event(
            logger.warning,
            "ai.invocation.cancelled",
            invocation_id=span.invocation_id,
            provider=provider,
            model=model,
            operation=operation,
            parent_stage=parent_stage,
            request_id=request_id,
            duration_ms=duration_ms,
            attempts=max(span.attempts, 1),
        )
        if telemetry is not None:
            span.outcome = "cancelled"
            telemetry.setdefault("ai_calls", []).append(_span_summary(span, duration_ms))
        raise
    except Exception as e:
        span.outcome = "error"
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        _log_ai_event(
            logger.error,
            "ai.invocation.failed",
            invocation_id=span.invocation_id,
            provider=provider,
            model=model,
            operation=operation,
            parent_stage=parent_stage,
            request_id=request_id,
            duration_ms=duration_ms,
            attempts=max(span.attempts, 1),
            is_fallback=span.is_fallback,
            http_status=span.http_status,
            error_category=span.error_category or type(e).__name__,
        )
        if telemetry is not None:
            telemetry.setdefault("ai_calls", []).append(_span_summary(span, duration_ms))
        raise
    else:
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        _log_ai_event(
            logger.info,
            "ai.invocation.completed",
            invocation_id=span.invocation_id,
            provider=provider,
            model=model,
            operation=operation,
            parent_stage=parent_stage,
            request_id=request_id,
            duration_ms=duration_ms,
            attempts=max(span.attempts, 1),
            is_fallback=span.is_fallback,
            outcome=span.outcome,
            input_tokens=span.input_tokens,
            output_tokens=span.output_tokens,
            request_summary=span.request_summary,
        )
        if telemetry is not None:
            telemetry.setdefault("ai_calls", []).append(_span_summary(span, duration_ms))


def _span_summary(span: AICallSpan, duration_ms: float) -> Dict[str, Any]:
    return {
        "invocation_id": span.invocation_id,
        "provider": span.provider,
        "model": span.model,
        "operation": span.operation,
        "parent_stage": span.parent_stage,
        "duration_ms": duration_ms,
        "attempts": max(span.attempts, 1),
        "is_fallback": span.is_fallback,
        "outcome": span.outcome,
        "input_tokens": span.input_tokens,
        "output_tokens": span.output_tokens,
    }


def log_cache_event(hit: bool, operation: str = "response_cache", request_id: Optional[str] = None) -> None:
    """A cache hit/miss is deliberately NOT an ai.invocation.* event - it
    cost nothing and invoked no provider - but still needs to be visible
    in the AI-usage log so request_summary.py (and inspect_logs.py stats)
    can report "N requests served from cache" distinctly from "N requests
    that made 0 AI calls for some other reason"."""
    _log_ai_event(logger.info, "ai.cache_hit" if hit else "ai.cache_miss", operation=operation, request_id=request_id)
