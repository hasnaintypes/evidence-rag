"""Tests for src/storage/database.py's dense_ann_search() - specifically
that every branch casts both sides of the `<=>` comparison to
halfvec(3072), matching scripts/supabase_schema.sql's idx_chunks_embedding
HNSW index. A mismatched cast on either branch means Postgres has no
matching indexed expression and silently falls back to a full sequential
scan instead of using the index - see #17."""

from unittest.mock import MagicMock, patch

import pytest

from src.config import settings
from src.storage.database import dense_ann_search


@pytest.fixture(autouse=True)
def supabase_mode(monkeypatch):
    monkeypatch.setattr(settings, "storage_mode", "supabase")


def _run_with_fake_cursor(doc_ids):
    fake_cursor = MagicMock()
    fake_cursor.fetchall.return_value = []
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    with patch("src.storage.database.get_db_connection", return_value=fake_conn):
        dense_ann_search([0.1, 0.2, 0.3], top_k=5, doc_ids=doc_ids)

    return fake_cursor.execute.call_args[0][0]


def test_the_doc_id_filtered_branch_casts_both_sides_to_halfvec():
    sql = _run_with_fake_cursor(doc_ids=["doc-1"])
    assert "embedding::halfvec(3072) <=> %s::halfvec(3072)" in sql


def test_the_unfiltered_branch_also_casts_both_sides_to_halfvec():
    """Regression test: this branch used to order by the plain
    `embedding <=> %s::vector`, which doesn't match idx_chunks_embedding's
    indexed expression and silently falls back to a sequential scan."""
    sql = _run_with_fake_cursor(doc_ids=None)
    assert "embedding::halfvec(3072) <=> %s::halfvec(3072)" in sql
    assert "::vector" not in sql


def test_raises_outside_supabase_mode(monkeypatch):
    monkeypatch.setattr(settings, "storage_mode", "local")
    with pytest.raises(RuntimeError):
        dense_ann_search([0.1, 0.2, 0.3], top_k=5)
