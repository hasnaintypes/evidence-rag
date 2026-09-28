"use client";

import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { ChatMessageBubble } from "@/components/chat/chat-message";
import { getConversation, sendMessage } from "@/lib/api";
import type { ChatMessage, ConversationMessage } from "@/lib/types";

let messageIdCounter = 0;
function nextMessageId() {
  messageIdCounter += 1;
  return `msg-${messageIdCounter}`;
}

function fromServerMessage(m: ConversationMessage): ChatMessage {
  return {
    id: `server-${m.id}`,
    role: m.role,
    content: m.content,
    sources: m.sources,
    faithfulness:
      m.faithfulness_score !== null ? { score: m.faithfulness_score, unsupported_claims: [] } : undefined,
  };
}

export function ChatPanel({ conversationId }: { conversationId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [input, setInput] = useState("");
  const [advancedMode, setAdvancedMode] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getConversation(conversationId)
      .then(({ messages: history }) => setMessages(history.map(fromServerMessage)))
      .catch(() => setMessages([]))
      .finally(() => setIsLoadingHistory(false));
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isSending) return;

    const userMessage: ChatMessage = {
      id: nextMessageId(),
      role: "user",
      content: trimmed,
    };
    const pendingId = nextMessageId();

    setMessages((prev) => [
      ...prev,
      userMessage,
      { id: pendingId, role: "assistant", content: "", pending: true },
    ]);
    setInput("");
    setIsSending(true);

    try {
      const result = await sendMessage(conversationId, trimmed, advancedMode);
      setMessages((prev) =>
        prev.map((message) =>
          message.id === pendingId
            ? {
                ...message,
                content: result.content,
                sources: result.sources,
                faithfulness:
                  result.faithfulness_score !== null
                    ? { score: result.faithfulness_score, unsupported_claims: [] }
                    : undefined,
                pending: false,
              }
            : message
        )
      );
    } catch (error) {
      setMessages((prev) =>
        prev.map((message) =>
          message.id === pendingId
            ? {
                ...message,
                content:
                  error instanceof Error
                    ? `Something went wrong reaching the server: ${error.message}`
                    : "Something went wrong reaching the server.",
                pending: false,
                error: true,
              }
            : message
        )
      );
    } finally {
      setIsSending(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 px-4 py-6">
      <header className="flex items-center justify-between border-b border-border pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight">EvidenceRAG</h1>
          <p className="text-xs text-muted-foreground">
            Ask a question about this document.
          </p>
        </div>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={advancedMode}
            onChange={(event) => setAdvancedMode(event.target.checked)}
            className="size-3.5 accent-foreground"
          />
          Advanced retrieval
        </label>
      </header>

      <div className="flex flex-1 flex-col gap-3">
        {isLoadingHistory ? (
          <p className="mt-10 text-center text-sm text-muted-foreground">Loading conversation…</p>
        ) : messages.length === 0 ? (
          <p className="mt-10 text-center text-sm text-muted-foreground">
            No messages yet — ask something about this document.
          </p>
        ) : (
          messages.map((message) => (
            <ChatMessageBubble key={message.id} message={message} />
          ))
        )}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-2 border-t border-border pt-4"
      >
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question…"
          rows={2}
          disabled={isSending}
          className="w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
        />
        <div className="flex justify-end">
          <Button type="submit" disabled={isSending || !input.trim()}>
            {isSending ? "Sending…" : "Send"}
          </Button>
        </div>
      </form>
    </div>
  );
}
