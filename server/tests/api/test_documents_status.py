"""
Tests for GET /documents/{doc_id}/status and the SSE status stream
(DocumentService.get_status()/status_stream()) - previously untested (see
CLAUDE.md's "Test coverage is still partial" note)."""

from unittest.mock import patch

from tests.conftest import override_current_user
from api.services.document_service import DocumentService
from src.storage.database import upsert_document_record, mark_document_processing

OWNER = "owner-user"
OTHER = "other-user"


def _seed_private_document(doc_id="doc-1", owner=OWNER, filename="private.pdf"):
    upsert_document_record(
        doc_id=doc_id, filename=filename, file_hash="hash1", node_count=0, chunk_count=0, user_id=owner
    )


# --- GET /documents/{doc_id}/status ---------------------------------------


def test_get_status_404s_for_a_non_owner(client, app):
    _seed_private_document()
    override_current_user(app, OTHER)

    response = client.get("/documents/doc-1/status")
    assert response.status_code == 404


def test_get_status_404s_for_a_doc_id_that_does_not_exist(client, app):
    override_current_user(app, OWNER)

    response = client.get("/documents/does-not-exist/status")
    assert response.status_code == 404


def test_get_status_returns_the_real_row_for_the_owner(client, app):
    override_current_user(app, OWNER)
    mark_document_processing("doc-1", "private.pdf", file_hash="hash1", user_id=OWNER, node_count=5, chunks_total=5)

    response = client.get("/documents/doc-1/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["chunks_total"] == 5


# --- SSE status stream generator -------------------------------------------
#
# Tested directly against DocumentService._status_stream_generator() rather
# than over TestClient's streaming support - the generator's own
# termination/dedup logic is what #46-adjacent coverage is after here, not
# the StreamingResponse wiring itself (a thin pass-through in
# api/routers/documents.py).


def test_status_stream_emits_on_change_and_stops_at_a_terminal_state():
    statuses = [
        {"status": "processing", "chunks_indexed": 0, "chunks_total": 2, "chunk_count": 0},
        {"status": "processing", "chunks_indexed": 0, "chunks_total": 2, "chunk_count": 0},  # unchanged - no event
        {"status": "processing", "chunks_indexed": 1, "chunks_total": 2, "chunk_count": 0},
        {"status": "ready", "chunks_indexed": 2, "chunks_total": 2, "chunk_count": 2},
    ]
    calls = iter(statuses)

    with (
        patch("api.services.document_service.get_document_status", lambda doc_id: next(calls)),
        patch("api.services.document_service.time.sleep", lambda _s: None),
    ):
        events = list(DocumentService._status_stream_generator("doc-1"))

    # The unchanged second status must not produce a duplicate event.
    assert len(events) == 3
    assert '"status": "processing", "chunks_indexed": 0' in events[0]
    assert '"status": "processing", "chunks_indexed": 1' in events[1]
    assert '"status": "ready"' in events[2]


def test_status_stream_emits_an_error_event_and_stops_when_the_document_disappears():
    with patch("api.services.document_service.get_document_status", lambda doc_id: None):
        events = list(DocumentService._status_stream_generator("doc-1"))

    assert len(events) == 1
    assert "event: error" in events[0]
    assert "Document not found" in events[0]


def test_status_stream_stops_at_failed_too():
    with (
        patch(
            "api.services.document_service.get_document_status",
            lambda doc_id: {"status": "failed", "chunks_indexed": 0, "chunks_total": 2, "chunk_count": 0},
        ),
        patch("api.services.document_service.time.sleep", lambda _s: None),
    ):
        events = list(DocumentService._status_stream_generator("doc-1"))

    assert len(events) == 1
    assert '"status": "failed"' in events[0]
