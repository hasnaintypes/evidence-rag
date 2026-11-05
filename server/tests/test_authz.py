"""Unit tests for api/authz.py's shared ownership-check helpers. Each
resource lookup is mocked directly - these tests cover authz.py's own
branching logic, not the storage layer underneath it. Integration-level
cross-user coverage (via real HTTP requests) lives in test_ownership.py."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.authz import get_owned_conversation, get_owned_document, get_owned_graph_scope
from api.deps import CurrentUser


def test_get_owned_document_404s_on_unknown_document():
    with patch("api.authz.get_document_record", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            get_owned_document("missing-doc", CurrentUser(id="user-1", email=None))
        assert exc_info.value.status_code == 404


def test_get_owned_document_404s_on_another_users_document():
    with patch("api.authz.get_document_record", return_value={"user_id": "owner", "filename": "a.pdf"}):
        with pytest.raises(HTTPException) as exc_info:
            get_owned_document("doc-1", CurrentUser(id="someone-else", email=None))
        assert exc_info.value.status_code == 404


def test_get_owned_document_allows_the_owner():
    record = {"user_id": "owner", "filename": "a.pdf"}
    with patch("api.authz.get_document_record", return_value=record):
        result = get_owned_document("doc-1", CurrentUser(id="owner", email=None))
        assert result == record


def test_get_owned_document_allows_any_user_on_a_shared_document():
    """user_id=None on the document record means shared/demo (e.g.
    docs/sample_docs) - every signed-in user can access it."""
    record = {"user_id": None, "filename": "shared.pdf"}
    with patch("api.authz.get_document_record", return_value=record):
        result = get_owned_document("doc-1", CurrentUser(id="anyone", email=None))
        assert result == record


def test_get_owned_conversation_404s_on_unknown_conversation():
    with patch("api.authz.get_conversation", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            get_owned_conversation("missing-conv", CurrentUser(id="user-1", email=None))
        assert exc_info.value.status_code == 404


def test_get_owned_conversation_404s_on_another_users_conversation():
    with patch("api.authz.get_conversation", return_value={"user_id": "owner", "doc_ids": []}):
        with pytest.raises(HTTPException) as exc_info:
            get_owned_conversation("conv-1", CurrentUser(id="someone-else", email=None))
        assert exc_info.value.status_code == 404


def test_get_owned_conversation_allows_the_owner():
    record = {"user_id": "owner", "doc_ids": ["doc-1"]}
    with patch("api.authz.get_conversation", return_value=record):
        result = get_owned_conversation("conv-1", CurrentUser(id="owner", email=None))
        assert result == record


def test_get_owned_graph_scope_with_a_doc_id_checks_ownership():
    with patch("api.authz.get_document_record", return_value={"user_id": "owner", "filename": "a.pdf"}):
        scope = get_owned_graph_scope("doc-1", CurrentUser(id="owner", email=None))
    assert scope == {"doc_id": "doc-1", "allowed_doc_ids": None}


def test_get_owned_graph_scope_with_a_doc_id_404s_for_a_non_owner():
    with patch("api.authz.get_document_record", return_value={"user_id": "owner", "filename": "a.pdf"}):
        with pytest.raises(HTTPException) as exc_info:
            get_owned_graph_scope("doc-1", CurrentUser(id="someone-else", email=None))
        assert exc_info.value.status_code == 404


def test_get_owned_graph_scope_without_a_doc_id_returns_every_accessible_doc_id():
    accessible = [{"doc_id": "doc-1"}, {"doc_id": "doc-2"}]
    with patch("api.authz.list_documents", return_value=accessible):
        scope = get_owned_graph_scope(None, CurrentUser(id="user-1", email=None))
    assert scope == {"doc_id": None, "allowed_doc_ids": ["doc-1", "doc-2"]}
