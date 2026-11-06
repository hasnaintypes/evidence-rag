"""
Tests for POST /conversations/{id}/messages's failure path (#52) - a
process_chat_query() failure must be a real 500, not a 200 with a
fabricated reply persisted as if it were a real assistant turn.
"""

from unittest.mock import patch

from tests.conftest import override_current_user
from src.storage.database import create_conversation, get_conversation_messages, upsert_document_record

OWNER = "owner-user"


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
