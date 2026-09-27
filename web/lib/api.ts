import type {
  ChatApiResponse,
  DocumentRecord,
  GraphData,
  GraphSection,
} from "@/lib/types";

// Defaults to the backend's local dev address (see server's `uvicorn
// api.app:app --reload`, default port 8000). Override with
// NEXT_PUBLIC_API_URL for any other deployment.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export async function sendChatMessage(
  message: string,
  advancedMode: boolean
): Promise<ChatApiResponse> {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, advanced_mode: advancedMode }),
  });

  if (!response.ok) {
    throw new Error(`Chat request failed with status ${response.status}`);
  }

  return response.json() as Promise<ChatApiResponse>;
}

export async function getDocuments(): Promise<DocumentRecord[]> {
  const response = await fetch(`${API_BASE_URL}/documents`);
  if (!response.ok) {
    throw new Error(`Documents request failed with status ${response.status}`);
  }
  const data = (await response.json()) as { documents: DocumentRecord[] };
  return data.documents;
}

export async function getGraphData(docId?: string): Promise<GraphData> {
  const url = docId
    ? `${API_BASE_URL}/graph?doc_id=${encodeURIComponent(docId)}`
    : `${API_BASE_URL}/graph`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Graph request failed with status ${response.status}`);
  }
  return response.json() as Promise<GraphData>;
}

export async function getGraphSection(nodeId: string): Promise<GraphSection> {
  const response = await fetch(
    `${API_BASE_URL}/graph/section/${encodeURIComponent(nodeId)}`
  );
  if (!response.ok) {
    throw new Error(`Graph section request failed with status ${response.status}`);
  }
  return response.json() as Promise<GraphSection>;
}
