"""
Tests for the entity graph (src/graph.py) and its read-only API surface
(GraphService / GET /graph, GET /graph/section/{node_id}) - previously
untested (see CLAUDE.md's "Test coverage is still partial" note). The
entity graph is exploration-only (not consulted during retrieval/
generation - see CLAUDE.md), so these tests only need to prove it builds
and reads correctly, not that retrieval depends on it.
"""

import json
from unittest.mock import patch

import pytest

from tests.conftest import override_current_user
from src.ingestion.parsers.base import KnowledgeNode, NodeType
from src.storage.database import insert_nodes, upsert_document_record
from src.graph import extract_entities_from_text, build_graph_for_section, build_document_graph

OWNER = "owner-user"
OTHER = "other-user"

LONG_ENOUGH_TEXT = "x" * 150  # extract_entities_from_text requires >= 100 chars


# --- extract_entities_from_text --------------------------------------------


def test_extract_entities_skips_short_text():
    with patch("src.graph.generate_chat_response") as mock_generate:
        result = extract_entities_from_text("too short")
    assert result == []
    mock_generate.assert_not_called()


def test_extract_entities_returns_empty_on_generation_exception():
    with patch("src.graph.generate_chat_response", side_effect=RuntimeError("quota exceeded")):
        result = extract_entities_from_text(LONG_ENOUGH_TEXT)
    assert result == []


def test_extract_entities_treats_an_error_response_as_no_entities():
    with patch("src.graph.generate_chat_response", return_value="Error during generation: timeout"):
        result = extract_entities_from_text(LONG_ENOUGH_TEXT)
    assert result == []


def test_extract_entities_detects_a_repetition_loop():
    degenerate = "\n".join(["JSON array: []"] * 10)
    with patch("src.graph.generate_chat_response", return_value=degenerate):
        result = extract_entities_from_text(LONG_ENOUGH_TEXT)
    assert result == []


def test_extract_entities_returns_empty_when_no_array_found():
    with patch("src.graph.generate_chat_response", return_value="no brackets here at all"):
        result = extract_entities_from_text(LONG_ENOUGH_TEXT)
    assert result == []


def test_extract_entities_returns_empty_on_malformed_json():
    with patch("src.graph.generate_chat_response", return_value='["unterminated'):
        result = extract_entities_from_text(LONG_ENOUGH_TEXT)
    assert result == []


def test_extract_entities_parses_a_valid_array_embedded_in_extra_text():
    response = 'Sure, here is the JSON array: ["Emergency Stop", "SCARA", "600 hours"]\nDone.'
    with patch("src.graph.generate_chat_response", return_value=response):
        result = extract_entities_from_text(LONG_ENOUGH_TEXT)
    assert result == ["Emergency Stop", "SCARA", "600 hours"]


def test_extract_entities_caps_at_eight():
    entities = [f"term-{i}" for i in range(12)]
    with patch("src.graph.generate_chat_response", return_value=json.dumps(entities)):
        result = extract_entities_from_text(LONG_ENOUGH_TEXT)
    assert len(result) == 8


def test_extract_entities_filters_non_scalar_entries():
    # None/dict entries (a malformed-but-valid-JSON LLM response) must be
    # dropped; str/int entries are kept (numbers coerced to str) - see
    # extract_entities_from_text's isinstance() filter. No nested [...]
    # here deliberately - the outer regex extraction is non-greedy, so a
    # nested list/array would need its own dedicated test instead of
    # muddying this one.
    raw = '["Emergency Stop", 600, null, {"nested": "object"}, "SCARA"]'
    with patch("src.graph.generate_chat_response", return_value=raw):
        result = extract_entities_from_text(LONG_ENOUGH_TEXT)
    assert result == ["Emergency Stop", "600", "SCARA"]


# --- build_graph_for_section / build_document_graph -------------------------


def _section_child(doc_id, content="Some section content."):
    return {"content": content}


def test_build_graph_for_section_skips_when_no_content():
    with patch("src.graph.extract_entities_from_text") as mock_extract:
        build_graph_for_section(doc_id="doc-1", section_node_id="sec-1", section_children=[{"content": ""}])
    mock_extract.assert_not_called()


def test_build_graph_for_section_skips_when_fewer_than_two_entities():
    with (
        patch("src.graph.extract_entities_from_text", return_value=["only-one"]),
        patch("src.graph.upsert_entity") as mock_upsert_entity,
    ):
        build_graph_for_section(doc_id="doc-1", section_node_id="sec-1", section_children=[_section_child("doc-1")])
    mock_upsert_entity.assert_not_called()


def test_build_graph_for_section_upserts_entities_and_pairwise_edges():
    with (
        patch("src.graph.extract_entities_from_text", return_value=["A", "B", "C"]),
        patch("src.graph.upsert_entity", side_effect=[1, 2, 3]) as mock_upsert_entity,
        patch("src.graph.upsert_edge") as mock_upsert_edge,
    ):
        build_graph_for_section(doc_id="doc-1", section_node_id="sec-1", section_children=[_section_child("doc-1")])

    assert mock_upsert_entity.call_count == 3
    # 3 entities -> 3 pairwise edges (1-2, 1-3, 2-3).
    assert mock_upsert_edge.call_count == 3


def test_build_document_graph_processes_every_section_via_get_children():
    doc_id = "doc-graph-1"
    section = KnowledgeNode(doc_id=doc_id, type=NodeType.SECTION, heading_path="Intro")
    child = KnowledgeNode(doc_id=doc_id, parent_id=section.id, type=NodeType.PARAGRAPH, content=LONG_ENOUGH_TEXT)
    insert_nodes([section, child])

    with patch("src.graph.build_graph_for_section") as mock_build_section:
        processed = build_document_graph(doc_id, [section])

    assert processed == 1
    mock_build_section.assert_called_once()
    _, kwargs = mock_build_section.call_args
    assert kwargs["section_node_id"] == section.id
    assert len(kwargs["section_children"]) == 1
    assert kwargs["section_children"][0]["id"] == child.id


# --- GraphService / API routes ----------------------------------------------


def _seed_private_document(doc_id="doc-1", owner=OWNER, filename="private.pdf"):
    upsert_document_record(
        doc_id=doc_id, filename=filename, file_hash="hash1", node_count=0, chunk_count=0, user_id=owner
    )


def test_graph_section_404s_for_a_missing_node(client, app):
    override_current_user(app, OWNER)
    response = client.get("/graph/section/does-not-exist")
    assert response.status_code == 404


def test_graph_section_404s_for_a_non_owner(client, app):
    _seed_private_document()
    doc_id = "doc-1"
    section = KnowledgeNode(doc_id=doc_id, type=NodeType.SECTION, heading_path="Intro", content="hi")
    insert_nodes([section])
    override_current_user(app, OTHER)

    response = client.get(f"/graph/section/{section.id}")
    assert response.status_code == 404


def test_graph_section_returns_content_and_a_source_token_for_the_owner(client, app):
    _seed_private_document()
    doc_id = "doc-1"
    section = KnowledgeNode(doc_id=doc_id, type=NodeType.SECTION, heading_path="Intro", content="hello section")
    insert_nodes([section])
    override_current_user(app, OWNER)

    response = client.get(f"/graph/section/{section.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["doc_id"] == doc_id
    assert body["content"] == "hello section"
    assert body["source_token"]


def test_graph_endpoint_404s_when_doc_id_is_given_and_not_owned(client, app):
    _seed_private_document()
    override_current_user(app, OTHER)

    response = client.get("/graph", params={"doc_id": "doc-1"})
    assert response.status_code == 404


def test_graph_endpoint_scopes_to_accessible_documents_when_doc_id_omitted(client, app):
    _seed_private_document(doc_id="doc-1", owner=OWNER)
    _seed_private_document(doc_id="doc-2", owner=OTHER, filename="other.pdf")
    override_current_user(app, OWNER)

    with patch("api.services.graph_service.get_graph_data") as mock_get_graph_data:
        mock_get_graph_data.return_value = {"nodes": [], "edges": []}
        response = client.get("/graph")

    assert response.status_code == 200
    _, kwargs = mock_get_graph_data.call_args
    assert kwargs["doc_id"] is None
    assert kwargs["allowed_doc_ids"] == ["doc-1"]


@pytest.mark.parametrize("entities", [["A"], []])
def test_extract_entities_requires_at_least_two_to_build_anything(entities):
    """Documents extract_entities_from_text's own floor (>=2 is checked by
    build_graph_for_section, not extract_entities_from_text itself) -
    fewer than 2 extracted names is a legitimate, common result (e.g. a
    short or generic section) and must not raise."""
    with patch("src.graph.generate_chat_response", return_value=json.dumps(entities)):
        result = extract_entities_from_text(LONG_ENOUGH_TEXT)
    assert result == entities
