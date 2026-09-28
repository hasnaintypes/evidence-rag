// Mirrors the JSON shape returned by the backend's POST /chat endpoint
// (see server/src/query_pipeline.py's process_chat_query return dict).

export type Source = {
  index: number;
  document: string;
  page: number | null;
  section: string;
  snippet: string;
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
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  faithfulness?: Faithfulness;
  pending?: boolean;
  error?: boolean;
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
};

// Mirrors GET /conversations and POST /conversations
// (server/api/routers/conversations.py).
export type Conversation = {
  id: string;
  doc_id: string;
  filename: string | null;
  title: string | null;
  created_at: string;
  updated_at: string;
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
};
