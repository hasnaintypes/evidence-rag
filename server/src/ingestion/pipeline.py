import hashlib

from src.config import settings
from src.storage.database import (
    insert_chunk, insert_nodes, get_document_hash,
    upsert_document_record, delete_document_data,
)
from src.ingestion.parsers import get_parser
from src.ingestion.parsers.base import NodeType
from src.ingestion.chunking import chunk_document, chunk_nodes
from src.llm import get_embedding, EMBEDDING_MODEL_NAME
from src.graph import build_document_graph

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


def make_doc_id(filename: str) -> str:
    """Stable doc_id derived from filename, so re-ingestion of the same file
    always maps to the same doc_id (required for hash-based dedup to work -
    otherwise every run would look like a "new" document)."""
    return hashlib.sha1(filename.encode("utf-8")).hexdigest()[:12]


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


def ingest_file(file_path: str, filename: str) -> dict:
    """
    Parses, chunks, embeds, and indexes one document with hash-based dedup.

    Shared by scripts/ingest.py (bulk CLI ingestion over docs/sample_docs)
    and the /upload API route, so a file dropped on disk and one uploaded
    through the UI go through the exact same pipeline and produce the same
    knowledge tree / chunk structure.

    Returns {"status": "unchanged" | "success" | "empty", "chunk_count": int}.
    """
    doc_id = make_doc_id(filename)
    current_hash = file_hash(file_path)
    stored_hash = get_document_hash(doc_id)

    if stored_hash == current_hash:
        return {"status": "unchanged", "chunk_count": 0}

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
        return {"status": "empty", "chunk_count": 0}

    indexed_count = 0
    for item in chunks_data:
        # Table/figure/warning nodes can be empty at this stage (e.g. a
        # figure awaiting vision captioning) - skip embedding empty text,
        # nothing useful to index yet.
        if not item["chunk_text"].strip():
            continue
        embedding = get_embedding(item["chunk_text"])
        insert_chunk(item, embedding)
        indexed_count += 1

    upsert_document_record(
        doc_id=doc_id,
        filename=filename,
        file_hash=current_hash,
        node_count=len(chunks_data),
        chunk_count=indexed_count,
        embedding_model=EMBEDDING_MODEL_NAME,
    )

    return {"status": "success", "chunk_count": indexed_count}
