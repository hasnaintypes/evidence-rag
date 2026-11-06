"""
Tests for POST /upload (DocumentService.upload()) - previously untested (see
CLAUDE.md's "Test coverage is still partial" note: upload -> background-
ingestion -> status transitions had no coverage). Mocks save_upload/
prepare_ingest/finish_ingest at their import site in
api.services.document_service, same convention as test_document_mutations.py
- these tests never touch real disk or run real parsing/embedding.
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest

from tests.conftest import override_current_user
from src.storage.database import upsert_document_record

OWNER = "owner-user"
OTHER = "other-user"


@contextmanager
def _fake_save_upload(path="/tmp/fake-upload.md"):
    yield path


def _upload(client, filename="doc.md", content=b"content", content_type="text/markdown"):
    return client.post("/upload", files={"file": (filename, content, content_type)})


def test_upload_rejects_unsupported_extension(client, app):
    override_current_user(app, OWNER)

    response = _upload(client, filename="doc.exe")
    assert response.status_code == 400
    assert "Unsupported file format" in response.json()["detail"]


def test_upload_rejects_oversized_file(client, app):
    override_current_user(app, OWNER)

    oversized = b"x" * (50 * 1024 * 1024 + 1)
    response = _upload(client, content=oversized)
    assert response.status_code == 413


def test_upload_409s_when_filename_in_use_by_other(client, app):
    override_current_user(app, OWNER)
    upsert_document_record(
        doc_id="other-doc", filename="doc.md", file_hash="h", node_count=0, chunk_count=0, user_id=OTHER
    )

    response = _upload(client)
    assert response.status_code == 409


def test_upload_500s_when_prepare_ingest_raises(client, app):
    override_current_user(app, OWNER)

    with (
        patch("api.services.document_service.save_upload", lambda filename, f: _fake_save_upload()),
        patch("api.services.document_service.prepare_ingest", side_effect=RuntimeError("parse failed")),
    ):
        response = _upload(client)

    assert response.status_code == 500


def test_upload_returns_unchanged_for_identical_content(client, app):
    override_current_user(app, OWNER)

    with (
        patch("api.services.document_service.save_upload", lambda filename, f: _fake_save_upload()),
        patch("api.services.document_service.prepare_ingest") as mock_prepare,
    ):
        mock_prepare.return_value = {"status": "unchanged", "chunk_count": 0, "doc_id": "doc-1"}
        response = _upload(client)

    assert response.status_code == 200
    assert response.json()["status"] == "unchanged"


def test_upload_400s_for_empty_content(client, app):
    override_current_user(app, OWNER)

    with (
        patch("api.services.document_service.save_upload", lambda filename, f: _fake_save_upload()),
        patch("api.services.document_service.prepare_ingest") as mock_prepare,
    ):
        mock_prepare.return_value = {"status": "empty", "chunk_count": 0, "doc_id": "doc-1"}
        response = _upload(client)

    assert response.status_code == 400


def test_upload_schedules_finish_ingest_with_nodes_and_is_replace(client, app):
    """The response's "processing" status must come with finish_ingest()
    scheduled as a background task, carrying through prepare_ingest()'s
    nodes/is_replace - the fields #46's fix added to make the delete/
    insert swap safe to defer. A regression here (e.g. dropping those
    kwargs) would silently re-introduce #46 for the upload path too."""
    override_current_user(app, OWNER)

    fake_nodes = ["node-a", "node-b"]
    fake_chunks = [{"chunk_text": "hello", "metadata": {}}]
    with (
        patch("api.services.document_service.save_upload", lambda filename, f: _fake_save_upload()),
        patch("api.services.document_service.prepare_ingest") as mock_prepare,
        patch("api.services.document_service.finish_ingest") as mock_finish,
    ):
        mock_prepare.return_value = {
            "status": "ready_to_index",
            "doc_id": "doc-1",
            "chunks_data": fake_chunks,
            "nodes": fake_nodes,
            "is_replace": True,
        }
        response = _upload(client)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "processing"
    assert body["doc_id"] == "doc-1"
    assert body["analytics"]["chunk_count"] == 1

    mock_finish.assert_called_once()
    args, kwargs = mock_finish.call_args
    assert args[0] == "doc-1"
    assert args[1] == fake_chunks
    assert kwargs["nodes"] == fake_nodes
    assert kwargs["is_replace"] is True


@pytest.mark.parametrize("is_replace", [True, False])
def test_upload_handles_missing_nodes_is_replace_keys_gracefully(client, app, is_replace):
    """prepare_ingest()'s "nodes"/"is_replace" keys should be read with
    .get()/defaults, not direct indexing, so a caller or a future
    prepare_ingest() change that omits them doesn't crash the route."""
    override_current_user(app, OWNER)

    fake_chunks = [{"chunk_text": "hello", "metadata": {}}]
    prep = {"status": "ready_to_index", "doc_id": "doc-1", "chunks_data": fake_chunks}
    if is_replace:
        prep["is_replace"] = True

    with (
        patch("api.services.document_service.save_upload", lambda filename, f: _fake_save_upload()),
        patch("api.services.document_service.prepare_ingest", return_value=prep),
        patch("api.services.document_service.finish_ingest"),
    ):
        response = _upload(client)

    assert response.status_code == 202
