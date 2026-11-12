"""
Tests for the entity graph (src/graph.py) and its read-only API surface
(GraphService / GET /graph, GET /graph/section/{node_id}) - previously
untested (see CLAUDE.md's "Test coverage is still partial" note). The
entity graph is exploration-only (not consulted during retrieval/
generation - see CLAUDE.md), so these tests only need to prove it builds
and reads correctly, not that retrieval depends on it.
"""

from unittest.mock import patch

from tests.conftest import override_current_user
from src.ingestion.parsers.base import KnowledgeNode, NodeType
from src.storage.database import insert_nodes, upsert_document_record
from src.graph import extract_entities_batch, build_document_graph

OWNER = "owner-user"
OTHER = "other-user"

LONG_ENOUGH_TEXT = "x" * 150  # build_document_graph requires >= 100 chars per section


# --- extract_entities_batch --------------------------------------------


def test_extract_entities_batch_returns_empty_list_for_no_texts():
    with patch("src.graph.generate_structured_response") as mock_generate:
        result = extract_entities_batch([])
    assert result == []
    mock_generate.assert_not_called()


def test_extract_entities_batch_returns_empty_lists_on_generation_failure():
    with patch("src.graph.generate_structured_response", return_value=None):
        result = extract_entities_batch(["section one text", "section two text"])
    assert result == [[], []]


def test_extract_entities_batch_maps_results_back_by_index():
    response = {
        "sections": [
            {"index": 1, "entities": ["Emergency Stop", "SCARA", "600 hours"]},
            {"index": 2, "entities": []},
        ]
    }
    with patch("src.graph.generate_structured_response", return_value=response):
        result = extract_entities_batch(["section one text", "section two text"])
    assert result == [["Emergency Stop", "SCARA", "600 hours"], []]


def test_extract_entities_batch_defaults_a_missing_index_to_empty():
    # The model omitting an entry for a section (rather than returning an
    # explicit empty array) must fall back to [] instead of crashing or
    # misaligning the rest of the results.
    response = {"sections": [{"index": 2, "entities": ["Only section two"]}]}
    with patch("src.graph.generate_structured_response", return_value=response):
        result = extract_entities_batch(["section one text", "section two text"])
    assert result == [[], ["Only section two"]]


def test_extract_entities_batch_caps_at_eight_per_section():
    entities = [f"term-{i}" for i in range(12)]
    response = {"sections": [{"index": 1, "entities": entities}]}
    with patch("src.graph.generate_structured_response", return_value=response):
        result = extract_entities_batch(["section one text"])
    assert len(result[0]) == 8


def test_extract_entities_batch_filters_non_scalar_entries():
    response = {"sections": [{"index": 1, "entities": ["Emergency Stop", 600, None, {"nested": "x"}, "SCARA"]}]}
    with patch("src.graph.generate_structured_response", return_value=response):
        result = extract_entities_batch(["section one text"])
    assert result[0] == ["Emergency Stop", "600", "SCARA"]


# --- build_document_graph ---------------------------------------------------


def test_build_document_graph_skips_sections_with_no_content():
    doc_id = "doc-graph-empty"
    section = KnowledgeNode(doc_id=doc_id, type=NodeType.SECTION, heading_path="Intro")
    insert_nodes([section])

    with patch("src.graph.extract_entities_batch") as mock_extract:
        processed = build_document_graph(doc_id, [section])

    assert processed == 1
    mock_extract.assert_not_called()


def test_build_document_graph_skips_when_fewer_than_two_entities():
    doc_id = "doc-graph-one-entity"
    section = KnowledgeNode(doc_id=doc_id, type=NodeType.SECTION, heading_path="Intro")
    child = KnowledgeNode(doc_id=doc_id, parent_id=section.id, type=NodeType.PARAGRAPH, content=LONG_ENOUGH_TEXT)
    insert_nodes([section, child])

    with (
        patch("src.graph.extract_entities_batch", return_value=[["only-one"]]),
        patch("src.graph.upsert_entity") as mock_upsert_entity,
    ):
        build_document_graph(doc_id, [section])
    mock_upsert_entity.assert_not_called()


def test_build_document_graph_upserts_entities_and_pairwise_edges():
    doc_id = "doc-graph-three-entities"
    section = KnowledgeNode(doc_id=doc_id, type=NodeType.SECTION, heading_path="Intro")
    child = KnowledgeNode(doc_id=doc_id, parent_id=section.id, type=NodeType.PARAGRAPH, content=LONG_ENOUGH_TEXT)
    insert_nodes([section, child])

    with (
        patch("src.graph.extract_entities_batch", return_value=[["A", "B", "C"]]),
        patch("src.graph.upsert_entity", side_effect=[1, 2, 3]) as mock_upsert_entity,
        patch("src.graph.upsert_edge") as mock_upsert_edge,
    ):
        build_document_graph(doc_id, [section])

    assert mock_upsert_entity.call_count == 3
    # 3 entities -> 3 pairwise edges (1-2, 1-3, 2-3).
    assert mock_upsert_edge.call_count == 3


def test_build_document_graph_batches_many_sections_into_fewer_calls():
    # GRAPH_BATCH_SIZE is 5 - 7 sections should take 2 extract_entities_batch
    # calls (one call per batch, not one call per section).
    doc_id = "doc-graph-many-sections"
    sections = []
    for i in range(7):
        section = KnowledgeNode(doc_id=doc_id, type=NodeType.SECTION, heading_path=f"Section {i}")
        child = KnowledgeNode(doc_id=doc_id, parent_id=section.id, type=NodeType.PARAGRAPH, content=LONG_ENOUGH_TEXT)
        insert_nodes([section, child])
        sections.append(section)

    with patch("src.graph.extract_entities_batch", return_value=[[] for _ in range(5)]) as mock_extract:
        processed = build_document_graph(doc_id, sections)

    assert processed == 7
    assert mock_extract.call_count == 2


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
