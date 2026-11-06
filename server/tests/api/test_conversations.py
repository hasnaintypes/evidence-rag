"""
Tests for POST /conversations/{id}/messages's failure path (#52) - a
process_chat_query() failure must be a real 500, not a 200 with a
fabricated reply persisted as if it were a real assistant turn - and for
POST /conversations/{id}/documents's ownership/business-rule behavior
(#54) - adding a document now asserts conversation ownership via
api/authz.py's get_owned_conversation() like every other mutation,
instead of add_document_to_conversation()'s own inline check.
"""

from unittest.mock import patch

import pytest

from tests.conftest import override_current_user
from src.storage.database import (
    MAX_CONVERSATION_DOCS,
    add_document_to_conversation,
    create_conversation,
    get_conversation_messages,
    upsert_document_record,
)

OWNER = "owner-user"
OTHER = "other-user"


def _seed_conversation(doc_id="doc-1", owner=OWNER) -> str:
    upsert_document_record(doc_id=doc_id, filename="doc.md", file_hash="h", node_count=1, chunk_count=1, user_id=owner)
    conversation = create_conversation("conv-1", user_id=owner, doc_ids=[doc_id])
    return conversation["id"]


def test_send_message_500s_and_does_not_persist_a_fake_reply_on_pipeline_failure(client, app):
    conversation_id = _seed_conversation()
    override_current_user(app, OWNER)

    with patch("api.services.conversation_service.process_chat_query", side_effect=RuntimeError("quota exceeded")):
        response = client.post(f"/conversations/{conversation_id}/messages", json={"message": "hello"})

    assert response.status_code == 500
    # The generic client-facing message, not the raw exception text -
    # never leak internal detail into the response.
    assert "quota exceeded" not in response.text

    messages = get_conversation_messages(conversation_id)
    # The user's own message is real and stays; no fabricated assistant
    # reply gets persisted alongside it.
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "hello"


def test_send_message_returns_the_real_reply_on_success(client, app):
    conversation_id = _seed_conversation()
    override_current_user(app, OWNER)

    fake_result = {
        "reply": "a real answer",
        "sources": [],
        "faithfulness": {"score": 0.9, "unsupported_claims": []},
        "telemetry": {"request_id": "abc"},
        "chunks_matrix": [],
        "thinking": "",
    }
    with patch("api.services.conversation_service.process_chat_query", return_value=fake_result):
        response = client.post(f"/conversations/{conversation_id}/messages", json={"message": "hello"})

    assert response.status_code == 200
    assert response.json()["content"] == "a real answer"

    messages = get_conversation_messages(conversation_id)
    assert len(messages) == 2
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "a real answer"


# --- Add document to a conversation (#54) -----------------------------------


def test_add_document_404s_for_a_non_owner_of_the_conversation(client, app):
    conversation_id = _seed_conversation(owner=OWNER)
    upsert_document_record(
        doc_id="doc-2", filename="doc2.md", file_hash="h2", node_count=1, chunk_count=1, user_id=OTHER
    )
    override_current_user(app, OTHER)

    response = client.post(f"/conversations/{conversation_id}/documents", json={"doc_id": "doc-2"})
    assert response.status_code == 404


def test_add_document_404s_for_a_conversation_that_does_not_exist(client, app):
    upsert_document_record(doc_id="doc-1", filename="doc.md", file_hash="h", node_count=1, chunk_count=1, user_id=OWNER)
    override_current_user(app, OWNER)

    response = client.post("/conversations/does-not-exist/documents", json={"doc_id": "doc-1"})
    assert response.status_code == 404


def test_add_document_400s_when_already_attached(client, app):
    conversation_id = _seed_conversation(owner=OWNER)
    override_current_user(app, OWNER)

    response = client.post(f"/conversations/{conversation_id}/documents", json={"doc_id": "doc-1"})
    assert response.status_code == 400
    assert "already attached" in response.json()["detail"]


def test_add_document_400s_at_the_conversation_document_cap(client, app):
    conversation_id = _seed_conversation(owner=OWNER)
    override_current_user(app, OWNER)

    for i in range(MAX_CONVERSATION_DOCS - 1):
        doc_id = f"extra-doc-{i}"
        upsert_document_record(
            doc_id=doc_id, filename=f"{doc_id}.md", file_hash=f"h{i}", node_count=1, chunk_count=1, user_id=OWNER
        )
        response = client.post(f"/conversations/{conversation_id}/documents", json={"doc_id": doc_id})
        assert response.status_code == 200

    upsert_document_record(
        doc_id="one-too-many", filename="too-many.md", file_hash="hx", node_count=1, chunk_count=1, user_id=OWNER
    )
    response = client.post(f"/conversations/{conversation_id}/documents", json={"doc_id": "one-too-many"})
    assert response.status_code == 400
    assert "at most" in response.json()["detail"]


def test_add_document_to_conversation_raises_lookup_error_not_a_crash_for_a_vanished_conversation():
    """Regression for a race caught in code review: add_document_to_conversation()
    no longer does its own ownership SELECT (that moved to
    get_owned_conversation(), see #54) - but it must still handle a
    conversation_id that doesn't exist (e.g. deleted between the
    service's ownership check and this call) by raising LookupError,
    not by crashing on dict(None)."""
    with pytest.raises(LookupError):
        add_document_to_conversation("does-not-exist", doc_id="doc-1")


def test_add_document_succeeds_for_the_owner(client, app):
    conversation_id = _seed_conversation(owner=OWNER)
    upsert_document_record(
        doc_id="doc-2", filename="doc2.md", file_hash="h2", node_count=1, chunk_count=1, user_id=OWNER
    )
    override_current_user(app, OWNER)

    response = client.post(f"/conversations/{conversation_id}/documents", json={"doc_id": "doc-2"})
    assert response.status_code == 200
    assert "doc-2" in response.json()["doc_ids"]
