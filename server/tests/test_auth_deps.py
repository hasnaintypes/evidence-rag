"""Unit tests for api/deps.py - JWT verification (missing/expired/invalid/
happy path) and the require_document_access ownership helper. The JWKS
client itself (a real network call to Supabase) is mocked - these tests
cover deps.py's own branching logic, not Supabase's key rotation."""

from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException

from api.deps import get_current_user, require_document_access, CurrentUser


def _mock_jwks_client(decoded_payload=None, decode_side_effect=None):
    """Patches api.deps._get_jwks_client() so get_current_user never makes
    a real network call, and patches jwt.decode to return/raise whatever
    the test wants - get_signing_key_from_jwt's return value is irrelevant
    to deps.py's own logic once jwt.decode is controlled directly."""
    fake_client = MagicMock()
    fake_client.get_signing_key_from_jwt.return_value = MagicMock(key="fake-key")
    decode_patch = patch("api.deps.jwt.decode")
    if decode_side_effect is not None:
        decode_patch_obj = decode_patch.start()
        decode_patch_obj.side_effect = decode_side_effect
    else:
        decode_patch_obj = decode_patch.start()
        decode_patch_obj.return_value = decoded_payload
    return fake_client, decode_patch


def test_missing_authorization_header_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="")
    assert exc_info.value.status_code == 401


def test_malformed_scheme_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="Basic sometoken")
    assert exc_info.value.status_code == 401


def test_bearer_with_no_token_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="Bearer ")
    assert exc_info.value.status_code == 401


def test_expired_token_is_rejected():
    fake_client, decode_patch = _mock_jwks_client(decode_side_effect=jwt.ExpiredSignatureError())
    try:
        with patch("api.deps._get_jwks_client", return_value=fake_client):
            with pytest.raises(HTTPException) as exc_info:
                get_current_user(authorization="Bearer sometoken")
            assert exc_info.value.status_code == 401
            assert "expired" in exc_info.value.detail.lower()
    finally:
        decode_patch.stop()


def test_invalid_token_is_rejected():
    fake_client, decode_patch = _mock_jwks_client(decode_side_effect=jwt.InvalidTokenError())
    try:
        with patch("api.deps._get_jwks_client", return_value=fake_client):
            with pytest.raises(HTTPException) as exc_info:
                get_current_user(authorization="Bearer sometoken")
            assert exc_info.value.status_code == 401
    finally:
        decode_patch.stop()


def test_token_without_subject_claim_is_rejected():
    fake_client, decode_patch = _mock_jwks_client(decoded_payload={"email": "a@b.com"})
    try:
        with patch("api.deps._get_jwks_client", return_value=fake_client):
            with pytest.raises(HTTPException) as exc_info:
                get_current_user(authorization="Bearer sometoken")
            assert exc_info.value.status_code == 401
    finally:
        decode_patch.stop()


def test_valid_token_returns_the_current_user():
    fake_client, decode_patch = _mock_jwks_client(decoded_payload={"sub": "user-123", "email": "a@b.com"})
    try:
        with patch("api.deps._get_jwks_client", return_value=fake_client):
            user = get_current_user(authorization="Bearer sometoken")
            assert user.id == "user-123"
            assert user.email == "a@b.com"
    finally:
        decode_patch.stop()


def test_require_document_access_404s_on_unknown_document():
    with patch("api.deps.get_document_record", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            require_document_access("missing-doc", CurrentUser(id="user-1", email=None))
        assert exc_info.value.status_code == 404


def test_require_document_access_404s_on_another_users_document():
    with patch("api.deps.get_document_record", return_value={"user_id": "owner", "filename": "a.pdf"}):
        with pytest.raises(HTTPException) as exc_info:
            require_document_access("doc-1", CurrentUser(id="someone-else", email=None))
        assert exc_info.value.status_code == 404


def test_require_document_access_allows_the_owner():
    record = {"user_id": "owner", "filename": "a.pdf"}
    with patch("api.deps.get_document_record", return_value=record):
        result = require_document_access("doc-1", CurrentUser(id="owner", email=None))
        assert result == record


def test_require_document_access_allows_any_user_on_a_shared_document():
    """user_id=None on the document record means shared/demo (e.g.
    docs/sample_docs) - every signed-in user can access it."""
    record = {"user_id": None, "filename": "shared.pdf"}
    with patch("api.deps.get_document_record", return_value=record):
        result = require_document_access("doc-1", CurrentUser(id="anyone", email=None))
        assert result == record
