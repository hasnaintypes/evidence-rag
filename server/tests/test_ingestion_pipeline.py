"""
Regression coverage for #46: a re-ingest whose background embedding fails
partway through must leave the document's previously-indexed chunks intact,
not deleted. See src/ingestion/pipeline.py's prepare_ingest()/finish_ingest()
docstrings for the fix - the old-data delete is deferred from prepare_ingest
to finish_ingest, and only runs once every chunk's embedding has already
succeeded.
"""

from unittest.mock import patch

import pytest

from src.ingestion.pipeline import prepare_ingest, finish_ingest
from src.retrieval.hybrid import _get_scoped_index
from src.storage.database import get_chunks_for_sparse_by_doc_ids, get_document_status

MARKDOWN_CONTENT = """# Section One

Some paragraph content that is long enough to be chunked on its own.

# Section Two

More paragraph content, also long enough to survive chunking as a block.
"""


def _write_md(tmp_path, name="doc.md", content=MARKDOWN_CONTENT):
    file_path = tmp_path / name
    file_path.write_text(content)
    return str(file_path)


def _write_section_one(tmp_path, text):
    """Same two-section shape as MARKDOWN_CONTENT, with only section one's
    wording changed - used to force a content edit that doesn't change the
    resulting chunk count."""
    content = f"""# Section One

{text} Padded so this paragraph survives chunking as its own block.

# Section Two

Unrelated paragraph content, also long enough to survive chunking as a block.
"""
    return _write_md(tmp_path, content=content)


def _fake_embedding():
    return [0.0] * 8


def _ingest(file_path, filename="doc.md", force=False):
    with patch("src.ingestion.pipeline.get_embedding", return_value=_fake_embedding()):
        prep = prepare_ingest(file_path, filename, force=force)
        assert prep["status"] == "ready_to_index"
        result = finish_ingest(
            prep["doc_id"], prep["chunks_data"], nodes=prep.get("nodes"), is_replace=prep["is_replace"]
        )
        assert result["status"] == "success"
    return prep


def test_failed_reembedding_preserves_previous_chunks(tmp_path):
    file_path = _write_md(tmp_path)
    prep = _ingest(file_path)

    doc_id = prep["doc_id"]
    original_chunks = get_chunks_for_sparse_by_doc_ids([doc_id])
    assert len(original_chunks) > 0

    # Re-ingest the same (unchanged) content with force=True, as the
    # "re-ingest" button does - but this time the embedding call fails
    # partway through the chunk list.
    with patch("src.ingestion.pipeline.get_embedding", side_effect=RuntimeError("quota exceeded")):
        prep2 = prepare_ingest(file_path, "doc.md", force=True)
        assert prep2["status"] == "ready_to_index"
        assert prep2["is_replace"] is True

        with pytest.raises(RuntimeError):
            finish_ingest(
                prep2["doc_id"],
                prep2["chunks_data"],
                nodes=prep2.get("nodes"),
                is_replace=prep2["is_replace"],
            )

    # The document is marked failed, but its previous, working chunks are
    # still there rather than wiped out by the failed re-embedding attempt.
    status = get_document_status(doc_id)
    assert status["status"] == "failed"

    surviving_chunks = get_chunks_for_sparse_by_doc_ids([doc_id])
    assert len(surviving_chunks) == len(original_chunks)


def test_successful_reingest_still_replaces_old_chunks(tmp_path):
    """The fix must not break the normal, successful re-ingest path -
    old chunks should still be fully replaced when the new embeddings do
    succeed."""
    file_path = _write_md(tmp_path)
    prep = _ingest(file_path)

    doc_id = prep["doc_id"]
    first_chunk_ids = {c["id"] for c in get_chunks_for_sparse_by_doc_ids([doc_id])}

    # Change the content so the hash-based dedup doesn't short-circuit.
    new_content = MARKDOWN_CONTENT + "\n# Section Three\n\nA brand new section with its own content block.\n"
    _write_md(tmp_path, content=new_content)

    prep2 = _ingest(file_path)
    assert prep2["is_replace"] is True

    second_chunk_ids = {c["id"] for c in get_chunks_for_sparse_by_doc_ids([doc_id])}
    assert first_chunk_ids.isdisjoint(second_chunk_ids)


def test_reingest_invalidates_scoped_cache_even_when_chunk_count_is_unchanged(tmp_path):
    """retrieval/hybrid.py's per-scope index cache treats an unchanged
    document_chunks COUNT(*) as "nothing changed" (see its docstring) - an
    edit that doesn't add/remove chunks would sail past that check unless
    something explicitly invalidates the cache at the actual delete+insert
    swap. That swap now happens inside finish_ingest() itself (deferred
    from prepare_ingest, #46), so the invalidation has to live there too,
    not only in document_service.py's callers."""
    file_path = _write_section_one(tmp_path, "Original wording for section one.")
    prep = _ingest(file_path)
    doc_id = prep["doc_id"]

    # Populate the scoped cache with the original content.
    cached = _get_scoped_index([doc_id])
    original_count = cached["chunk_count"]
    assert any("Original wording" in c["chunk_text"] for c in cached["chunks"])

    # Re-ingest with different wording but the same section/paragraph
    # structure, so the chunk count comes out identical.
    _write_section_one(tmp_path, "Replacement wording for section one.")
    prep2 = _ingest(file_path)
    assert prep2["is_replace"] is True

    refreshed = _get_scoped_index([doc_id])
    assert refreshed["chunk_count"] == original_count
    assert any("Replacement wording" in c["chunk_text"] for c in refreshed["chunks"])
    assert not any("Original wording" in c["chunk_text"] for c in refreshed["chunks"])
