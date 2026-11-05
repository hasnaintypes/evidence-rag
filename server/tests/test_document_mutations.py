"""Tests for the document management actions added in #21 (rename, delete,
re-ingest): authz (shared docs 403, someone else's doc 404, owner 200) plus
basic per-action behavior. File-storage/pipeline calls are mocked at their
import site in api.services.document_service, same convention as
test_ownership.py's get_source_path patch - these tests never touch real
disk."""

from unittest.mock import patch

from tests.conftest import override_current_user
from src.storage.database import get_document_record, upsert_document_record

OWNER = "owner-user"
OTHER = "other-user"


def _seed_private_document(doc_id="doc-1", owner=OWNER, filename="private.pdf"):
    upsert_document_record(
        doc_id=doc_id, filename=filename, file_hash="hash1", node_count=0, chunk_count=0, user_id=owner
    )


def _seed_shared_document(doc_id="shared-doc", filename="shared.pdf"):
    upsert_document_record(
        doc_id=doc_id, filename=filename, file_hash="hash2", node_count=0, chunk_count=0, user_id=None
    )


# --- Rename ---------------------------------------------------------------


def test_rename_404s_for_a_non_owner(client, app):
    _seed_private_document()
    override_current_user(app, OTHER)

    response = client.patch("/documents/doc-1", json={"filename": "renamed.pdf"})
    assert response.status_code == 404


def test_rename_404s_for_a_doc_id_that_does_not_exist(client, app):
    override_current_user(app, OWNER)

    response = client.patch("/documents/no-such-doc", json={"filename": "renamed.pdf"})
    assert response.status_code == 404


def test_rename_403s_for_a_shared_document(client, app):
    _seed_shared_document()
    override_current_user(app, OWNER)

    response = client.patch("/documents/shared-doc", json={"filename": "renamed.pdf"})
    assert response.status_code == 403


def test_rename_succeeds_for_the_owner(client, app):
    _seed_private_document()
    override_current_user(app, OWNER)

    with patch("api.services.document_service.rename_file") as mock_rename_file:
        response = client.patch("/documents/doc-1", json={"filename": "renamed.pdf"})

    assert response.status_code == 200
    mock_rename_file.assert_called_once_with("private.pdf", "renamed.pdf")
    assert get_document_record("doc-1")["filename"] == "renamed.pdf"


def test_rename_rejects_a_different_file_extension(client, app):
    _seed_private_document()
    override_current_user(app, OWNER)

    response = client.patch("/documents/doc-1", json={"filename": "renamed.docx"})
    assert response.status_code == 400
    assert get_document_record("doc-1")["filename"] == "private.pdf"


def test_rename_rejects_a_filename_already_used_by_another_document(client, app):
    _seed_private_document(doc_id="doc-1", filename="private.pdf")
    _seed_private_document(doc_id="doc-2", filename="taken.pdf")
    override_current_user(app, OWNER)

    response = client.patch("/documents/doc-1", json={"filename": "taken.pdf"})
    assert response.status_code == 409


# --- Delete -----------------------------------------------------------------


def test_delete_404s_for_a_non_owner(client, app):
    _seed_private_document()
    override_current_user(app, OTHER)

    response = client.delete("/documents/doc-1")
    assert response.status_code == 404


def test_delete_403s_for_a_shared_document(client, app):
    _seed_shared_document()
    override_current_user(app, OWNER)

    response = client.delete("/documents/shared-doc")
    assert response.status_code == 403


def test_delete_succeeds_for_the_owner_and_removes_the_record(client, app):
    _seed_private_document()
    override_current_user(app, OWNER)

    with patch("api.services.document_service.delete_file") as mock_delete_file:
        response = client.delete("/documents/doc-1")

    assert response.status_code == 200
    mock_delete_file.assert_called_once_with("private.pdf")
    assert get_document_record("doc-1") is None


# --- Re-ingest ---------------------------------------------------------------


def test_reingest_404s_for_a_non_owner(client, app):
    _seed_private_document()
    override_current_user(app, OTHER)

    response = client.post("/documents/doc-1/reingest")
    assert response.status_code == 404


def test_reingest_403s_for_a_shared_document(client, app):
    _seed_shared_document()
    override_current_user(app, OWNER)

    response = client.post("/documents/shared-doc/reingest")
    assert response.status_code == 403


def test_reingest_404s_when_the_stored_file_is_missing(client, app):
    _seed_private_document()
    override_current_user(app, OWNER)

    with patch("api.services.document_service.get_source_path", return_value=None):
        response = client.post("/documents/doc-1/reingest")

    assert response.status_code == 404


def test_reingest_forces_past_the_unchanged_short_circuit(client, app):
    """force=True must reach prepare_ingest - a hash-unchanged file should
    still get a "processing" response, not the "unchanged" one that a
    plain re-upload would get for an identical file."""
    _seed_private_document()
    override_current_user(app, OWNER)

    fake_chunks = [{"chunk_text": "hello", "metadata": {}}]
    with (
        patch("api.services.document_service.get_source_path", return_value="/tmp/fake-private.pdf"),
        patch("api.services.document_service.prepare_ingest") as mock_prepare_ingest,
        patch("api.services.document_service.finish_ingest"),
        patch("api.services.document_service.invalidate_index_cache"),
    ):
        mock_prepare_ingest.return_value = {
            "status": "ready_to_index",
            "doc_id": "doc-1",
            "chunks_data": fake_chunks,
        }
        response = client.post("/documents/doc-1/reingest")

    assert response.status_code == 200
    assert response.json()["status"] == "processing"
    mock_prepare_ingest.assert_called_once_with("/tmp/fake-private.pdf", "private.pdf", user_id=OWNER, force=True)
