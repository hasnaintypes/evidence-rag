import type { ChatApiResponse } from "@/lib/types";

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
