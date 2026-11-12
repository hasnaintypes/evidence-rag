"""
Unit tests for src/core/logging_config.py - JSON rendering, per-category
file routing, and the error-mirror behavior. Uses a temp LOG_DIRECTORY
and resets the module's idempotency guard around each test so these
don't leak handlers into the rest of the suite (see conftest.py's other
autouse fixtures for the same leak-prevention pattern).
"""

import json
import logging
import os

import pytest
import structlog

from src.core.config import settings
from src.core.logging_config import configure_logging, reset_logging_config_for_tests


@pytest.fixture(autouse=True)
def _reset_logging(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "log_directory", str(tmp_path / "logs"))
    monkeypatch.setattr(settings, "log_to_console", False)
    monkeypatch.setattr(settings, "log_to_file", True)
    monkeypatch.setattr(settings, "log_format", "json")
    reset_logging_config_for_tests()
    yield
    reset_logging_config_for_tests()


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_configure_logging_creates_the_category_directories():
    configure_logging()
    for category in ("application", "ai", "chat", "errors"):
        assert os.path.isdir(os.path.join(settings.log_directory, category))


def test_a_structured_event_is_valid_json_with_required_fields():
    configure_logging()
    structlog.get_logger("evidence_rag.ai").info("ai.invocation.started", provider="cloudflare", model="m")

    rows = _read_jsonl(os.path.join(settings.log_directory, "ai", "invocations.jsonl"))
    assert len(rows) == 1
    row = rows[0]
    assert row["event"] == "ai.invocation.started"
    assert row["level"] == "info"
    assert row["service"] == "evidence-rag-api"
    assert "timestamp" in row
    assert row["provider"] == "cloudflare"


def test_a_plain_stdlib_logger_call_is_also_rendered_as_json():
    configure_logging()
    logging.getLogger("evidence_rag.llm").warning("plain message %s", "value")

    rows = _read_jsonl(os.path.join(settings.log_directory, "application", "app.jsonl"))
    assert len(rows) == 1
    assert "plain message value" in rows[0]["event"]
    assert rows[0]["level"] == "warning"


def test_ai_events_land_only_in_the_ai_file_not_application():
    configure_logging()
    structlog.get_logger("evidence_rag.ai").info("ai.invocation.started", provider="cloudflare")

    assert len(_read_jsonl(os.path.join(settings.log_directory, "ai", "invocations.jsonl"))) == 1
    assert len(_read_jsonl(os.path.join(settings.log_directory, "application", "app.jsonl"))) == 0


def test_chat_events_land_only_in_the_chat_file_not_application():
    configure_logging()
    structlog.get_logger("evidence_rag.chat").info("chat.request.completed", outcome="success")

    assert len(_read_jsonl(os.path.join(settings.log_directory, "chat", "requests.jsonl"))) == 1
    assert len(_read_jsonl(os.path.join(settings.log_directory, "application", "app.jsonl"))) == 0


def test_an_error_from_any_logger_is_mirrored_into_errors_jsonl():
    configure_logging()
    structlog.get_logger("evidence_rag.ai").error("ai.invocation.failed", provider="cloudflare")

    ai_rows = _read_jsonl(os.path.join(settings.log_directory, "ai", "invocations.jsonl"))
    error_rows = _read_jsonl(os.path.join(settings.log_directory, "errors", "errors.jsonl"))
    assert len(ai_rows) == 1
    assert len(error_rows) == 1  # same event, deliberately duplicated into the error mirror
    assert error_rows[0]["event"] == "ai.invocation.failed"


def test_an_info_level_event_is_not_mirrored_into_errors_jsonl():
    configure_logging()
    structlog.get_logger("evidence_rag.ai").info("ai.invocation.started", provider="cloudflare")

    error_rows = _read_jsonl(os.path.join(settings.log_directory, "errors", "errors.jsonl"))
    assert error_rows == []


def test_configure_logging_is_idempotent():
    configure_logging()
    configure_logging()  # must not add a second set of handlers
    structlog.get_logger("evidence_rag.ai").info("ai.invocation.started", provider="cloudflare")

    rows = _read_jsonl(os.path.join(settings.log_directory, "ai", "invocations.jsonl"))
    assert len(rows) == 1  # not 2 - a duplicate handler would double-log this line
