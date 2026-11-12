import logging
import sys

from src.core.config import settings

# --------------------------------------------------------------------------- #
# Nothing in this app ever called logging.basicConfig()/dictConfig() - every
# "evidence_rag.*" logger (observability.py's stage tracing, llm.py's
# model-routing warnings, telemetry.py, conversation_service.py) just
# propagated to the root logger and relied on "whatever the process entry
# point already configured". In practice nothing did: uvicorn's own logging
# config (uvicorn.config.LOGGING_CONFIG) only sets up "uvicorn"/
# "uvicorn.error"/"uvicorn.access" with propagate=False, and never touches
# the root logger or its level. With no handler anywhere and root's default
# level (WARNING), every INFO-level call - including every stage_start/
# stage_complete line traced_stage() emits, which observability.py's own
# docstring claims makes "which stage failed/was slow for request X
# answerable from container logs" - was silently dropped. Only WARNING/
# ERROR calls surfaced at all, and only via logging.lastResort's bare
# stderr fallback with no timestamp/level/logger-name formatting.
#
# configure_logging() fixes that for every process entry point (the
# FastAPI app and every scripts/*.py CLI): one formatted StreamHandler on
# the root logger, with the "evidence_rag" logger tree's own level
# controlled by LOG_LEVEL (settings.log_level) independent of root's level,
# so raising app verbosity doesn't also unmute noisy third-party libraries.
# --------------------------------------------------------------------------- #

_configured = False


def configure_logging() -> None:
    """Idempotent - safe to call from every entry point without risking
    duplicate handlers/log lines if it ends up called more than once."""
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.addHandler(handler)

    logging.getLogger("evidence_rag").setLevel(settings.log_level.upper())

    _configured = True
