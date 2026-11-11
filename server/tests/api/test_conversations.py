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
    get_conversation,
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


def test_send_message_returns_llm_generated_title_on_first_turn_only(client, app):
    conversation_id = _seed_conversation()
    override_current_user(app, OWNER)

    fake_result = {
        "reply": "a real answer",
        "sources": [],
        "faithfulness": {"score": 0.9, "unsupported_claims": []},
        "telemetry": {},
        "chunks_matrix": [],
        "thinking": "",
    }
    with (
        patch("api.services.conversation_service.process_chat_query", return_value=fake_result),
        patch(
            "api.services.conversation_service.generate_structured_response",
            return_value={"title": "Retention Drivers This Quarter"},
        ),
    ):
        first = client.post(f"/conversations/{conversation_id}/messages", json={"message": "hello"})
        assert first.status_code == 200
        assert first.json()["title"] == "Retention Drivers This Quarter"

        # A second turn in the same conversation is not the first turn
        # anymore - no LLM title call should fire, and the response's
        # title field should be None even though the mock would still
        # happily return one if called.
        second = client.post(f"/conversations/{conversation_id}/messages", json={"message": "a follow-up"})
        assert second.status_code == 200
        assert second.json()["title"] is None

    conversation = get_conversation(conversation_id)
    assert conversation["title"] == "Retention Drivers This Quarter"


def test_send_message_falls_back_to_truncated_title_when_llm_call_fails(client, app):
    conversation_id = _seed_conversation()
    override_current_user(app, OWNER)

    fake_result = {
        "reply": "a real answer",
        "sources": [],
        "faithfulness": {"score": 0.9, "unsupported_claims": []},
        "telemetry": {},
        "chunks_matrix": [],
        "thinking": "",
    }
    with (
        patch("api.services.conversation_service.process_chat_query", return_value=fake_result),
        patch("api.services.conversation_service.generate_structured_response", return_value=None),
    ):
        response = client.post(f"/conversations/{conversation_id}/messages", json={"message": "a fresh question"})

    assert response.status_code == 200
    assert response.json()["title"] is None  # nothing new was generated, so nothing to animate

    conversation = get_conversation(conversation_id)
    assert conversation["title"] == "a fresh question"  # the existing truncated fallback, unchanged


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


def _seed_many_conversations(n: int, owner=OWNER) -> list[str]:
    upsert_document_record(
        doc_id="doc-many", filename="doc.md", file_hash="h", node_count=1, chunk_count=1, user_id=owner
    )
    return [create_conversation(f"conv-many-{i}", user_id=owner, doc_ids=["doc-many"])["id"] for i in range(n)]


def test_list_conversations_returns_lightweight_shape(client, app):
    """GET /conversations's per-row shape should be the lightweight
    ConversationListItemOut - no doc_ids/filenames (those need a second
    batched query only the detail view should pay for)."""
    _seed_many_conversations(1)
    override_current_user(app, OWNER)

    response = client.get("/conversations")
    assert response.status_code == 200
    body = response.json()
    assert "next_cursor" in body
    assert "has_more" in body
    row = body["conversations"][0]
    assert set(row.keys()) == {"id", "title", "pinned", "created_at", "updated_at"}


def test_list_conversations_paginates_without_gaps_or_duplicates(client, app):
    ids = set(_seed_many_conversations(5))
    override_current_user(app, OWNER)

    seen: set[str] = set()
    cursor = None
    pages = 0
    while True:
        response = client.get("/conversations", params={"limit": 2, **({"cursor": cursor} if cursor else {})})
        assert response.status_code == 200
        body = response.json()
        page_ids = {c["id"] for c in body["conversations"]}
        assert not (page_ids & seen), "a page re-returned a conversation from an earlier page"
        seen |= page_ids
        pages += 1
        if not body["has_more"]:
            assert body["next_cursor"] is None
            break
        cursor = body["next_cursor"]
        assert cursor is not None
        assert pages < 10, "pagination never terminated"

    assert seen == ids
    assert pages >= 3  # 5 conversations at 2/page: at least 3 pages


def test_list_conversations_cursor_is_stable_against_a_concurrent_rename(client, app):
    """The property keyset pagination is bought for over OFFSET/LIMIT:
    a conversation being renamed between two page fetches - title isn't
    part of the ORDER BY, so its position is unaffected - must not cause
    the next page to skip or duplicate a row. (A concurrent pin or new
    message is a different kind of churn: those change the row's sort key
    and can move it to before the page boundary already fetched, which no
    forward-only pagination scheme retroactively surfaces - the real
    sidebar handles that case by patching its already-rendered list
    in place client-side instead of relying on a re-fetch.)"""
    ids = _seed_many_conversations(5)
    override_current_user(app, OWNER)

    first = client.get("/conversations", params={"limit": 2})
    assert first.status_code == 200
    first_body = first.json()
    first_ids = {c["id"] for c in first_body["conversations"]}
    assert first_body["has_more"]

    not_yet_returned = next(i for i in ids if i not in first_ids)
    rename_response = client.patch(f"/conversations/{not_yet_returned}", json={"title": "Renamed mid-page"})
    assert rename_response.status_code == 200

    collected = set(first_ids)
    cursor = first_body["next_cursor"]
    while cursor:
        response = client.get("/conversations", params={"limit": 2, "cursor": cursor})
        assert response.status_code == 200
        body = response.json()
        page_ids = {c["id"] for c in body["conversations"]}
        assert not (page_ids & collected), "a rename mid-pagination caused a duplicate row"
        collected |= page_ids
        cursor = body["next_cursor"] if body["has_more"] else None

    assert collected == set(ids), "a rename mid-pagination caused a missing row"
