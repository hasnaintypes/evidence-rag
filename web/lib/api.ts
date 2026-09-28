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

export async function uploadDocument(file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  // No Content-Type header here - the browser sets the multipart boundary
  // itself when given a FormData body; setting it manually breaks the parse.
  await apiFetch("/upload", { method: "POST", body: form });
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

export async function createConversation(docId: string): Promise<Conversation> {
  const response = await apiFetch("/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: docId }),
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
