"""Unit tests for src/security.py's signed source-citation tokens - pure
JWT logic, no DB/network involved."""

import time

from src.security import generate_source_token, verify_source_token


def test_valid_token_returns_the_issuing_user_id():
    token = generate_source_token("report.pdf", "user-1")
    assert verify_source_token("report.pdf", token) == "user-1"


def test_token_rejected_for_a_different_filename():
    """A token is scoped to the exact filename it was minted for - it must
    not authorize access to any other file, even one the same user owns."""
    token = generate_source_token("report.pdf", "user-1")
    assert verify_source_token("other.pdf", token) is None


def test_expired_token_is_rejected():
    token = generate_source_token("report.pdf", "user-1", ttl_seconds=-1)
    assert verify_source_token("report.pdf", token) is None


def test_tampered_token_is_rejected():
    token = generate_source_token("report.pdf", "user-1")
    tampered = token[:-4] + ("0" if token[-4] != "0" else "1") + token[-3:]
    assert verify_source_token("report.pdf", tampered) is None


def test_missing_token_is_rejected():
    assert verify_source_token("report.pdf", "") is None
    assert verify_source_token("report.pdf", None) is None


def test_token_still_valid_just_before_expiry():
    token = generate_source_token("report.pdf", "user-1", ttl_seconds=5)
    time.sleep(0.1)
    assert verify_source_token("report.pdf", token) == "user-1"
