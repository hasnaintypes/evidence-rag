// Mirrors the JSON shape returned by the backend's POST /chat endpoint
// (see server/src/query_pipeline.py's process_chat_query return dict).

// Mirrors MAX_CONVERSATION_DOCS in server/src/storage/database.py.
export const MAX_CONVERSATION_DOCS = 5;

export type Source = {
  index: number;
  document: string;
  page: number | null;
  section: string;
  snippet: string;
  // Signed, short-lived token required by GET /source/{filename} - see
  // server/src/security.py. Null only for a source shape built without
  // one (shouldn't happen from the real API; keeps this field optional
  // for safety).
  source_token: string | null;
};

export type Faithfulness = {
  score: number | null;
  unsupported_claims: string[];
};

export type ChatApiResponse = {
  reply: string;
  thinking: string;
  telemetry: Record<string, number>;
  chunks_matrix: unknown[];
  sources: Source[];
  faithfulness: Faithfulness;
};

export type ChatMessage = {
  id: string;
  serverId?: number; // DB row id, when this message has been persisted - used to target a checkpoint restore
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  sources?: Source[];
  faithfulness?: Faithfulness;
  pending?: boolean;
  error?: boolean;
  attachments?: { docId: string; filename: string }[];
};

// Mirrors GET /documents (see server/src/storage/database.py's
// list_documents(), which just selects * from the documents table).
export type DocumentRecord = {
  doc_id: string;
  filename: string;
  file_hash: string;
  ingested_at: string;
  node_count: number;
  chunk_count: number;
  embedding_model: string | null;
  user_id: string | null;
  status: "processing" | "ready" | "failed";
  chunks_indexed: number;
  chunks_total: number;
};

// Shared with the Documents management page's upload button - kept in
// sync with server/src/ingestion/pipeline.py's SUPPORTED_EXTENSIONS by
// hand (this is just an OS file-picker hint; the server independently
// validates on upload regardless of what this allows through).
export const ACCEPTED_DOCUMENT_EXTENSIONS = ".md,.pdf,.docx,.xlsx,.xls,.csv";

// Mirrors POST /conversations and GET /conversations/{id} (full detail -
// server/api/schemas.py's ConversationOut). GET /conversations (the
// sidebar list) returns the lighter ConversationListItem below instead.
export type Conversation = {
  id: string;
  doc_ids: string[];
  filenames: (string | null)[];
  pinned: boolean;
  title: string | null;
  created_at: string;
  updated_at: string;
};

// Mirrors GET /conversations's per-row shape (server/api/schemas.py's
// ConversationListItemOut) - no doc_ids/filenames, see Conversation above
// for the full shape a single opened conversation returns.
export type ConversationListItem = {
  id: string;
  title: string | null;
  pinned: boolean;
  created_at: string;
  updated_at: string;
};

// Mirrors GET /conversations's top-level response shape.
export type ConversationListPage = {
  conversations: ConversationListItem[];
  next_cursor: string | null;
  has_more: boolean;
};

// Mirrors a row from GET /conversations/{id} and the response shape of
// POST /conversations/{id}/messages.
export type ConversationMessage = {
  id: number;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  faithfulness_score: number | null;
  created_at: string;
  // Only present on the POST /conversations/{id}/messages response, not
  // when loading history via GET /conversations/{id}.
  telemetry?: Record<string, number>;
  chunks_matrix?: unknown[];
  thinking?: string;
  // Set only on the turn that just (re)generated the conversation's title
  // (the first turn, when the LLM call succeeds) - null on every other turn.
  title?: string | null;
};

// Mirrors GET /graph (see get_graph_data() in server/src/storage/database.py).
export type GraphNode = {
  id: number;
  label: string;
  doc_id: string;
  node_id: string;
};

export type GraphEdge = {
  from: number;
  to: number;
  weight: number;
};

export type GraphData = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

// Mirrors GET /graph/section/{node_id}.
export type GraphSection = {
  doc_id: string;
  heading_path: string | null;
  content: string | null;
  page: number | null;
  source_token: string;
};
