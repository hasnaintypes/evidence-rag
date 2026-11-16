import glob
import logging
import logging.handlers
import os
import queue
import sys
import time
import urllib.error
import urllib.request

import structlog

from src.core.config import settings

# --------------------------------------------------------------------------- #
# Structured logging foundation
#
# Previously this module set up a single plain-text StreamHandler on the
# root logger (see git history) - every "evidence_rag.*" logger (pipeline/
# llm/telemetry/api) just emitted "%(asctime)s %(levelname)s %(name)s:
# %(message)s" lines, unstructured and console-only, with no way to
# machine-parse a request's AI calls or correlate events across stages
# beyond grepping for a request_id substring.
#
# This keeps every existing `logging.getLogger("evidence_rag.xxx")` call
# site working completely unchanged (observability.py's traced_stage(),
# llm.py's model-routing warnings, telemetry.py, conversation_service.py)
# while routing their output through structlog's processor pipeline, so
# every log line - old call sites and new structured ones (ai_tracker.py,
# request_summary.py) alike - gets the same JSON shape: timestamp (UTC
# ISO-8601), level, service, environment, logger name, event, plus
# whatever structured fields a structlog-native call site added as
# kwargs. This is structlog's documented "wrap stdlib logging" recipe
# (https://www.structlog.org/en/stable/standard-library.html), not a
# second, competing logging system - stdlib `logging` is still what every
# call site above ultimately calls into.
#
# Category routing (logs/application, logs/ai, logs/chat, logs/errors -
# see Phase 5 of the observability work) is done by attaching a filter to
# each file handler that matches on logger name / level, not by having
# call sites decide where their own output goes - ai_tracker.py and
# request_summary.py just log through "evidence_rag.ai" / "evidence_rag.chat"
# loggers like any other module here, and this module decides where those
# land. logs/errors/errors.jsonl is a deliberate *mirror* (any ERROR+
# line, from any logger, also lands there) - every other category is
# mutually exclusive so a single event is never duplicated across two
# non-error files.
#
# Rotation uses concurrent-log-handler's ConcurrentRotatingFileHandler,
# not stdlib's RotatingFileHandler - the stdlib handler's rotation isn't
# safe across multiple OS processes writing the same file (a size check +
# rename race), which matters here even in dev (uvicorn --reload spawns a
# reloader + worker process pair) and would matter immediately if this
# app's single-process assumption (documented throughout this codebase -
# response_cache.py, rate_limiter.py, hybrid.py's index cache) ever
# changes to multiple workers.
# --------------------------------------------------------------------------- #

_configured = False

_SERVICE_NAME = "evidence-rag-api"


def _add_service_fields(logger, method_name, event_dict):
    event_dict["service"] = _SERVICE_NAME
    event_dict["environment"] = settings.environment
    return event_dict


def _logger_name_matches(name: str, prefix: str) -> bool:
    """`name` is `prefix` itself or one of its dotted children -
    `record.name.startswith(prefix)` alone would also match an unrelated
    sibling logger name that merely shares the prefix as a character
    sequence (e.g. a future "evidence_rag.aiops" logger matching
    "evidence_rag.ai")."""
    return name == prefix or name.startswith(prefix + ".")


class _LoggerNameFilter(logging.Filter):
    """Routes a file handler to only the logger names it owns, so
    structured AI-invocation/chat-summary events don't also duplicate
    into application/app.jsonl."""

    def __init__(self, prefixes):
        super().__init__()
        self._prefixes = tuple(prefixes)

    def filter(self, record: logging.LogRecord) -> bool:
        return any(_logger_name_matches(record.name, prefix) for prefix in self._prefixes)


class _ExcludeLoggerNameFilter(logging.Filter):
    def __init__(self, prefixes):
        super().__init__()
        self._prefixes = tuple(prefixes)

    def filter(self, record: logging.LogRecord) -> bool:
        return not any(_logger_name_matches(record.name, prefix) for prefix in self._prefixes)


def _build_formatter(renderer) -> logging.Formatter:
    """One ProcessorFormatter per handler, sharing the same
    foreign_pre_chain (so a plain stdlib logger.info() call - which never
    passes through structlog's own processor chain - still gets a
    timestamp/level/service/environment added before rendering) but with
    its own final renderer (JSON for files, optionally console-colored
    for stdout)."""
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            _add_service_fields,
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
    )


def _purge_old_logs(directory: str, retention_days: int) -> None:
    """Deletes rotated log files (the handler's own `.1`, `.2`, ... backups
    - never the live, currently-open file) older than retention_days.
    Run once at startup rather than on a timer/per-request sweep like
    telemetry.py's query_log purge: log file rotation is already bounded
    by LOG_MAX_FILE_SIZE_MB, so the failure mode this guards against
    (unbounded disk growth from backups nobody ever deletes) only
    compounds slowly across process restarts, not within one run."""
    cutoff = time.time() - (retention_days * 86400)
    for path in glob.glob(os.path.join(directory, "**", "*.jsonl.*"), recursive=True):
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass  # another process may be mid-rotation; never fatal to startup


def _make_file_handler(path: str, filter_: logging.Filter) -> logging.Handler:
    from concurrent_log_handler import ConcurrentRotatingFileHandler

    os.makedirs(os.path.dirname(path), exist_ok=True)
    handler = ConcurrentRotatingFileHandler(
        path,
        maxBytes=settings.log_max_file_size_mb * 1024 * 1024,
        backupCount=10,
    )
    handler.setFormatter(_build_formatter(structlog.processors.JSONRenderer()))
    handler.addFilter(filter_)
    return handler


def configure_logging() -> None:
    """Idempotent - safe to call from every entry point (the FastAPI app
    and every scripts/*.py CLI) without risking duplicate handlers/log
    lines if it ends up called more than once."""
    global _configured
    if _configured:
        return

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            _add_service_fields,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    root = logging.getLogger()
    root.setLevel(logging.WARNING)

    if settings.log_to_console:
        console_renderer = (
            structlog.dev.ConsoleRenderer() if settings.log_format == "console" else structlog.processors.JSONRenderer()
        )
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(_build_formatter(console_renderer))
        root.addHandler(console_handler)

    if settings.log_to_file:
        log_dir = settings.log_directory
        ai_prefixes = ("evidence_rag.ai",)
        chat_prefixes = ("evidence_rag.chat",)

        app_handler = _make_file_handler(
            os.path.join(log_dir, "application", "app.jsonl"),
            _ExcludeLoggerNameFilter(ai_prefixes + chat_prefixes),
        )
        ai_handler = _make_file_handler(
            os.path.join(log_dir, "ai", "invocations.jsonl"), _LoggerNameFilter(ai_prefixes)
        )
        chat_handler = _make_file_handler(
            os.path.join(log_dir, "chat", "requests.jsonl"), _LoggerNameFilter(chat_prefixes)
        )
        error_handler = _make_file_handler(os.path.join(log_dir, "errors", "errors.jsonl"), logging.Filter())
        error_handler.setLevel(logging.ERROR)  # deliberate mirror of any ERROR+ line, from any category

        for handler in (app_handler, ai_handler, chat_handler, error_handler):
            root.addHandler(handler)

        _purge_old_logs(log_dir, settings.log_retention_days)

    _maybe_add_better_stack_handler(root)

    logging.getLogger("evidence_rag").setLevel(settings.log_level.upper())

    _configured = True


class _BetterStackHTTPHandler(logging.Handler):
    """
    Ships one formatted JSON line per record to Better Stack's Logs HTTP
    ingestion endpoint (in.logs.betterstack.com by default - see
    settings.better_stack_ingesting_host) over plain urllib (stdlib only -
    no new HTTP client dependency for a feature that's off by default in
    every environment this app actually runs in today).

    Deliberately best-effort and single-attempt: a failed POST (network
    error, Better Stack outage, exceeded free-tier quota) is swallowed,
    never raised and never retried - "telemetry exporter failures do not
    break chat requests" (this task's own Phase 7 requirement) matters
    more here than not losing a line, since the local logs/*.jsonl files
    this module already writes are the durable copy either way.
    """

    def __init__(self, source_token: str, ingesting_host: str):
        super().__init__()
        self._source_token = source_token
        self._url = f"https://{ingesting_host}"

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = self.format(record).encode("utf-8")
            request = urllib.request.Request(
                self._url,
                data=payload,
                method="POST",
                headers={"Authorization": f"Bearer {self._source_token}", "Content-Type": "application/json"},
            )
            urllib.request.urlopen(request, timeout=2.0)
        except (urllib.error.URLError, OSError, ValueError):
            pass  # never break a chat request over a telemetry export failure


def _maybe_add_better_stack_handler(root: logging.Logger) -> None:
    """
    No-op unless BETTER_STACK_SOURCE_TOKEN is set - this app makes zero
    outbound calls to Better Stack otherwise, same "lazily configured,
    requires an explicit credential" posture as llm.py's LLM-endpoint
    client. When it IS set, the actual HTTP POST runs on a dedicated
    background thread (via logging.handlers.QueueHandler/QueueListener)
    rather than inline in emit() - a request thread only has to put a
    formatted string on an in-process queue, never wait on a network
    round trip to Better Stack, so an exporter slowdown or outage can't
    add latency to (or block) a real chat response.
    """
    if not settings.better_stack_source_token:
        return

    log_queue: "queue.Queue" = queue.Queue(-1)
    queue_handler = logging.handlers.QueueHandler(log_queue)
    queue_handler.setFormatter(_build_formatter(structlog.processors.JSONRenderer()))
    queue_handler.setLevel(logging.INFO)
    root.addHandler(queue_handler)

    http_handler = _BetterStackHTTPHandler(settings.better_stack_source_token, settings.better_stack_ingesting_host)
    # No separate formatter needed on http_handler - QueueListener passes
    # the already-formatted LogRecord through; set a passthrough format.
    http_handler.setFormatter(logging.Formatter("%(message)s"))
    listener = logging.handlers.QueueListener(log_queue, http_handler, respect_handler_level=True)
    listener.start()


def reset_logging_config_for_tests() -> None:
    """Test-only: clears the idempotency guard and removes handlers this
    module added, so a test can call configure_logging() again with
    different settings (e.g. a temp log_directory) without leaking
    handlers into the next test."""
    global _configured
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    _configured = False
