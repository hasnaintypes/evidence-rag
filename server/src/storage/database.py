import sqlite3
import json
import os
from typing import List, Dict, Any, Optional

from src.config import settings

DB_PATH = "data/rag.db"

# --------------------------------------------------------------------------- #
# Connection
#
# storage_mode="local": SQLite file on disk (DB_PATH), as before.
# storage_mode="supabase": Postgres+pgvector via psycopg2, using the direct
# connection string (SUPABASE_DB_URL). Schema is NOT created by this app for
# supabase mode - run scripts/supabase_schema.sql once in the Supabase SQL
# editor first. Every function below branches on storage_mode internally,
# so every caller elsewhere in the codebase is unchanged either way.
# --------------------------------------------------------------------------- #

def get_db_connection():
    """Returns a DB-API connection for the active storage backend.
    Rows are dict-like in both cases (sqlite3.Row / RealDictCursor) so
    row["col"] and dict(row) work identically regardless of storage_mode."""
    if settings.storage_mode == "supabase":
        import psycopg2
        import psycopg2.extras
        if not settings.supabase_db_url:
            raise RuntimeError("STORAGE_MODE=supabase requires SUPABASE_DB_URL to be set.")
        return psycopg2.connect(settings.supabase_db_url, cursor_factory=psycopg2.extras.RealDictCursor)

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ph(n: int) -> str:
    """Returns n comma-separated placeholders in the active backend's
    style ("?" for SQLite, "%s" for Postgres) - avoids sprinkling
    storage_mode checks through every query string below."""
    mark = "%s" if settings.storage_mode == "supabase" else "?"
    return ", ".join([mark] * n)


def init_db() -> None:
    """
    Initializes local storage. No-op for storage_mode=supabase - that
    schema is managed once via scripts/supabase_schema.sql instead of
    being created/migrated by the app on every startup, since doing DDL
    against a shared hosted database on every boot is the wrong default.
    """
    if settings.storage_mode == "supabase":
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            ingested_at TEXT DEFAULT CURRENT_TIMESTAMP,
            node_count INTEGER DEFAULT 0,
            chunk_count INTEGER DEFAULT 0,
            embedding_model TEXT,
            user_id TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            title TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            sources_json TEXT,
            faithfulness_score REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_nodes (
            id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            parent_id TEXT,
            type TEXT NOT NULL,
            level INTEGER DEFAULT 0,
            heading_path TEXT,
            content TEXT,
            page INTEGER,
            bbox TEXT,
            node_order INTEGER,
            metadata TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT,
            source_file TEXT NOT NULL,
            page_number INTEGER DEFAULT 1,
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            embedding BLOB NOT NULL,
            node_type TEXT DEFAULT 'paragraph',
            heading_path TEXT,
            node_ids TEXT,
            parent_id TEXT,
            bbox TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT NOT NULL,
            name TEXT NOT NULL,
            node_id TEXT,
            UNIQUE(doc_id, name)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entity_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT NOT NULL,
            source_entity_id INTEGER NOT NULL,
            target_entity_id INTEGER NOT NULL,
            weight INTEGER DEFAULT 1,
            UNIQUE(source_entity_id, target_entity_id)
        )
    """)

    conn.commit()

    # --- Migration pass: patch any pre-existing table missing new columns ---
    _migrate_missing_columns(cursor, "documents", {
        "filename": "TEXT",
        "file_hash": "TEXT",
        "node_count": "INTEGER DEFAULT 0",
        "chunk_count": "INTEGER DEFAULT 0",
        "embedding_model": "TEXT",
        "user_id": "TEXT",
    })
    _migrate_missing_columns(cursor, "knowledge_nodes", {
        "doc_id": "TEXT",
        "parent_id": "TEXT",
        "type": "TEXT",
        "level": "INTEGER DEFAULT 0",
        "heading_path": "TEXT",
        "content": "TEXT",
        "page": "INTEGER",
        "bbox": "TEXT",
        "node_order": "INTEGER",
        "metadata": "TEXT",
    })
    _migrate_missing_columns(cursor, "document_chunks", {
        "doc_id": "TEXT",
        "source_file": "TEXT",
        "page_number": "INTEGER DEFAULT 1",
        "chunk_index": "INTEGER",
        "chunk_text": "TEXT",
        "embedding": "BLOB",
        "node_type": "TEXT DEFAULT 'paragraph'",
        "heading_path": "TEXT",
        "node_ids": "TEXT",
        "parent_id": "TEXT",
        "bbox": "TEXT",
    })
    conn.commit()

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_parent ON knowledge_nodes(parent_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_doc ON knowledge_nodes(doc_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_parent ON document_chunks(parent_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks(doc_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_doc ON entities(doc_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_doc ON entity_edges(doc_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)")

    conn.commit()
    conn.close()


def _migrate_missing_columns(cursor, table_name: str, expected_columns: dict) -> None:
    """
    Adds any column from expected_columns that doesn't already exist on
    table_name. SQLite's ALTER TABLE only supports adding columns - existing
    rows get the new column back-filled with NULL (or the column's default).
    Local-mode only - see init_db().
    """
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row[1] for row in cursor.fetchall()}

    for col_name, col_type in expected_columns.items():
        if col_name not in existing_columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")


# --------------------------------------------------------------------------- #
# Documents registry — drives incremental ingestion (hash-based dedup)
# and embedding-model consistency checks
# --------------------------------------------------------------------------- #

def get_document_hash(doc_id: str) -> Optional[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT file_hash FROM documents WHERE doc_id = {_ph(1)}", (doc_id,))
    row = cursor.fetchone()
    conn.close()
    return row["file_hash"] if row else None


def upsert_document_record(
    doc_id: str,
    filename: str,
    file_hash: str,
    node_count: int,
    chunk_count: int,
    embedding_model: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    if settings.storage_mode == "supabase":
        cursor.execute("""
            INSERT INTO documents (doc_id, filename, file_hash, node_count, chunk_count, embedding_model, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (doc_id) DO UPDATE SET
                filename = EXCLUDED.filename,
                file_hash = EXCLUDED.file_hash,
                ingested_at = now(),
                node_count = EXCLUDED.node_count,
                chunk_count = EXCLUDED.chunk_count,
                embedding_model = EXCLUDED.embedding_model,
                user_id = EXCLUDED.user_id
        """, (doc_id, filename, file_hash, node_count, chunk_count, embedding_model, user_id))
    else:
        cursor.execute("""
            INSERT INTO documents (doc_id, filename, file_hash, node_count, chunk_count, embedding_model, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                filename = excluded.filename,
                file_hash = excluded.file_hash,
                ingested_at = CURRENT_TIMESTAMP,
                node_count = excluded.node_count,
                chunk_count = excluded.chunk_count,
                embedding_model = excluded.embedding_model,
                user_id = excluded.user_id
        """, (doc_id, filename, file_hash, node_count, chunk_count, embedding_model, user_id))
    conn.commit()
    conn.close()


def get_indexed_embedding_models() -> List[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT embedding_model FROM documents WHERE embedding_model IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()
    return [r["embedding_model"] for r in rows]


def delete_document_data(doc_id: str) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    ph = _ph(1)
    cursor.execute(f"DELETE FROM knowledge_nodes WHERE doc_id = {ph}", (doc_id,))
    cursor.execute(f"DELETE FROM document_chunks WHERE doc_id = {ph}", (doc_id,))
    cursor.execute(f"DELETE FROM entities WHERE doc_id = {ph}", (doc_id,))
    cursor.execute(f"DELETE FROM entity_edges WHERE doc_id = {ph}", (doc_id,))
    conn.commit()
    conn.close()


def list_documents(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns a user's own uploaded documents plus shared/demo documents
    (user_id IS NULL, e.g. docs/sample_docs ingested via scripts/ingest.py).
    user_id=None returns every document regardless of owner - used by
    internal/non-request-scoped callers only, never by the /documents route.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    if user_id is not None:
        ph = _ph(1)
        cursor.execute(
            f"SELECT * FROM documents WHERE user_id = {ph} OR user_id IS NULL ORDER BY ingested_at DESC",
            (user_id,),
        )
    else:
        cursor.execute("SELECT * FROM documents ORDER BY ingested_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Knowledge tree (nodes)
# --------------------------------------------------------------------------- #

def insert_nodes(nodes: List[Any]) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    is_supabase = settings.storage_mode == "supabase"
    for node in nodes:
        d = node.to_dict() if hasattr(node, "to_dict") else node
        bbox = d.get("bbox")
        metadata = d.get("metadata", {})
        if is_supabase:
            cursor.execute("""
                INSERT INTO knowledge_nodes (id, doc_id, parent_id, type, level, heading_path, content, page, bbox, node_order, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                d["id"], d["doc_id"], d.get("parent_id"), d["type"], d.get("level", 0),
                d.get("heading_path", ""), d.get("content", ""), d.get("page"),
                json.dumps(bbox) if bbox else None, d.get("order", 0), json.dumps(metadata),
            ))
        else:
            cursor.execute("""
                INSERT INTO knowledge_nodes (id, doc_id, parent_id, type, level, heading_path, content, page, bbox, node_order, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                d["id"], d["doc_id"], d.get("parent_id"), d["type"], d.get("level", 0),
                d.get("heading_path", ""), d.get("content", ""), d.get("page"),
                json.dumps(bbox) if bbox else None, d.get("order", 0), json.dumps(metadata),
            ))
    conn.commit()
    conn.close()


def get_node(node_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM knowledge_nodes WHERE id = {_ph(1)}", (node_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    if settings.storage_mode != "supabase":
        # Postgres returns jsonb columns already parsed; SQLite stores them
        # as plain TEXT and needs an explicit decode.
        d["bbox"] = json.loads(d["bbox"]) if d["bbox"] else None
        d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
    return d


def get_children(node_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM knowledge_nodes WHERE parent_id = {_ph(1)} ORDER BY node_order", (node_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Retrieval chunks (dense + sparse index source)
# --------------------------------------------------------------------------- #

def insert_chunk(chunk: Dict[str, Any], embedding: List[float]) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    meta = chunk["metadata"]
    bbox = meta.get("bbox")

    if settings.storage_mode == "supabase":
        # pgvector accepts its text literal ("[0.1,0.2,...]") cast to
        # ::vector - no extra adapter package needed for a plain insert.
        embedding_literal = "[" + ",".join(str(float(x)) for x in embedding) + "]"
        cursor.execute("""
            INSERT INTO document_chunks
                (doc_id, source_file, page_number, chunk_index, chunk_text, embedding,
                 node_type, heading_path, node_ids, parent_id, bbox)
            VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s, %s)
        """, (
            meta.get("doc_id"), meta.get("source_file", ""), meta.get("page_number", 1),
            meta.get("chunk_index", 0), chunk["chunk_text"], embedding_literal,
            meta.get("node_type", "paragraph"), meta.get("heading_path", ""),
            json.dumps(meta.get("node_ids", [])), meta.get("parent_id"),
            json.dumps(bbox) if bbox else None,
        ))
    else:
        embedding_blob = json.dumps(embedding).encode("utf-8")
        cursor.execute("""
            INSERT INTO document_chunks
                (doc_id, source_file, page_number, chunk_index, chunk_text, embedding,
                 node_type, heading_path, node_ids, parent_id, bbox)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            meta.get("doc_id"), meta.get("source_file", ""), meta.get("page_number", 1),
            meta.get("chunk_index", 0), chunk["chunk_text"], embedding_blob,
            meta.get("node_type", "paragraph"), meta.get("heading_path", ""),
            json.dumps(meta.get("node_ids", [])), meta.get("parent_id"),
            json.dumps(bbox) if bbox else None,
        ))
    conn.commit()
    conn.close()


def get_all_chunks_for_sparse() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM document_chunks")
    rows = cursor.fetchall()
    conn.close()

    is_supabase = settings.storage_mode == "supabase"
    chunks = []
    for row in rows:
        d = dict(row)
        if is_supabase:
            # pgvector's default text output ("[0.1,0.2,...]") is valid
            # JSON, and node_ids/bbox are jsonb (already parsed objects).
            d["embedding"] = json.loads(d["embedding"]) if isinstance(d["embedding"], str) else list(d["embedding"])
        else:
            d["embedding"] = json.loads(d["embedding"].decode("utf-8"))
            d["node_ids"] = json.loads(d["node_ids"]) if d["node_ids"] else []
            d["bbox"] = json.loads(d["bbox"]) if d["bbox"] else None
        chunks.append(d)
    return chunks


# --------------------------------------------------------------------------- #
# Entity graph (entities + co-occurrence edges)
# --------------------------------------------------------------------------- #

def upsert_entity(doc_id: str, name: str, node_id: str) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    if settings.storage_mode == "supabase":
        cursor.execute("""
            INSERT INTO entities (doc_id, name, node_id) VALUES (%s, %s, %s)
            ON CONFLICT (doc_id, name) DO NOTHING
        """, (doc_id, name, node_id))
        conn.commit()
        cursor.execute("SELECT id FROM entities WHERE doc_id = %s AND name = %s", (doc_id, name))
    else:
        cursor.execute("""
            INSERT INTO entities (doc_id, name, node_id) VALUES (?, ?, ?)
            ON CONFLICT(doc_id, name) DO NOTHING
        """, (doc_id, name, node_id))
        conn.commit()
        cursor.execute("SELECT id FROM entities WHERE doc_id = ? AND name = ?", (doc_id, name))

    row = cursor.fetchone()
    conn.close()
    return row["id"]


def upsert_edge(doc_id: str, source_entity_id: int, target_entity_id: int) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    if settings.storage_mode == "supabase":
        cursor.execute("""
            INSERT INTO entity_edges (doc_id, source_entity_id, target_entity_id, weight)
            VALUES (%s, %s, %s, 1)
            ON CONFLICT (source_entity_id, target_entity_id) DO UPDATE SET
                weight = entity_edges.weight + 1
        """, (doc_id, source_entity_id, target_entity_id))
    else:
        cursor.execute("""
            INSERT INTO entity_edges (doc_id, source_entity_id, target_entity_id, weight)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(source_entity_id, target_entity_id) DO UPDATE SET
                weight = weight + 1
        """, (doc_id, source_entity_id, target_entity_id))
    conn.commit()
    conn.close()


def get_graph_data(doc_id: Optional[str] = None) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    ph = _ph(1)

    if doc_id:
        cursor.execute(f"SELECT id, name, doc_id, node_id FROM entities WHERE doc_id = {ph}", (doc_id,))
    else:
        cursor.execute("SELECT id, name, doc_id, node_id FROM entities")
    entity_rows = cursor.fetchall()

    if doc_id:
        cursor.execute(f"SELECT source_entity_id, target_entity_id, weight FROM entity_edges WHERE doc_id = {ph}", (doc_id,))
    else:
        cursor.execute("SELECT source_entity_id, target_entity_id, weight FROM entity_edges")
    edge_rows = cursor.fetchall()

    conn.close()
    return {
        "nodes": [
            {"id": r["id"], "label": r["name"], "doc_id": r["doc_id"], "node_id": r["node_id"]}
            for r in entity_rows
        ],
        "edges": [{"from": r["source_entity_id"], "to": r["target_entity_id"], "weight": r["weight"]} for r in edge_rows],
    }


# --------------------------------------------------------------------------- #
# Conversations + messages (per-document chat sessions)
# --------------------------------------------------------------------------- #

def create_conversation(conversation_id: str, user_id: str, doc_id: str) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    if settings.storage_mode == "supabase":
        cursor.execute(
            "INSERT INTO conversations (id, user_id, doc_id) VALUES (%s, %s, %s)",
            (conversation_id, user_id, doc_id),
        )
    else:
        cursor.execute(
            "INSERT INTO conversations (id, user_id, doc_id) VALUES (?, ?, ?)",
            (conversation_id, user_id, doc_id),
        )
    conn.commit()
    conn.close()


def list_conversations(user_id: str) -> List[Dict[str, Any]]:
    """Joins in the conversation's document filename so the sidebar doesn't
    need a second round trip per conversation to show what it's about."""
    conn = get_db_connection()
    cursor = conn.cursor()
    ph = _ph(1)
    cursor.execute(f"""
        SELECT c.id, c.doc_id, c.title, c.created_at, c.updated_at, d.filename
        FROM conversations c
        LEFT JOIN documents d ON d.doc_id = c.doc_id
        WHERE c.user_id = {ph}
        ORDER BY c.updated_at DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    ph = _ph(1)
    cursor.execute(f"SELECT * FROM conversations WHERE id = {ph}", (conversation_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_conversation(conversation_id: str) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    ph = _ph(1)
    cursor.execute(f"DELETE FROM messages WHERE conversation_id = {ph}", (conversation_id,))
    cursor.execute(f"DELETE FROM conversations WHERE id = {ph}", (conversation_id,))
    conn.commit()
    conn.close()


def touch_conversation(conversation_id: str, title: Optional[str] = None) -> None:
    """Bumps updated_at on every new message, and sets title once (only
    when it's still unset) from the conversation's first user message."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if settings.storage_mode == "supabase":
        if title is not None:
            cursor.execute(
                "UPDATE conversations SET updated_at = now(), title = COALESCE(title, %s) WHERE id = %s",
                (title, conversation_id),
            )
        else:
            cursor.execute("UPDATE conversations SET updated_at = now() WHERE id = %s", (conversation_id,))
    else:
        if title is not None:
            cursor.execute(
                "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP, title = COALESCE(title, ?) WHERE id = ?",
                (title, conversation_id),
            )
        else:
            cursor.execute(
                "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (conversation_id,)
            )
    conn.commit()
    conn.close()


def insert_message(
    conversation_id: str,
    role: str,
    content: str,
    sources: Optional[List[Dict[str, Any]]] = None,
    faithfulness_score: Optional[float] = None,
) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    sources_json = json.dumps(sources) if sources is not None else None
    if settings.storage_mode == "supabase":
        cursor.execute("""
            INSERT INTO messages (conversation_id, role, content, sources_json, faithfulness_score)
            VALUES (%s, %s, %s, %s, %s) RETURNING id, created_at
        """, (conversation_id, role, content, sources_json, faithfulness_score))
        row = cursor.fetchone()
        conn.commit()
    else:
        cursor.execute("""
            INSERT INTO messages (conversation_id, role, content, sources_json, faithfulness_score)
            VALUES (?, ?, ?, ?, ?)
        """, (conversation_id, role, content, sources_json, faithfulness_score))
        conn.commit()
        cursor.execute("SELECT id, created_at FROM messages WHERE id = ?", (cursor.lastrowid,))
        row = cursor.fetchone()
    conn.close()
    return {
        "id": row["id"],
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "sources": sources or [],
        "faithfulness_score": faithfulness_score,
        "created_at": row["created_at"],
    }


def get_conversation_messages(conversation_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    ph = _ph(1)
    query = f"SELECT * FROM messages WHERE conversation_id = {ph} ORDER BY id ASC"
    cursor.execute(query, (conversation_id,))
    rows = cursor.fetchall()
    conn.close()

    messages = []
    for r in rows:
        d = dict(r)
        d["sources"] = (
            d["sources_json"] if isinstance(d["sources_json"], list) else json.loads(d["sources_json"] or "[]")
        ) if d.get("sources_json") is not None else []
        messages.append(d)

    return messages[-limit:] if limit else messages
