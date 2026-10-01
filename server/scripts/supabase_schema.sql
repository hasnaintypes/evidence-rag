-- Run once in the Supabase SQL editor before setting STORAGE_MODE=supabase.
-- Mirrors the SQLite schema in src/db.py's local-mode init_db(), so both
-- backends store the same shape of data.
--
-- vector(3072) matches gemini-embedding-001's output dimension (the
-- embedding model set via GEMINI_EMBEDDING_MODEL). If you ever swap
-- embedding models, this column width has to change too, and existing
-- rows would need re-embedding (see EMBEDDING_MODEL_NAME /
-- get_indexed_embedding_models in src/storage/database.py, which exists
-- specifically to catch that mismatch).

create extension if not exists vector;

create table if not exists documents (
    doc_id text primary key,
    filename text not null,
    file_hash text not null,
    ingested_at timestamptz default now(),
    node_count integer default 0,
    chunk_count integer default 0,
    embedding_model text,
    user_id text,
    status text default 'ready',
    chunks_indexed integer default 0,
    chunks_total integer default 0
);

-- Migration for documents tables created before per-user ownership was
-- added - NULL means a shared/demo document (e.g. docs/sample_docs).
alter table documents add column if not exists user_id text;

-- Migration for documents tables created before background-job ingestion -
-- status tracks 'processing'/'ready'/'failed' while chunks are embedded
-- concurrently in the background, chunks_indexed/chunks_total back the
-- upload progress poll (see GET /documents/{doc_id}/status).
alter table documents add column if not exists status text default 'ready';
alter table documents add column if not exists chunks_indexed integer default 0;
alter table documents add column if not exists chunks_total integer default 0;

create table if not exists conversations (
    id text primary key,
    user_id text not null,
    doc_ids text not null,
    pinned boolean not null default false,
    title text,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

-- Migration for conversations tables created before multi-document chats -
-- doc_ids stores a JSON array of doc_id strings (max 5), replacing the old
-- single doc_id column.
alter table conversations drop column if exists doc_id;
alter table conversations add column if not exists doc_ids text not null default '[]';
alter table conversations add column if not exists pinned boolean not null default false;

create table if not exists messages (
    id serial primary key,
    conversation_id text not null,
    role text not null,
    content text not null,
    sources_json jsonb,
    faithfulness_score real,
    created_at timestamptz default now()
);

create table if not exists knowledge_nodes (
    id text primary key,
    doc_id text not null,
    parent_id text,
    type text not null,
    level integer default 0,
    heading_path text,
    content text,
    page integer,
    bbox jsonb,
    node_order integer,
    metadata jsonb
);

create table if not exists document_chunks (
    id serial primary key,
    doc_id text,
    source_file text not null,
    page_number integer default 1,
    chunk_index integer not null,
    chunk_text text not null,
    embedding vector(3072) not null,
    node_type text default 'paragraph',
    heading_path text,
    node_ids jsonb,
    parent_id text,
    bbox jsonb
);

create table if not exists entities (
    id serial primary key,
    doc_id text not null,
    name text not null,
    node_id text,
    unique (doc_id, name)
);

create table if not exists entity_edges (
    id serial primary key,
    doc_id text not null,
    source_entity_id integer not null,
    target_entity_id integer not null,
    weight integer default 1,
    unique (source_entity_id, target_entity_id)
);

create table if not exists query_log (
    id serial primary key,
    timestamp timestamptz default now(),
    query text not null,
    advanced_mode integer default 1,
    hop_count integer,
    chunk_count integer,
    top_rerank_score real,
    generation_failed integer default 0,
    telemetry_json jsonb,
    faithfulness_score real,
    unsupported_claims_json jsonb
);

-- Migration for query_log tables created before faithfulness scoring was
-- added (LLM-as-judge score of whether the generated answer is actually
-- supported by its retrieved chunks) - no-ops on a fresh table.
alter table query_log add column if not exists faithfulness_score real;
alter table query_log add column if not exists unsupported_claims_json jsonb;

create index if not exists idx_nodes_parent on knowledge_nodes(parent_id);
create index if not exists idx_nodes_doc on knowledge_nodes(doc_id);
create index if not exists idx_chunks_parent on document_chunks(parent_id);
create index if not exists idx_chunks_doc on document_chunks(doc_id);
create index if not exists idx_entities_doc on entities(doc_id);
create index if not exists idx_edges_doc on entity_edges(doc_id);
create index if not exists idx_conversations_user on conversations(user_id);
create index if not exists idx_messages_conversation on messages(conversation_id);

-- Optional but recommended once you have more than a few thousand chunks:
-- speeds up cosine-similarity search via pgvector's approximate index.
-- create index if not exists idx_chunks_embedding on document_chunks
--     using hnsw (embedding vector_cosine_ops);
