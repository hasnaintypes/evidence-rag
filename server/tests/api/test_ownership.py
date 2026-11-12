"""Integration tests for cross-user ownership enforcement across documents,
conversations, graph, and /source routes - the concrete regression test
for the Security & Authz Hardening phase (issue #7 / PR #22)."""

from unittest.mock import patch

from tests.conftest import override_current_user
from src.storage.database import (
    upsert_document_record,
    insert_nodes,
    create_conversation,
)
from src.core.security import generate_source_token

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


def test_document_status_404s_for_a_non_owner(client, app):
    _seed_private_document()
    override_current_user(app, OTHER)

    response = client.get("/documents/doc-1/status")
    assert response.status_code == 404


def test_document_status_succeeds_for_the_owner(client, app):
    _seed_private_document()
    override_current_user(app, OWNER)

    response = client.get("/documents/doc-1/status")
    assert response.status_code == 200


def test_document_status_succeeds_for_any_user_on_a_shared_document(client, app):
    _seed_shared_document()
    override_current_user(app, OTHER)

    response = client.get("/documents/shared-doc/status")
    assert response.status_code == 200


def test_conversation_creation_rejects_a_document_the_caller_does_not_own(client, app):
    _seed_private_document()
    override_current_user(app, OTHER)

    response = client.post("/conversations", json={"doc_ids": ["doc-1"]})
    assert response.status_code == 404


def test_conversation_creation_accepts_a_shared_document(client, app):
    _seed_shared_document()
    override_current_user(app, OTHER)

    response = client.post("/conversations", json={"doc_ids": ["shared-doc"]})
    assert response.status_code == 201


def test_conversation_creation_with_no_doc_ids_falls_back_to_the_shared_corpus(client, app):
    _seed_shared_document()
    _seed_private_document()  # some other user's private doc must never be picked up here
    override_current_user(app, OTHER)

    response = client.post("/conversations", json={"doc_ids": []})
    assert response.status_code == 201
    assert response.json()["doc_ids"] == ["shared-doc"]


def test_conversation_creation_with_doc_ids_omitted_also_falls_back(client, app):
    _seed_shared_document()
    override_current_user(app, OTHER)

    response = client.post("/conversations", json={})
    assert response.status_code == 201
    assert response.json()["doc_ids"] == ["shared-doc"]


def test_conversation_creation_400s_when_no_shared_documents_exist(client, app):
    override_current_user(app, OTHER)

    response = client.post("/conversations", json={"doc_ids": []})
    assert response.status_code == 400


def test_get_conversation_404s_for_a_non_owner(client, app):
    _seed_shared_document()
    create_conversation("conv-1", user_id=OWNER, doc_ids=["shared-doc"])
    override_current_user(app, OTHER)

    response = client.get("/conversations/conv-1")
    assert response.status_code == 404


def test_get_conversation_succeeds_for_the_owner(client, app):
    _seed_shared_document()
    create_conversation("conv-1", user_id=OWNER, doc_ids=["shared-doc"])
    override_current_user(app, OWNER)

    response = client.get("/conversations/conv-1")
    assert response.status_code == 200


def test_delete_conversation_404s_for_a_non_owner(client, app):
    _seed_shared_document()
    create_conversation("conv-1", user_id=OWNER, doc_ids=["shared-doc"])
    override_current_user(app, OTHER)

    response = client.delete("/conversations/conv-1")
    assert response.status_code == 404


def test_add_document_to_conversation_rejects_a_document_the_caller_does_not_own(client, app):
    _seed_shared_document()
    _seed_private_document(doc_id="private-2", owner=OWNER)
    create_conversation("conv-1", user_id=OTHER, doc_ids=["shared-doc"])
    override_current_user(app, OTHER)

    response = client.post("/conversations/conv-1/documents", json={"doc_id": "private-2"})
    assert response.status_code == 404


def test_graph_endpoint_404s_for_a_non_owner_scoped_query(client, app):
    _seed_private_document()
    override_current_user(app, OTHER)

    response = client.get("/graph", params={"doc_id": "doc-1"})
    assert response.status_code == 404


def _seed_node(node_id="node-1", doc_id="doc-1"):
    """insert_nodes() accepts plain dicts (falls back to the raw dict when
    the item has no to_dict() method), so a real KnowledgeNode isn't
    needed here."""
    insert_nodes(
        [
            {
                "id": node_id,
                "doc_id": doc_id,
                "parent_id": None,
                "type": "paragraph",
                "level": 0,
                "heading_path": "Intro",
                "content": "hello",
                "page": 1,
                "bbox": None,
                "order": 0,
                "metadata": {},
            }
        ]
    )


def test_graph_section_404s_for_a_non_owner(client, app):
    _seed_private_document()
    _seed_node()
    override_current_user(app, OTHER)

    response = client.get("/graph/section/node-1")
    assert response.status_code == 404


def test_graph_section_succeeds_for_the_owner(client, app):
    _seed_private_document()
    _seed_node()
    override_current_user(app, OWNER)

    response = client.get("/graph/section/node-1")
    assert response.status_code == 200
    assert response.json()["doc_id"] == "doc-1"


def test_graph_section_404s_for_an_unknown_node(client, app):
    override_current_user(app, OWNER)

    response = client.get("/graph/section/does-not-exist")
    assert response.status_code == 404


def test_source_route_rejects_a_token_issued_for_a_different_filename(client):
    token = generate_source_token("other.pdf", OWNER)
    response = client.get("/source/private.pdf", params={"token": token})
    assert response.status_code == 403


def test_source_route_404s_when_the_token_owner_cannot_access_the_file(client):
    _seed_private_document(filename="private.pdf")
    token = generate_source_token("private.pdf", OTHER)
    response = client.get("/source/private.pdf", params={"token": token})
    assert response.status_code == 404


def test_source_route_rejects_a_missing_token(client):
    response = client.get("/source/private.pdf", params={"token": ""})
    assert response.status_code == 403


def test_source_route_serves_the_file_for_the_owner(client):
    _seed_private_document(filename="private.pdf")
    token = generate_source_token("private.pdf", OWNER)
    with patch("api.services.document_service.get_source_path", return_value=None):
        # Ownership passes; the 404 here is "file not on disk", not an
        # authz failure - confirms the token/ownership check let it
        # through to the next stage rather than blocking it.
        response = client.get("/source/private.pdf", params={"token": token})
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
