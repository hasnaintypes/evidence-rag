import threading
import time
from typing import Any, Dict, List, Optional

import numpy as np

from src.config import settings

# --------------------------------------------------------------------------- #
# Semantic response cache
#
# A repeated or near-duplicate question against the same document set pays
# the full pipeline cost again - query rewriting, retrieval, rerank, grade,
# generation, and a second LLM call for faithfulness scoring - even though
# the answer would come out the same. This caches the final pipeline
# result keyed by (doc_ids, advanced_mode) and matched by cosine similarity
# against the query embedding already computed for PHASE 2, so a
# differently-worded but semantically equivalent question ("how do I reset
# the robot" vs "what's the procedure to reset the robot") can still hit.
#
# Deliberately scoped to avoid correctness risk over maximizing hit rate:
# - Only consulted/populated when `history` is empty (the first turn of a
#   conversation). A follow-up ("what about X") depends on prior turns, so
#   caching it under the bare query embedding could serve a stale/wrong
#   answer for a differently-contexted repeat of the same words. Caching
#   history-dependent turns is a possible future extension, not attempted
#   here.
# - Only a fully-successful, non-gated result is cached - not an empty-
#   retrieval reply, not an abstained-confidence reply, not a
#   faithfulness-gated withheld answer, and not a generation failure.
#   Pipeline-level failures are frequently transient (a rate-limited
#   Gemini call, a flaky retrieval), and caching one would make a user's
#   retry deterministically see the exact same failure instead of a fresh
#   attempt that might succeed.
# - In-memory, per-process only - not shared across workers or persisted
#   across a restart. Consistent with hybrid.py's existing in-memory index
#   cache; revisit alongside the multi-worker/horizontal-scaling work
#   already tracked in #20/#27 if this ever needs to be shared.
#
# Safe to share across different users/conversations: doc_ids scoping here
# mirrors the same doc_ids every caller already had to be authorized for
# before process_chat_query() was invoked (see
# api/routers/conversations.py's all_documents_accessible check) - serving
# a cached answer for the same exact doc_ids set doesn't expose anything a
# second authorized caller couldn't already see. Cached `sources` entries
# still get a fresh per-user signed source_token at serve time (see
# query_pipeline.py) rather than reusing whoever's token first populated
# the cache entry.
# --------------------------------------------------------------------------- #

_ENTRY_TIMESTAMP = "_cached_at"

# {scope_key: [{"embedding": np.ndarray, "result": dict, "_cached_at": float}, ...]}
_cache: Dict[str, List[Dict[str, Any]]] = {}

# FastAPI dispatches every route here to a thread pool (conversations.py's
# routes are plain `def`, not `async def`), so concurrent requests can read
# and write _cache from different threads at once. Without this, two
# near-simultaneous first-turn requests in the same scope can race on the
# read-modify-write in store_cached_response() and silently drop one
# entry (last writer wins) - doesn't corrupt anything, just quietly
# degrades the hit rate under load.
_lock = threading.Lock()


def _scope_key(doc_ids: Optional[List[str]], advanced_mode: bool) -> str:
    # Sorted so the same document set hits the same scope regardless of
    # the order a conversation's doc_ids happen to be stored/passed in.
    doc_key = ",".join(sorted(doc_ids)) if doc_ids else "none"
    return f"{doc_key}|{advanced_mode}"


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _prune_expired(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cutoff = time.time() - settings.response_cache_ttl_seconds
    return [e for e in entries if e[_ENTRY_TIMESTAMP] >= cutoff]


def get_cached_response(
    doc_ids: Optional[List[str]], advanced_mode: bool, query_embedding: List[float]
) -> Optional[Dict[str, Any]]:
    """
    Returns a cached pipeline result for a semantically similar prior
    query in the same (doc_ids, advanced_mode) scope, or None on a miss.
    Expired entries are pruned as a side effect of the lookup, not on a
    separate timer - simplest correct behavior for an in-memory cache
    this size.
    """
    if not settings.response_cache_enabled:
        return None

    key = _scope_key(doc_ids, advanced_mode)
    with _lock:
        entries = _cache.get(key)
        if not entries:
            return None

        entries = _prune_expired(entries)
        _cache[key] = entries
        if not entries:
            return None

        query_vec = np.array(query_embedding)
        best_entry, best_score = None, -1.0
        for entry in entries:
            score = _cosine_similarity(query_vec, entry["embedding"])
            if score > best_score:
                best_entry, best_score = entry, score

        if best_entry is not None and best_score >= settings.response_cache_similarity_threshold:
            return best_entry["result"]
        return None


def store_cached_response(
    doc_ids: Optional[List[str]], advanced_mode: bool, query_embedding: List[float], result: Dict[str, Any]
) -> None:
    """Stores `result` for future near-duplicate lookups in this
    (doc_ids, advanced_mode) scope, evicting the oldest entry first if the
    scope is already at its size cap."""
    if not settings.response_cache_enabled:
        return

    key = _scope_key(doc_ids, advanced_mode)
    with _lock:
        entries = _prune_expired(_cache.get(key, []))

        if len(entries) >= settings.response_cache_max_entries_per_scope:
            entries.sort(key=lambda e: e[_ENTRY_TIMESTAMP])
            entries = entries[1:]

        entries.append({"embedding": np.array(query_embedding), "result": result, _ENTRY_TIMESTAMP: time.time()})
        _cache[key] = entries


def invalidate_doc_id(doc_id: str) -> None:
    """
    Drops every cached entry for any scope whose doc_ids set includes
    `doc_id` - called when a document's indexed content changes (see
    ingestion/pipeline.py's finish_ingest(), right before
    delete_document_data() clears the old nodes/chunks for a re-ingested
    file, once the new content's embeddings have actually succeeded) so a
    stale, pre-edit cached answer can't outlive the content it was
    generated from. Scope keys are "doc_id,doc_id,...|advanced_mode"
    (see _scope_key()), so a plain comma-split membership check is enough
    without needing a parallel doc_id -> scope-keys index.
    """
    with _lock:
        for key in list(_cache.keys()):
            scope_doc_ids = key.split("|", 1)[0].split(",")
            if doc_id in scope_doc_ids:
                del _cache[key]


def clear_cache() -> None:
    """Test/debug helper - drops every cached entry across every scope."""
    _cache.clear()
