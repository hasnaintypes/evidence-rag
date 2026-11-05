from collections import OrderedDict

import numpy as np
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi

from src.config import settings
from src.storage.database import (
    dense_ann_search,
    get_all_chunks_for_sparse,
    get_chunks_for_sparse_by_doc_ids,
    get_db_connection,
    get_indexed_embedding_models,
)
from src.llm import EMBEDDING_MODEL_NAME

# --------------------------------------------------------------------------- #
# In-memory index cache - full-corpus (doc_ids=None) path only
#
# Rebuilding BM25 from scratch and computing cosine similarity in a Python
# loop on every single query does not scale past a few hundred chunks - at
# a few thousand chunks this alone can take seconds per query. The index
# only actually changes when ingest.py adds/removes chunks, so it should be
# built once and reused, not rebuilt per request.
#
# Staleness check: a cheap COUNT(*) against document_chunks. If it differs
# from what the cache was built with, the corpus changed (new ingestion
# run) and we rebuild. This avoids needing to manually call an invalidate
# function from ingest.py, at the cost of one lightweight COUNT query per
# doc_ids=None hybrid_retrieve() call.
#
# Every real chat request passes doc_ids (a conversation's 1-5 documents)
# and never touches this cache at all - it builds/reuses a fresh,
# unscaled-with-total-corpus-size index scoped to just those documents
# instead (see the per-scope cache below and #27). Only
# scripts/run_eval.py's doc_ids=None full-corpus search still uses this.
# --------------------------------------------------------------------------- #

_cache: Dict[str, Any] = {
    "chunk_count": None,
    "chunks": None,  # List[Dict] - full chunk payloads, index-aligned with embedding_matrix
    "bm25": None,  # BM25Okapi instance built once
    "embedding_matrix": None,  # np.ndarray, shape (n_chunks, dim), L2-normalized rows
}

# --------------------------------------------------------------------------- #
# Per-scope index cache - doc_ids-given (real chat request) path
#
# A conversation stays on the same 1-5 document doc_ids for every turn,
# so without caching, a multi-turn conversation against a large document
# would re-tokenize every chunk and rebuild a fresh BM25Okapi object on
# every single message - repeated CPU work on the chat request's hot
# path for no reason, since nothing about that scope changed between
# turns. Keyed by the sorted doc_ids tuple (order shouldn't matter to
# cache identity) and bounded to _SCOPED_CACHE_MAX_ENTRIES
# least-recently-used scopes, since unlike the single global cache
# above, a busy server could otherwise accumulate one entry per distinct
# doc_ids set ever queried, unbounded.
# --------------------------------------------------------------------------- #

_SCOPED_CACHE_MAX_ENTRIES = 20
_scoped_cache: "OrderedDict[tuple, Dict[str, Any]]" = OrderedDict()


def _current_chunk_count(doc_ids: Optional[List[str]] = None) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    if doc_ids:
        mark = "%s" if settings.storage_mode == "supabase" else "?"
        placeholders = ", ".join([mark] * len(doc_ids))
        cursor.execute(f"SELECT COUNT(*) as cnt FROM document_chunks WHERE doc_id IN ({placeholders})", tuple(doc_ids))
    else:
        cursor.execute("SELECT COUNT(*) as cnt FROM document_chunks")
    count = cursor.fetchone()["cnt"]
    conn.close()
    return count


def _build_bm25_and_matrix(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Builds a BM25 index and (local/SQLite mode only) a normalized dense
    embedding matrix from an arbitrary chunk list. Shared by the global
    cached index below (_build_index(), the full corpus - doc_ids=None
    callers only, e.g. scripts/run_eval.py) and the per-scope cached
    index (_get_scoped_index(), a conversation's <=5 documents - #27).
    Only called on an actual cache miss/rebuild in both cases, not per
    request, so the extra get_indexed_embedding_models() query below is
    cheap in practice despite running on every miss.

    Callers must not call this with an empty chunks list - both cache
    paths short-circuit that case themselves before reaching here.
    """
    # Guard against silently mixing incompatible embedding dimensions -
    # e.g. switching MODE from local (384-dim MiniLM) to cloud (1536-dim
    # Azure) without re-ingesting. Without this check, the mismatch would
    # only surface as a numpy shape-mismatch crash deep inside the
    # embedding_matrix @ query_vec multiplication below, which is much
    # harder to diagnose than a clear error raised here at index build time.
    indexed_models = get_indexed_embedding_models()
    if indexed_models and EMBEDDING_MODEL_NAME not in indexed_models:
        raise RuntimeError(
            f"Embedding model mismatch: current mode uses '{EMBEDDING_MODEL_NAME}', "
            f"but the indexed documents were embedded with {indexed_models}. "
            f"Re-run ingestion (scripts/ingest.py) after switching modes, or "
            f"switch MODE back to match the indexed embedding model."
        )

    corpus_tokenized = [chunk["chunk_text"].lower().split() for chunk in chunks]
    bm25 = BM25Okapi(corpus_tokenized)

    # Dense retrieval in supabase mode queries pgvector directly via
    # dense_ann_search() (a real ANN query against the HNSW index - see
    # hybrid_retrieve() below), so building an in-memory matrix here
    # would be pure waste: a (n_chunks, 3072) float32 copy of embeddings
    # that nothing would ever read. Local/SQLite mode has no pgvector
    # extension, so it keeps the original in-memory cosine-similarity
    # path and needs the matrix built here as before.
    embedding_matrix = None
    if settings.storage_mode != "supabase":
        # Build a single (n_chunks, dim) matrix and normalize each row once
        # here, instead of computing norms per-chunk on every query. With
        # normalized rows, cosine similarity against a normalized query
        # vector reduces to a single matrix-vector dot product.
        embedding_matrix = np.array([chunk["embedding"] for chunk in chunks], dtype=np.float32)
        norms = np.linalg.norm(embedding_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1e-10  # guard against zero-vector edge case
        embedding_matrix = embedding_matrix / norms

    return {"bm25": bm25, "embedding_matrix": embedding_matrix}


def _build_index() -> None:
    """Fetches every chunk in the corpus once and builds both the BM25
    index and a normalized dense embedding matrix, cached for reuse
    across doc_ids=None calls (the full-corpus search path - see
    hybrid_retrieve())."""
    all_chunks = get_all_chunks_for_sparse()

    if not all_chunks:
        _cache.update(chunk_count=0, chunks=[], bm25=None, embedding_matrix=None)
        return

    built = _build_bm25_and_matrix(all_chunks)
    _cache.update(chunk_count=len(all_chunks), chunks=all_chunks, **built)


def _get_index() -> Dict[str, Any]:
    """Returns the cached index, rebuilding it if the corpus size changed
    since it was last built (i.e. ingest.py added/removed chunks)."""
    live_count = _current_chunk_count()
    if _cache["chunk_count"] != live_count:
        _build_index()
    return _cache


def _get_scoped_index(doc_ids: List[str]) -> Dict[str, Any]:
    """
    Per-scope equivalent of _get_index() above, for the doc_ids-given
    (real chat request) path - see #27. Keyed by the sorted doc_ids
    tuple, rebuilt only when that scope's own chunk count has changed
    since it was cached (same COUNT(*)-staleness pattern as the global
    cache, just filtered to this scope's doc_ids), and evicted
    least-recently-used once _SCOPED_CACHE_MAX_ENTRIES distinct scopes
    have been cached.
    """
    key = tuple(sorted(doc_ids))
    live_count = _current_chunk_count(doc_ids)
    cached = _scoped_cache.get(key)
    if cached is not None and cached["chunk_count"] == live_count:
        _scoped_cache.move_to_end(key)
        return cached

    if live_count == 0:
        entry = {"chunk_count": 0, "chunks": [], "bm25": None, "embedding_matrix": None}
    else:
        all_chunks = get_chunks_for_sparse_by_doc_ids(doc_ids)
        built = _build_bm25_and_matrix(all_chunks)
        entry = {"chunk_count": len(all_chunks), "chunks": all_chunks, **built}

    _scoped_cache[key] = entry
    _scoped_cache.move_to_end(key)
    if len(_scoped_cache) > _SCOPED_CACHE_MAX_ENTRIES:
        _scoped_cache.popitem(last=False)
    return entry


def invalidate_index_cache() -> None:
    """
    Explicit cache invalidation hook for both caches above. The COUNT(*)
    checks in _get_index()/_get_scoped_index() already catch added/
    removed chunks automatically, but they'd miss an edit that replaces
    content without changing the row count (e.g. re-ingest, rename -
    see api/services/document_service.py). Call this after any such
    write to document_chunks to be safe.
    """
    _cache.update(chunk_count=None, chunks=None, bm25=None, embedding_matrix=None)
    _scoped_cache.clear()


def hybrid_retrieve(
    query_text: str,
    query_embedding: List[float],
    top_k: int = 5,
    rrf_k: int = 60,
    doc_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Executes hybrid search combining BM25 (sparse) and dense cosine
    similarity, fused via Reciprocal Rank Fusion (RRF).

    Args:
        query_text: Raw string question for sparse keyword matching.
        query_embedding: Query vector for dense semantic similarity.
        top_k: Number of top fused results to return.
        rrf_k: RRF penalty constant controlling rank-position weighting.
        doc_ids: When given (every real chat request - conversations are
            always scoped to 1-5 documents), both layers are scoped
            directly in SQL instead of ranking the full corpus and
            filtering afterward (#27): sparse (BM25) and, in local/SQLite
            mode, the dense matrix are built from just
            get_chunks_for_sparse_by_doc_ids(doc_ids)'s rows, cached
            per-scope (_get_scoped_index()) so a conversation's repeated
            turns against the same documents don't rebuild BM25 from
            scratch every message. Dense retrieval in supabase mode was
            already scoped this way via dense_ann_search()'s own
            WHERE doc_id = ANY(...) (#17). When doc_ids is omitted (only
            scripts/run_eval.py today), both layers fall back to the
            full-corpus cached index below.
    """
    if doc_ids:
        scoped = _get_scoped_index(doc_ids)
        all_chunks: Optional[List[Dict[str, Any]]] = scoped["chunks"]
        if not all_chunks:
            return []
        bm25: BM25Okapi = scoped["bm25"]
        embedding_matrix: Optional[np.ndarray] = scoped["embedding_matrix"]
    else:
        index = _get_index()
        all_chunks = index["chunks"]
        if not all_chunks:
            return []
        bm25 = index["bm25"]
        embedding_matrix = index["embedding_matrix"]

    # --- LAYER 1: SPARSE RETRIEVAL (BM25) ---
    query_tokens = query_text.lower().split()
    bm25_scores = bm25.get_scores(query_tokens)
    sparse_ranked_indices = np.argsort(bm25_scores)[::-1]

    sparse_ranks: Dict[Any, int] = {}
    for rank_idx, chunk_arr_idx in enumerate(sparse_ranked_indices):
        if bm25_scores[chunk_arr_idx] > 0:
            chunk_id = all_chunks[chunk_arr_idx]["id"]
            sparse_ranks[chunk_id] = rank_idx + 1

    # --- LAYER 2: DENSE RETRIEVAL ---
    if settings.storage_mode == "supabase":
        # Real ANN search against pgvector's HNSW-indexed column - see
        # dense_ann_search()'s docstring. Asks for a wider candidate set
        # than top_k so RRF still has a meaningful rank spread to fuse
        # against the sparse side, the same reason the sparse layer above
        # tracks every chunk with a positive BM25 score rather than just
        # the eventual top_k.
        dense_candidate_k = max(top_k * 4, 50)
        ann_hits = dense_ann_search(query_embedding, top_k=dense_candidate_k, doc_ids=doc_ids)
        dense_ranks: Dict[Any, int] = {hit["id"]: rank_idx + 1 for rank_idx, hit in enumerate(ann_hits)}
    else:
        query_vec = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            query_norm = 1e-10
        query_vec = query_vec / query_norm

        # embedding_matrix rows are already normalized -> this dot product
        # IS the cosine similarity for every chunk at once, no Python loop.
        dense_scores = embedding_matrix @ query_vec
        dense_ranked_indices = np.argsort(dense_scores)[::-1]

        dense_ranks = {
            all_chunks[chunk_arr_idx]["id"]: rank_idx + 1 for rank_idx, chunk_arr_idx in enumerate(dense_ranked_indices)
        }

    # --- LAYER 3: RECIPROCAL RANK FUSION ---
    rrf_scores: Dict[Any, float] = {}
    for chunk in all_chunks:
        c_id = chunk["id"]
        sparse_rank = sparse_ranks.get(c_id)
        sparse_score = 1.0 / (rrf_k + sparse_rank) if sparse_rank is not None else 0.0
        dense_rank = dense_ranks.get(c_id)
        dense_score = 1.0 / (rrf_k + dense_rank) if dense_rank is not None else 0.0
        rrf_scores[c_id] = sparse_score + dense_score

    sorted_chunks_by_rrf = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    # No post-hoc doc_ids filter needed here anymore (#27): all_chunks is
    # already exactly the doc_ids scope when doc_ids was given (both
    # layers were built from get_chunks_for_sparse_by_doc_ids() above),
    # and the full corpus otherwise - there's nothing left to filter out.
    chunk_map = {chunk["id"]: chunk for chunk in all_chunks}

    final_retrieved_chunks = []
    for chunk_id, rrf_final_score in sorted_chunks_by_rrf[:top_k]:
        target_chunk = dict(chunk_map[chunk_id])  # shallow copy, avoid mutating the cached chunk
        target_chunk["rrf_score"] = rrf_final_score
        target_chunk["dense_rank"] = dense_ranks.get(chunk_id, -1)
        target_chunk["sparse_rank"] = sparse_ranks.get(chunk_id, -1)
        final_retrieved_chunks.append(target_chunk)

    return final_retrieved_chunks
