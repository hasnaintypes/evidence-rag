"""Tests for #27: when doc_ids is given (every real chat request),
hybrid_retrieve() must score only chunks from those documents, fetched
directly via get_chunks_for_sparse_by_doc_ids() (WHERE doc_id IN (...)),
instead of scoring/caching the whole corpus and filtering afterward. The
doc_ids=None path (scripts/run_eval.py's full-corpus search) must keep
using the existing global cache unchanged."""

from unittest.mock import patch

import pytest

import src.retrieval.hybrid as hybrid
from src.storage.database import insert_chunk


def _chunk(doc_id, chunk_index, text, embedding):
    return (
        {
            "chunk_text": text,
            "metadata": {
                "doc_id": doc_id,
                "source_file": f"{doc_id}.pdf",
                "page_number": 1,
                "chunk_index": chunk_index,
                "node_type": "paragraph",
                "heading_path": "Intro",
            },
        },
        embedding,
    )


def test_a_scoped_request_never_touches_the_global_cache():
    """A doc_ids-given call must not fetch/score the full corpus at all -
    not get_all_chunks_for_sparse(), the global cache's fetch function."""
    chunk, embedding = _chunk("doc-1", 0, "grease the spindle every 600 hours", [1.0, 0.0, 0.0])
    insert_chunk(chunk, embedding)

    with patch("src.retrieval.hybrid.get_all_chunks_for_sparse") as mock_global_fetch:
        results = hybrid.hybrid_retrieve(
            query_text="grease", query_embedding=[1.0, 0.0, 0.0], top_k=5, doc_ids=["doc-1"]
        )

    mock_global_fetch.assert_not_called()
    assert results
    assert results[0]["chunk_text"] == "grease the spindle every 600 hours"


def test_a_scoped_requests_count_query_is_filtered_to_doc_ids():
    """The scoped path's own staleness check must count only this
    scope's chunks, not the whole document_chunks table."""
    in_scope, in_scope_emb = _chunk("doc-1", 0, "grease the spindle every 600 hours", [1.0, 0.0, 0.0])
    insert_chunk(in_scope, in_scope_emb)
    out_of_scope, out_of_scope_emb = _chunk("doc-2", 0, "replace the air filter annually", [0.0, 1.0, 0.0])
    insert_chunk(out_of_scope, out_of_scope_emb)

    scoped = hybrid._get_scoped_index(["doc-1"])
    assert scoped["chunk_count"] == 1


def test_repeated_calls_against_the_same_scope_reuse_the_cached_index():
    """A conversation's follow-up turns against the same doc_ids must not
    rebuild BM25 from scratch every message."""
    chunk, embedding = _chunk("doc-1", 0, "grease the spindle every 600 hours", [1.0, 0.0, 0.0])
    insert_chunk(chunk, embedding)

    with patch(
        "src.retrieval.hybrid.get_chunks_for_sparse_by_doc_ids", wraps=hybrid.get_chunks_for_sparse_by_doc_ids
    ) as mock_fetch:
        hybrid.hybrid_retrieve(query_text="grease", query_embedding=[1.0, 0.0, 0.0], top_k=5, doc_ids=["doc-1"])
        hybrid.hybrid_retrieve(query_text="grease", query_embedding=[1.0, 0.0, 0.0], top_k=5, doc_ids=["doc-1"])
        hybrid.hybrid_retrieve(query_text="grease", query_embedding=[1.0, 0.0, 0.0], top_k=5, doc_ids=["doc-1"])

    mock_fetch.assert_called_once()


def test_a_scope_cache_hit_is_invalidated_once_that_scopes_chunk_count_changes():
    chunk, embedding = _chunk("doc-1", 0, "grease the spindle every 600 hours", [1.0, 0.0, 0.0])
    insert_chunk(chunk, embedding)
    hybrid.hybrid_retrieve(query_text="grease", query_embedding=[1.0, 0.0, 0.0], top_k=5, doc_ids=["doc-1"])
    assert hybrid._scoped_cache[("doc-1",)]["chunk_count"] == 1

    second_chunk, second_embedding = _chunk("doc-1", 1, "also check the coolant filter", [0.0, 0.0, 1.0])
    insert_chunk(second_chunk, second_embedding)
    results = hybrid.hybrid_retrieve(query_text="coolant", query_embedding=[0.0, 0.0, 1.0], top_k=5, doc_ids=["doc-1"])

    assert hybrid._scoped_cache[("doc-1",)]["chunk_count"] == 2
    assert any(r["chunk_text"] == "also check the coolant filter" for r in results)


def test_a_scoped_request_ignores_chunks_outside_doc_ids_even_if_they_score_higher():
    """A chunk from a document outside doc_ids that would otherwise be
    the clear top match (exact keyword + exact embedding match) must
    never appear - it's excluded at the DB query level, not just at the
    end of the ranking."""
    in_scope, in_scope_emb = _chunk("doc-1", 0, "replace the air filter annually", [0.0, 1.0, 0.0])
    insert_chunk(in_scope, in_scope_emb)
    out_of_scope, out_of_scope_emb = _chunk("doc-2", 0, "grease the spindle every 600 hours", [1.0, 0.0, 0.0])
    insert_chunk(out_of_scope, out_of_scope_emb)

    results = hybrid.hybrid_retrieve(query_text="grease", query_embedding=[1.0, 0.0, 0.0], top_k=5, doc_ids=["doc-1"])

    assert all(r["doc_id"] == "doc-1" for r in results)
    assert "grease" not in " ".join(r["chunk_text"] for r in results)


def test_an_unscoped_request_still_uses_the_global_cache():
    """doc_ids omitted (the full-corpus search path, e.g.
    scripts/run_eval.py) must still go through get_all_chunks_for_sparse()/
    the cached index, not the new scoped fetch - no regression for that
    path."""
    chunk, embedding = _chunk("doc-1", 0, "grease the spindle every 600 hours", [1.0, 0.0, 0.0])
    insert_chunk(chunk, embedding)

    with patch("src.retrieval.hybrid.get_chunks_for_sparse_by_doc_ids") as mock_scoped_fetch:
        results = hybrid.hybrid_retrieve(query_text="grease", query_embedding=[1.0, 0.0, 0.0], top_k=5)

    mock_scoped_fetch.assert_not_called()
    assert results
    assert results[0]["chunk_text"] == "grease the spindle every 600 hours"


def test_a_scoped_request_still_catches_an_embedding_model_mismatch():
    """The embedding-dimension-mismatch guard (see _build_bm25_and_matrix's
    docstring) must still run on a cache miss for the scoped path too,
    not just the full-corpus one - otherwise a mismatch would surface as
    a confusing numpy error deep inside the matrix multiply instead of
    this clear one, on every real chat request (every one passes
    doc_ids)."""
    chunk, embedding = _chunk("doc-1", 0, "grease the spindle every 600 hours", [1.0, 0.0, 0.0])
    insert_chunk(chunk, embedding)

    with patch("src.retrieval.hybrid.get_indexed_embedding_models", return_value=["some-other-model"]):
        with pytest.raises(RuntimeError, match="Embedding model mismatch"):
            hybrid.hybrid_retrieve(query_text="grease", query_embedding=[1.0, 0.0, 0.0], top_k=5, doc_ids=["doc-1"])


def test_a_scoped_request_spanning_multiple_documents_includes_both():
    doc1_chunk, doc1_emb = _chunk("doc-1", 0, "grease the spindle every 600 hours", [1.0, 0.0, 0.0])
    insert_chunk(doc1_chunk, doc1_emb)
    doc2_chunk, doc2_emb = _chunk("doc-2", 0, "grease fittings need monthly attention", [0.9, 0.1, 0.0])
    insert_chunk(doc2_chunk, doc2_emb)
    other_doc_chunk, other_emb = _chunk("doc-3", 0, "grease is also mentioned here", [0.9, 0.0, 0.1])
    insert_chunk(other_doc_chunk, other_emb)

    results = hybrid.hybrid_retrieve(
        query_text="grease", query_embedding=[1.0, 0.0, 0.0], top_k=5, doc_ids=["doc-1", "doc-2"]
    )

    result_doc_ids = {r["doc_id"] for r in results}
    assert result_doc_ids == {"doc-1", "doc-2"}
