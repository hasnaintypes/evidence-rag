"""Unit tests for src/response_cache.py's semantic response cache."""

import threading
import time

from src.core.config import settings
from src.core.response_cache import get_cached_response, invalidate_doc_id, store_cached_response


def test_miss_on_an_empty_cache():
    assert get_cached_response(["doc-1"], True, [1.0, 0.0, 0.0]) is None


def test_hit_on_an_identical_embedding_in_the_same_scope():
    embedding = [1.0, 0.0, 0.0]
    result = {"reply": "cached answer"}
    store_cached_response(["doc-1"], True, embedding, result)

    assert get_cached_response(["doc-1"], True, embedding) == result


def test_hit_on_a_near_identical_embedding_above_the_similarity_threshold(monkeypatch):
    monkeypatch.setattr(settings, "response_cache_similarity_threshold", 0.97)
    result = {"reply": "cached answer"}
    store_cached_response(["doc-1"], True, [1.0, 0.0], result)

    # Cosine similarity of [1.0, 0.0] and [0.999, 0.02] is ~0.9998 - a
    # near-duplicate rewording should still hit.
    assert get_cached_response(["doc-1"], True, [0.999, 0.02]) == result


def test_miss_on_a_dissimilar_embedding_below_the_threshold():
    store_cached_response(["doc-1"], True, [1.0, 0.0], {"reply": "cached answer"})

    # Orthogonal vector - cosine similarity 0.0, nowhere near the default
    # 0.97 threshold.
    assert get_cached_response(["doc-1"], True, [0.0, 1.0]) is None


def test_different_doc_ids_scope_does_not_collide():
    embedding = [1.0, 0.0, 0.0]
    store_cached_response(["doc-1"], True, embedding, {"reply": "for doc-1"})

    assert get_cached_response(["doc-2"], True, embedding) is None


def test_different_advanced_mode_scope_does_not_collide():
    embedding = [1.0, 0.0, 0.0]
    store_cached_response(["doc-1"], True, embedding, {"reply": "advanced"})

    assert get_cached_response(["doc-1"], False, embedding) is None


def test_doc_ids_order_does_not_affect_scope():
    embedding = [1.0, 0.0, 0.0]
    store_cached_response(["doc-1", "doc-2"], True, embedding, {"reply": "multi-doc"})

    assert get_cached_response(["doc-2", "doc-1"], True, embedding) == {"reply": "multi-doc"}


def test_expired_entry_is_not_served(monkeypatch):
    monkeypatch.setattr(settings, "response_cache_ttl_seconds", 0)
    embedding = [1.0, 0.0, 0.0]
    store_cached_response(["doc-1"], True, embedding, {"reply": "stale"})
    time.sleep(0.05)

    assert get_cached_response(["doc-1"], True, embedding) is None


def test_scope_evicts_the_oldest_entry_once_past_the_cap(monkeypatch):
    monkeypatch.setattr(settings, "response_cache_max_entries_per_scope", 2)

    # Three near-orthogonal-but-distinct embeddings so each is its own
    # entry rather than overwriting a near-duplicate match.
    store_cached_response(["doc-1"], True, [1.0, 0.0, 0.0, 0.0], {"reply": "first"})
    store_cached_response(["doc-1"], True, [0.0, 1.0, 0.0, 0.0], {"reply": "second"})
    store_cached_response(["doc-1"], True, [0.0, 0.0, 1.0, 0.0], {"reply": "third"})

    # The cap is 2, so the oldest ("first") should have been evicted.
    assert get_cached_response(["doc-1"], True, [1.0, 0.0, 0.0, 0.0]) is None
    assert get_cached_response(["doc-1"], True, [0.0, 0.0, 1.0, 0.0]) == {"reply": "third"}


def test_disabled_cache_never_stores_or_serves(monkeypatch):
    monkeypatch.setattr(settings, "response_cache_enabled", False)
    embedding = [1.0, 0.0, 0.0]
    store_cached_response(["doc-1"], True, embedding, {"reply": "should not be cached"})

    assert get_cached_response(["doc-1"], True, embedding) is None


def test_invalidate_doc_id_drops_every_scope_that_includes_it():
    """A re-ingested document's stale cached answer must not outlive the
    content it was generated from - see ingestion/pipeline.py's
    prepare_ingest() call site."""
    embedding = [1.0, 0.0, 0.0]
    store_cached_response(["doc-1"], True, embedding, {"reply": "single-doc"})
    store_cached_response(["doc-1", "doc-2"], True, embedding, {"reply": "multi-doc"})
    store_cached_response(["doc-3"], True, embedding, {"reply": "unrelated"})

    invalidate_doc_id("doc-1")

    assert get_cached_response(["doc-1"], True, embedding) is None
    assert get_cached_response(["doc-1", "doc-2"], True, embedding) is None
    # A scope that never included doc-1 is untouched.
    assert get_cached_response(["doc-3"], True, embedding) == {"reply": "unrelated"}


def test_invalidate_doc_id_is_a_no_op_for_an_unknown_doc_id():
    embedding = [1.0, 0.0, 0.0]
    store_cached_response(["doc-1"], True, embedding, {"reply": "unaffected"})

    invalidate_doc_id("doc-does-not-exist")

    assert get_cached_response(["doc-1"], True, embedding) == {"reply": "unaffected"}


def test_concurrent_stores_in_the_same_scope_do_not_drop_entries():
    """Regression test for the read-modify-write race: without the lock,
    two threads racing on store_cached_response() in the same scope can
    each read the same starting list, append their own entry, and then
    one `_cache[key] = entries` write clobbers the other's - silently
    losing an entry. Each of these embeddings is near-orthogonal to the
    others, so a correct run stores all of them as distinct entries."""
    vectors = [
        [1.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 1.0],
    ]

    def worker(vec, idx):
        store_cached_response(["doc-1"], True, vec, {"reply": f"answer-{idx}"})

    threads = [threading.Thread(target=worker, args=(vec, idx)) for idx, vec in enumerate(vectors)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for idx, vec in enumerate(vectors):
        assert get_cached_response(["doc-1"], True, vec) == {"reply": f"answer-{idx}"}
