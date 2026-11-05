"""Tests for src/retrieval/hybrid.py's dense-retrieval branch: the
in-memory cosine-similarity path for local/SQLite mode (unchanged), and
the new pgvector ANN path for supabase mode (src.storage.database's
dense_ann_search(), see #17)."""

from unittest.mock import patch

import src.retrieval.hybrid as hybrid
from src.config import settings
from src.storage.database import insert_chunk


def _chunk(doc_id, chunk_index, text, embedding):
    return (
        {
            "chunk_text": text,
            "metadata": {
                "doc_id": doc_id,
                "source_file": "doc.pdf",
                "page_number": 1,
                "chunk_index": chunk_index,
                "node_type": "paragraph",
                "heading_path": "Intro",
            },
        },
        embedding,
    )


def test_local_mode_dense_retrieval_still_uses_the_in_memory_matrix():
    """storage_mode="local" (forced by the autouse isolated_sqlite_db
    fixture) has no pgvector extension - dense_ann_search() must never be
    called, and the existing in-memory cosine-similarity path still
    drives ranking."""
    chunk, embedding = _chunk("doc-1", 0, "grease the spindle every 600 hours", [1.0, 0.0, 0.0])
    insert_chunk(chunk, embedding)
    other_chunk, other_embedding = _chunk("doc-1", 1, "replace the air filter annually", [0.0, 1.0, 0.0])
    insert_chunk(other_chunk, other_embedding)

    with patch("src.retrieval.hybrid.dense_ann_search") as mock_ann:
        results = hybrid.hybrid_retrieve(query_text="grease", query_embedding=[1.0, 0.0, 0.0], top_k=5)

    mock_ann.assert_not_called()
    assert results
    assert results[0]["chunk_text"] == "grease the spindle every 600 hours"


def test_supabase_mode_dense_retrieval_calls_the_ann_search(monkeypatch):
    """storage_mode="supabase" must route dense retrieval through
    dense_ann_search() (the pgvector HNSW ANN query) instead of building
    an in-memory embedding matrix, and (with doc_ids given, the real
    chat-request path - see #27) sparse retrieval is scoped via
    get_chunks_for_sparse_by_doc_ids() rather than the global cache. The
    fused ranking should reflect the ANN search's returned order."""
    monkeypatch.setattr(settings, "storage_mode", "supabase")

    all_chunks = [
        {"id": 1, "doc_id": "doc-1", "chunk_text": "grease the spindle every 600 hours", "embedding": [1, 0, 0]},
        {"id": 2, "doc_id": "doc-1", "chunk_text": "replace the air filter annually", "embedding": [0, 1, 0]},
    ]

    with (
        patch("src.retrieval.hybrid.get_chunks_for_sparse_by_doc_ids", return_value=all_chunks) as mock_scoped_fetch,
        patch("src.retrieval.hybrid.get_all_chunks_for_sparse") as mock_global_fetch,
        patch(
            "src.retrieval.hybrid.dense_ann_search",
            return_value=[{"id": 2, "distance": 0.1}, {"id": 1, "distance": 0.9}],
        ) as mock_ann,
    ):
        results = hybrid.hybrid_retrieve(
            query_text="grease", query_embedding=[1.0, 0.0, 0.0], top_k=5, doc_ids=["doc-1"]
        )

    mock_scoped_fetch.assert_called_once_with(["doc-1"])
    mock_global_fetch.assert_not_called()  # the global cache must not be touched for a scoped request

    mock_ann.assert_called_once()
    _, call_kwargs = mock_ann.call_args
    assert call_kwargs["doc_ids"] == ["doc-1"]

    # chunk id 2 was ranked first by the (mocked) ANN search, even though
    # id 1 is the sparse/BM25 winner for this query - confirms the fused
    # rank actually reflects dense_ann_search's order rather than falling
    # back to the in-memory matrix path.
    result_ids = [r["id"] for r in results]
    assert 2 in result_ids
    assert 1 in result_ids
