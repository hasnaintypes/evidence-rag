import type {
  Conversation,
  ConversationMessage,
  DocumentRecord,
  GraphData,
  GraphSection,
} from "@/lib/types";
import { useAuthStore } from "@/stores/auth-store";

// Defaults to the backend's local dev address (see server's `uvicorn
// api.app:app --reload`, default port 8000). Override with
// NEXT_PUBLIC_API_URL for any other deployment.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

function authHeaders(): Record<string, string> {
  // Reads the store's cached session synchronously instead of calling
  // supabase.auth.getSession() on every request - supabase-js's background
  // auto-refresh timer keeps the store's token current via the
  // onAuthStateChange subscription in stores/auth-store.ts.
  const token = useAuthStore.getState().session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const auth = authHeaders();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { ...auth, ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    throw new Error(`Request to ${path} failed with status ${response.status}`);
  }
  return response;
}

export type DocumentStatus = {
  status: "processing" | "ready" | "failed";
  chunks_indexed: number;
  chunks_total: number;
  chunk_count: number;
};

export async function getDocumentStatus(docId: string): Promise<DocumentStatus> {
  const response = await apiFetch(`/documents/${encodeURIComponent(docId)}/status`);
  return response.json() as Promise<DocumentStatus>;
}

export async function uploadDocument(file: File): Promise<{ docId: string; status: DocumentStatus["status"] }> {
  const form = new FormData();
  form.append("file", file);
  // No Content-Type header here - the browser sets the multipart boundary
  // itself when given a FormData body; setting it manually breaks the parse.
  const response = await apiFetch("/upload", { method: "POST", body: form });
  const data = (await response.json()) as { status: string; doc_id: string };

  // "unchanged" - already fully indexed (hash-based dedup). Anything else
  // ("processing") is a background job on the server now; the caller
  // attaches it right away and watches subscribeToDocumentStatus for when
  // it finishes instead of waiting here.
  return { docId: data.doc_id, status: data.status === "unchanged" ? "ready" : "processing" };
}

/**
 * Live status updates for one document via Server-Sent Events - replaces
 * polling GET /documents/{doc_id}/status on a timer. Uses fetch + a manual
 * stream reader rather than the native EventSource API because EventSource
 * can't send an Authorization header, which every other endpoint here
 * requires.
 *
 * Calls onUpdate for every status change and stops on its own once the
 * document reaches "ready" or "failed". Returns a function to cancel early
 * (e.g. on unmount).
 */
const SSE_MAX_RECONNECT_ATTEMPTS = 5;
const SSE_RECONNECT_BASE_DELAY_MS = 1000;

export function subscribeToDocumentStatus(docId: string, onUpdate: (status: DocumentStatus) => void): () => void {
  const controller = new AbortController();
  let attempt = 0;

  async function connect() {
    let reachedTerminal = false;
    try {
      const response = await apiFetch(`/documents/${encodeURIComponent(docId)}/events`, {
        signal: controller.signal,
      });
      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const dataLine = frame.split("\n").find((line) => line.startsWith("data:"));
          if (!dataLine) continue;
          const status = JSON.parse(dataLine.slice(5).trim()) as DocumentStatus;
          if (status.status === "ready" || status.status === "failed") reachedTerminal = true;
          onUpdate(status);
        }
      }
    } catch (error) {
      if ((error as Error).name === "AbortError") return;
    }

    if (reachedTerminal || controller.signal.aborted) return;

    // The connection dropped mid-processing (network blip, proxy timeout)
    // rather than the document reaching a terminal state - reconnect with
    // backoff instead of leaving the UI stuck on a stale "processing" badge.
    attempt += 1;
    if (attempt > SSE_MAX_RECONNECT_ATTEMPTS) return;
    await new Promise((resolve) => setTimeout(resolve, SSE_RECONNECT_BASE_DELAY_MS * attempt));
    if (!controller.signal.aborted) connect();
  }

  connect();

  return () => controller.abort();
}

export async function getDocuments(): Promise<DocumentRecord[]> {
  const response = await apiFetch("/documents");
  const data = (await response.json()) as { documents: DocumentRecord[] };
  return data.documents;
}

export async function getGraphData(docId?: string): Promise<GraphData> {
  const path = docId ? `/graph?doc_id=${encodeURIComponent(docId)}` : "/graph";
  const response = await apiFetch(path);
  return response.json() as Promise<GraphData>;
}

export async function getGraphSection(nodeId: string): Promise<GraphSection> {
  const response = await apiFetch(`/graph/section/${encodeURIComponent(nodeId)}`);
  return response.json() as Promise<GraphSection>;
}

export async function listConversations(): Promise<Conversation[]> {
  const response = await apiFetch("/conversations");
  const data = (await response.json()) as { conversations: Conversation[] };
  return data.conversations;
}

export async function createConversation(docIds: string[]): Promise<Conversation> {
  const response = await apiFetch("/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_ids: docIds }),
  });
  return response.json() as Promise<Conversation>;
}

export async function addDocumentToConversation(
  conversationId: string,
  docId: string
): Promise<Conversation> {
  const response = await apiFetch(`/conversations/${encodeURIComponent(conversationId)}/documents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: docId }),
  });
  return response.json() as Promise<Conversation>;
}

export async function updateConversation(
  conversationId: string,
  updates: { title?: string; pinned?: boolean }
): Promise<Conversation> {
  const response = await apiFetch(`/conversations/${encodeURIComponent(conversationId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  return response.json() as Promise<Conversation>;
}

export async function getConversation(
  conversationId: string
): Promise<{ conversation: Conversation; messages: ConversationMessage[] }> {
  const response = await apiFetch(`/conversations/${encodeURIComponent(conversationId)}`);
  return response.json();
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await apiFetch(`/conversations/${encodeURIComponent(conversationId)}`, { method: "DELETE" });
}

export async function sendMessage(
  conversationId: string,
  message: string,
  advancedMode: boolean
): Promise<ConversationMessage> {
  const response = await apiFetch(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, advanced_mode: advancedMode }),
  });
  return response.json() as Promise<ConversationMessage>;
}

export async function restoreCheckpoint(
  conversationId: string,
  messageId: number
): Promise<ConversationMessage[]> {
  const response = await apiFetch(
    `/conversations/${encodeURIComponent(conversationId)}/checkpoints/${messageId}/restore`,
    { method: "POST" }
  );
  const data = (await response.json()) as { messages: ConversationMessage[] };
  return data.messages;
}
