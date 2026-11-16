// Hands a brand-new conversation's first message across the
// chat-composer -> /chat/[conversationId] navigation, so the composer can
// navigate the instant the conversation exists instead of blocking on the
// full round trip to Gemini first - the destination page then sends it and
// shows the real pending/thinking state right away, the way ChatGPT/Gemini
// open the conversation immediately rather than waiting on the same
// greeting screen for the first reply.
//
// Plain in-memory map, not persisted - this only needs to survive a single
// client-side router.push() in the same tab, not a reload.
const pending = new Map<string, string>();

export function stashPendingFirstMessage(conversationId: string, text: string) {
  pending.set(conversationId, text);
}

export function takePendingFirstMessage(conversationId: string): string | undefined {
  const text = pending.get(conversationId);
  pending.delete(conversationId);
  return text;
}
