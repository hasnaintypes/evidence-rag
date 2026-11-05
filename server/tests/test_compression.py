"""Tests for src/retrieval/compression.py's rerank_score-gated branches.

Regression coverage for a threshold recalibration bug caught by code
review: compress_context_chunks()'s high-confidence full-text-retention
branch was left at its old cross-encoder-scale cutoff (> 1.5) when
retrieval/reranker.py's score scale changed to a clamped 0.0-1.0 range,
making the branch permanently unreachable - see #20."""

from unittest.mock import patch

from src.retrieval.compression import compress_context_chunks


def _chunk(rerank_score, text="Sentence one. Sentence two about something else entirely."):
    return {
        "chunk_text": text,
        "node_type": "paragraph",
        "page_number": 5,
        "rerank_score": rerank_score,
        "parent_id": None,
    }


def test_a_high_confidence_chunk_keeps_its_full_text_untrimmed():
    """rerank_score is clamped to [0.0, 1.0] (see reranker.py) - 0.9+ is
    a real, reachable value a Gemini call can actually return, and must
    skip sentence-window trimming."""
    chunk = _chunk(rerank_score=0.95)
    with patch("src.retrieval.compression._attach_parent_context"):
        result = compress_context_chunks(query="something else", chunks=[chunk])
    assert len(result) == 1
    assert result[0]["chunk_text"] == chunk["chunk_text"]


def test_a_moderate_confidence_chunk_still_gets_sentence_window_trimmed():
    text = (
        "Opening filler sentence one. Opening filler sentence two. "
        "Mentions something else here. "
        "Closing filler sentence one. Closing filler sentence two."
    )
    chunk = _chunk(rerank_score=0.6, text=text)
    with patch("src.retrieval.compression._attach_parent_context"):
        result = compress_context_chunks(query="something else", chunks=[chunk])
    assert len(result) == 1
    # compress_context_chunks() mutates the chunk dict in place and
    # returns the same object, so compare against the original text
    # captured before the call, not chunk["chunk_text"] afterward.
    assert result[0]["chunk_text"] != text
    assert "something else" in result[0]["chunk_text"]
