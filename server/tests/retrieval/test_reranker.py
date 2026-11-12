"""Tests for src/retrieval/reranker.py's Cloudflare-based reranking (replaces
a locally-hosted cross-encoder - see #20, the OOM fix)."""

from unittest.mock import patch

from src.retrieval.reranker import rerank_chunks


def _chunk(text):
    return {"chunk_text": text}


def test_empty_chunks_returns_empty_without_calling_cloudflare():
    with patch("src.retrieval.reranker.generate_cloudflare_json") as mock_call:
        result = rerank_chunks(query="q", chunks=[])
    mock_call.assert_not_called()
    assert result == []


def test_chunks_are_sorted_by_the_returned_relevance_score():
    chunks = [_chunk("low relevance"), _chunk("high relevance"), _chunk("mid relevance")]
    cloudflare_response = {
        "scores": [
            {"index": 1, "relevance": 0.1},
            {"index": 2, "relevance": 0.9},
            {"index": 3, "relevance": 0.5},
        ]
    }
    with patch("src.retrieval.reranker.generate_cloudflare_json", return_value=cloudflare_response):
        result = rerank_chunks(query="q", chunks=chunks, top_n=4)

    assert [c["chunk_text"] for c in result] == ["high relevance", "mid relevance", "low relevance"]
    assert result[0]["rerank_score"] == 0.9


def test_top_n_truncates_the_result():
    chunks = [_chunk(f"chunk {i}") for i in range(5)]
    cloudflare_response = {"scores": [{"index": i + 1, "relevance": 1.0 - i * 0.1} for i in range(5)]}
    with patch("src.retrieval.reranker.generate_cloudflare_json", return_value=cloudflare_response):
        result = rerank_chunks(query="q", chunks=chunks, top_n=2)
    assert len(result) == 2


def test_a_missing_index_in_the_response_falls_back_to_zero_not_a_crash():
    chunks = [_chunk("a"), _chunk("b")]
    cloudflare_response = {"scores": [{"index": 1, "relevance": 0.7}]}  # index 2 omitted
    with patch("src.retrieval.reranker.generate_cloudflare_json", return_value=cloudflare_response):
        result = rerank_chunks(query="q", chunks=chunks, top_n=4)
    scores = {c["chunk_text"]: c["rerank_score"] for c in result}
    assert scores["a"] == 0.7
    assert scores["b"] == 0.0


def test_a_total_cloudflare_failure_falls_back_to_the_original_order():
    """None (every generate_cloudflare_json() failure mode) must degrade to the
    original retrieval order, not crash or scramble the chunks."""
    chunks = [_chunk("first"), _chunk("second"), _chunk("third")]
    with patch("src.retrieval.reranker.generate_cloudflare_json", return_value=None):
        result = rerank_chunks(query="q", chunks=chunks, top_n=4)
    assert [c["chunk_text"] for c in result] == ["first", "second", "third"]
    assert all(c["rerank_score"] == 0.0 for c in result)


def test_relevance_scores_are_clamped_to_zero_one():
    chunks = [_chunk("a"), _chunk("b")]
    cloudflare_response = {"scores": [{"index": 1, "relevance": 5.0}, {"index": 2, "relevance": -3.0}]}
    with patch("src.retrieval.reranker.generate_cloudflare_json", return_value=cloudflare_response):
        result = rerank_chunks(query="q", chunks=chunks, top_n=4)
    scores = {c["chunk_text"]: c["rerank_score"] for c in result}
    assert scores["a"] == 1.0
    assert scores["b"] == 0.0
