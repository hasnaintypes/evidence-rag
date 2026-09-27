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
