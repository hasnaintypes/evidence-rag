import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any

from src.config import settings
from src.storage.database import (
    insert_chunks_batch, insert_nodes, get_document_hash,
    delete_document_data, mark_document_processing,
    set_document_progress, mark_document_ready, mark_document_failed,
)
from src.ingestion.parsers import get_parser
from src.ingestion.parsers.base import NodeType
from src.ingestion.chunking import chunk_document, chunk_nodes
from src.llm import get_embedding, EMBEDDING_MODEL_NAME
from src.graph import build_document_graph

# Each chunk's embedding is one blocking Gemini API call - sequential was
# the single biggest cost on large documents (hundreds of chunks x one
# network round trip each, serially). Concurrent via a thread pool since
# the Gemini SDK call is synchronous I/O (releases the GIL while waiting
# on the socket) - no async client rewrite needed for this.
# ponytail: fixed worker count, raise if Gemini's per-minute rate limit
# allows more headroom than this leaves on the table.
EMBED_CONCURRENCY = 6

SUPPORTED_EXTENSIONS = ['.md', '.pdf', '.docx', '.xlsx', '.xls', '.csv']

# Explicit per-extension MIME types for Supabase Storage uploads - the
# client defaults to "text/plain" for everything if not told otherwise,
# which would fail the bucket's allowed_mime_types check for every format
# except .md.
EXTENSION_MIME_TYPES = {
    '.md': 'text/markdown',
    '.pdf': 'application/pdf',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.xls': 'application/vnd.ms-excel',
    '.csv': 'text/csv',
}


def file_hash(file_path: str) -> str:
    """Content hash used to detect whether a file changed since last ingestion."""
    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def make_doc_id(filename: str, user_id: str = None) -> str:
    """Stable doc_id derived from filename (+ user_id when set), so
    re-ingestion of the same file always maps to the same doc_id (required
    for hash-based dedup - otherwise every run would look like a "new"
    document). user_id is folded in so two different users uploading a
    file with the same name don't collide on the same doc_id and overwrite
    each other. Shared/demo docs (scripts/ingest.py, no user_id) keep the
    original filename-only hash - unchanged for docs already ingested that way."""
    key = f"{user_id}:{filename}" if user_id else filename
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _ingest_tree_aware(parser, file_path: str, doc_id: str, filename: str) -> list:
    nodes = parser.parse_to_tree(file_path, doc_id=doc_id)
    if not nodes:
        return []

    insert_nodes(nodes)
    chunks_data = chunk_nodes(
        nodes,
        chunk_size=settings.chunk_size_tokens,
        chunk_overlap=settings.chunk_overlap_tokens,
    )

    # chunk_nodes doesn't set metadata["doc_id"] on its own (it only carries
    # doc_id inside each node, not surfaced to the chunk-level metadata dict).
    # Set both here: doc_id for the FK/dedup column in document_chunks, and
    # source_file overwritten to the human-readable filename so telemetry/UI
    # shows "manual.pdf" instead of a hash.
    for item in chunks_data:
        item["metadata"]["doc_id"] = doc_id
        item["metadata"]["source_file"] = filename

    # Entity graph runs after insert_nodes() since it reads children back
    # from storage via get_children().
    if settings.enable_entity_graph:
        section_nodes = [n for n in nodes if n.type == NodeType.SECTION]
        if section_nodes:
            build_document_graph(doc_id, section_nodes)

    return chunks_data


def _ingest_legacy(parser, file_path: str, filename: str, doc_id: str) -> list:
    parsed_data = parser.parse(file_path)
    raw_content = parsed_data["content"]
    chunks_data = chunk_document(
        file_path,
        raw_content,
        chunk_size=settings.chunk_size_tokens,
        chunk_overlap=settings.chunk_overlap_tokens,
    )

    # Legacy chunker doesn't know about doc_id - attach it here so
    # insert_chunk's doc_id column and future dedup lookups stay consistent
    for item in chunks_data:
        item["metadata"]["doc_id"] = doc_id

    return chunks_data


def prepare_ingest(file_path: str, filename: str, user_id: str = None) -> dict:
    """
    Fast, synchronous phase: hash-based dedup check, parsing, chunking.
    Safe to run inline in an API request (no network calls - parsing is
    local CPU/disk work).

    Returns a terminal result immediately for the "unchanged"/"empty"
    cases. Otherwise marks the document "processing" (so a status poll has
    something real to report right away) and returns
    {"status": "ready_to_index", "doc_id", "chunks_data", ...} for the
    caller to hand to finish_ingest() - inline for the CLI script, or via
    FastAPI's BackgroundTasks for the API so the slow part (one Gemini
    call per chunk) doesn't hold the HTTP request open.
    """
    doc_id = make_doc_id(filename, user_id=user_id)
    current_hash = file_hash(file_path)
    stored_hash = get_document_hash(doc_id)

    if stored_hash == current_hash:
        return {"status": "unchanged", "chunk_count": 0, "doc_id": doc_id}

    if stored_hash is not None:
        # File existed before but content changed - clear stale nodes/chunks
        # first, otherwise old and new versions would coexist and retrieval
        # would return duplicate/contradictory chunks.
        delete_document_data(doc_id)

    parser = get_parser(file_path)
    if hasattr(parser, "parse_to_tree"):
        chunks_data = _ingest_tree_aware(parser, file_path, doc_id, filename)
    else:
        chunks_data = _ingest_legacy(parser, file_path, filename, doc_id)

    if not chunks_data:
        return {"status": "empty", "chunk_count": 0, "doc_id": doc_id}

    # Table/figure/warning nodes can be empty at this stage (e.g. a figure
    # awaiting vision captioning) - nothing useful to embed/index yet.
    indexable = [item for item in chunks_data if item["chunk_text"].strip()]

    mark_document_processing(
        doc_id, filename, file_hash=current_hash, user_id=user_id,
        node_count=len(chunks_data), chunks_total=len(indexable),
    )

    return {"status": "ready_to_index", "doc_id": doc_id, "chunks_data": indexable}


PROGRESS_FLUSH_INTERVAL_SECONDS = 1.0


def finish_ingest(doc_id: str, chunks_data: List[Dict[str, Any]]) -> dict:
    """
    Slow phase: embeds every chunk concurrently (EMBED_CONCURRENCY workers -
    measured ~4.6x faster than sequential for Gemini's embedding API, which
    isn't itself rate-limited tightly enough to negate client-side
    concurrency), then writes every chunk in a single batched INSERT
    instead of one round trip per chunk - N individual INSERTs under
    concurrent load didn't speed up much (connection-pool contention +
    GIL-bound vector-literal formatting dominated), so batching sidesteps
    that entirely instead of fighting it.

    Progress (documents.chunks_indexed) is tracked in memory and flushed
    to the DB by a single background thread every
    PROGRESS_FLUSH_INTERVAL_SECONDS, rather than once per chunk - a DB
    round trip per embedding completion was itself slow enough to measurably
    undercut the concurrency gain it was meant to just observe.

    On any failure the document is marked "failed" rather than left stuck
    at "processing" forever.
    """
    indexed_count = 0
    count_lock = threading.Lock()
    stop_flushing = threading.Event()

    def _flush_progress_periodically() -> None:
        last_flushed = -1
        while not stop_flushing.wait(PROGRESS_FLUSH_INTERVAL_SECONDS):
            with count_lock:
                current = indexed_count
            if current != last_flushed:
                set_document_progress(doc_id, current)
                last_flushed = current

    def _embed(item: Dict[str, Any]):
        nonlocal indexed_count
        embedding = get_embedding(item["chunk_text"])
        with count_lock:
            indexed_count += 1
        return (item, embedding)

    flusher = threading.Thread(target=_flush_progress_periodically, daemon=True)
    flusher.start()
    try:
        with ThreadPoolExecutor(max_workers=EMBED_CONCURRENCY) as executor:
            # list(...) forces iteration so the first worker exception
            # propagates here instead of being silently swallowed.
            embedded = list(executor.map(_embed, chunks_data))
    except Exception:
        stop_flushing.set()
        mark_document_failed(doc_id)
        raise
    finally:
        stop_flushing.set()
        flusher.join(timeout=PROGRESS_FLUSH_INTERVAL_SECONDS + 1)

    insert_chunks_batch(embedded)

    indexed_total = len(embedded)
    mark_document_ready(doc_id, chunk_count=indexed_total, embedding_model=EMBEDDING_MODEL_NAME)
    return {"status": "success", "chunk_count": indexed_total, "doc_id": doc_id}


def ingest_file(file_path: str, filename: str, user_id: str = None) -> dict:
    """
    Parses, chunks, embeds, and indexes one document with hash-based dedup -
    the synchronous all-in-one entry point used by scripts/ingest.py (bulk
    CLI ingestion over docs/sample_docs, user_id=None -> shared/demo doc).
    The /upload API route calls prepare_ingest()/finish_ingest() directly
    instead, so the slow phase can run as a background task.

    Returns {"status": "unchanged" | "success" | "empty", "chunk_count": int, "doc_id": str}.
    """
    prep = prepare_ingest(file_path, filename, user_id=user_id)
    if prep["status"] != "ready_to_index":
        return prep
    return finish_ingest(prep["doc_id"], prep["chunks_data"])
