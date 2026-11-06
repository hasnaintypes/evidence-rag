"""Unit tests for src/rate_limiter.py's per-user sliding-window limiter."""

import time

import pytest
from fastapi import HTTPException

import src.core.rate_limiter as rate_limiter
from src.core.config import settings
from src.core.rate_limiter import enforce_chat_rate_limit, enforce_upload_rate_limit


def test_requests_under_the_limit_all_succeed(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_chat_max_requests", 3)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    for _ in range(3):
        enforce_chat_rate_limit("user-1")  # must not raise


def test_the_request_over_the_limit_is_rejected_with_429(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_chat_max_requests", 2)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    enforce_chat_rate_limit("user-1")
    enforce_chat_rate_limit("user-1")

    with pytest.raises(HTTPException) as exc_info:
        enforce_chat_rate_limit("user-1")
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


def test_different_users_do_not_share_a_limit(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_chat_max_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    enforce_chat_rate_limit("user-1")
    enforce_chat_rate_limit("user-2")  # must not raise - separate key


def test_chat_and_upload_scopes_do_not_share_a_limit(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_chat_max_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_upload_max_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    enforce_chat_rate_limit("user-1")
    enforce_upload_rate_limit("user-1")  # must not raise - separate scope key


def test_an_expired_entry_falls_out_of_the_window(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_chat_max_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 0.05)

    enforce_chat_rate_limit("user-1")
    with pytest.raises(HTTPException):
        enforce_chat_rate_limit("user-1")

    time.sleep(0.1)
    enforce_chat_rate_limit("user-1")  # window has rolled past the first request


def test_a_periodic_sweep_evicts_users_who_never_call_again(monkeypatch):
    """Regression test: a user_id that makes one request and is never
    seen again must not leave a permanent entry in _requests - nothing
    ever revisits that specific key to trim it, so only a periodic sweep
    across the whole dict (triggered by *any* caller's traffic, not
    necessarily that user's own) can reclaim it."""
    monkeypatch.setattr(settings, "rate_limit_chat_max_requests", 5)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 0.05)
    monkeypatch.setattr(rate_limiter, "_SWEEP_EVERY", 3)

    enforce_chat_rate_limit("one-and-done-user")
    assert "chat:one-and-done-user" in rate_limiter._requests

    time.sleep(0.1)  # that user's entry is now fully expired

    # Three unrelated calls from a different user - never touches
    # one-and-done-user's key directly, but should trip the sweep.
    for _ in range(3):
        enforce_chat_rate_limit("someone-else")

    assert "chat:one-and-done-user" not in rate_limiter._requests


def test_disabled_rate_limiting_never_raises(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(settings, "rate_limit_chat_max_requests", 1)

    for _ in range(5):
        enforce_chat_rate_limit("user-1")
