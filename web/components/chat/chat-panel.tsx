"use client";

import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { toast } from "sonner";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  PromptInput,
  PromptInputBody,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputTools,
  PromptInputButton,
  PromptInputSubmit,
} from "@/components/ai-elements/prompt-input";
import { Attachments, Attachment, AttachmentPreview, AttachmentInfo } from "@/components/ai-elements/attachments";
import { Checkpoint, CheckpointIcon, CheckpointTrigger } from "@/components/ai-elements/checkpoint";
import { ChatMessageBubble } from "@/components/chat/chat-message";
import { Skeleton } from "@/components/ui/skeleton";
import { addDocumentToConversation, getConversation, restoreCheckpoint, sendMessage, uploadDocument } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import { MAX_CONVERSATION_DOCS } from "@/lib/types";
import type { ChatMessage, Conversation as ConversationRecord, ConversationMessage } from "@/lib/types";
import { Loader2, Paperclip } from "lucide-react";

const ACCEPTED_EXTENSIONS = ".md,.pdf,.docx,.xlsx,.xls,.csv";

let messageIdCounter = 0;
function nextMessageId() {
  messageIdCounter += 1;
  return `msg-${messageIdCounter}`;
}

function fromServerMessage(m: ConversationMessage): ChatMessage {
  return {
    id: `server-${m.id}`,
    serverId: m.id,
    role: m.role,
    content: m.content,
    thinking: m.thinking,
    sources: m.sources,
    faithfulness: m.faithfulness_score !== null ? { score: m.faithfulness_score, unsupported_claims: [] } : undefined,
  };
}

function MessageSkeleton({ align }: { align: "start" | "end" }) {
  return (
    <div className={`flex w-full ${align === "end" ? "justify-end" : "justify-start"}`}>
      <div className="flex flex-col gap-2">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-4 w-32" />
      </div>
    </div>
  );
}

function timeOfDayGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Morning";
  if (hour < 18) return "Afternoon";
  return "Evening";
}

function displayName(user: { email?: string; user_metadata?: { full_name?: string } } | null | undefined): string {
  const fullName = user?.user_metadata?.full_name?.trim();
  if (fullName) return fullName.split(" ")[0];
  if (!user?.email) return "there";
  const local = user.email.split("@")[0];
  return local.charAt(0).toUpperCase() + local.slice(1);
}

export function ChatPanel({ conversationId }: { conversationId: string }) {
  const { user } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [conversation, setConversation] = useState<ConversationRecord | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [advancedMode, setAdvancedMode] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [isAttaching, setIsAttaching] = useState(false);

  useEffect(() => {
    getConversation(conversationId)
      .then(({ conversation: conv, messages: history }) => {
        setConversation(conv);
        setMessages(history.map(fromServerMessage));
      })
      .catch(() => toast.error("Couldn't load this conversation."))
      .finally(() => setIsLoadingHistory(false));
  }, [conversationId]);

  async function handleSubmit({ text }: { text: string }) {
    const trimmed = text.trim();
    if (!trimmed || isSending) return;

    const userMessage: ChatMessage = { id: nextMessageId(), role: "user", content: trimmed };
    const pendingId = nextMessageId();

    setMessages((prev) => [...prev, userMessage, { id: pendingId, role: "assistant", content: "", pending: true }]);
    setIsSending(true);

    try {
      const result = await sendMessage(conversationId, trimmed, advancedMode);
      setMessages((prev) => prev.map((m) => (m.id === pendingId ? { ...fromServerMessage(result), id: pendingId } : m)));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Something went wrong reaching the server.";
      toast.error(message);
      setMessages((prev) => prev.map((m) => (m.id === pendingId ? { ...m, content: message, pending: false, error: true } : m)));
    } finally {
      setIsSending(false);
    }
  }

  async function handleAttachFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setIsAttaching(true);
    const toastId = toast.loading(`Processing "${file.name}"…`);
    try {
      const { docId } = await uploadDocument(file);
      const updated = await addDocumentToConversation(conversationId, docId);
      setConversation(updated);
      toast.success(`"${file.name}" added to this chat.`, { id: toastId });
    } catch (error) {
      const message = error instanceof Error ? error.message : `Couldn't attach "${file.name}".`;
      toast.error(message, { id: toastId });
    } finally {
      setIsAttaching(false);
    }
  }

  async function handleRestore(messageId: number) {
    try {
      const remaining = await restoreCheckpoint(conversationId, messageId);
      setMessages(remaining.map(fromServerMessage));
      toast.success("Restored to this point in the conversation.");
    } catch {
      toast.error("Couldn't restore this checkpoint.");
    }
  }

  const advancedModeToggle = (
    <label className="flex items-center gap-2 text-xs text-muted-foreground">
      <input
        type="checkbox"
        checked={advancedMode}
        onChange={(event) => setAdvancedMode(event.target.checked)}
        className="size-3.5 accent-foreground"
      />
      Advanced retrieval
    </label>
  );

  const atDocCap = (conversation?.doc_ids.length ?? 0) >= MAX_CONVERSATION_DOCS;

  const promptInput = (
    <PromptInput onSubmit={handleSubmit}>
      <PromptInputBody>
        <PromptInputTextarea placeholder="Ask a question…" disabled={isSending} />
      </PromptInputBody>
      <PromptInputFooter>
        <PromptInputTools>
          <PromptInputButton
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isSending || isAttaching || atDocCap}
            tooltip={atDocCap ? `Max ${MAX_CONVERSATION_DOCS} documents per chat` : "Attach a document"}
          >
            {isAttaching ? <Loader2 className="size-4 animate-spin" /> : <Paperclip className="size-4" />}
          </PromptInputButton>
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS}
            className="hidden"
            onChange={handleAttachFile}
          />
          {advancedModeToggle}
        </PromptInputTools>
        <PromptInputSubmit status={isSending ? "submitted" : undefined} disabled={isSending} />
      </PromptInputFooter>
    </PromptInput>
  );

  const attachmentChip = conversation && conversation.doc_ids.length > 0 && (
    <Attachments variant="inline">
      {conversation.doc_ids.map((docId, index) => (
        <Attachment
          key={docId}
          data={{
            type: "file",
            id: docId,
            filename: conversation.filenames[index] ?? docId,
            mediaType: "application/octet-stream",
            url: "",
          }}
        >
          <AttachmentPreview />
          <AttachmentInfo />
        </Attachment>
      ))}
    </Attachments>
  );

  // Empty conversation: centered greeting + prompt input, like a fresh
  // chat landing screen. Once the first message goes out, the layout
  // below takes over - scrollable history with the input pinned to the bottom.
  if (!isLoadingHistory && messages.length === 0) {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center gap-6 px-4">
        <div className="flex items-center gap-2 text-3xl font-semibold tracking-tight text-foreground">
          Good {timeOfDayGreeting()}, {displayName(user)}
        </div>
        {attachmentChip && <div className="flex justify-center">{attachmentChip}</div>}
        <div className="w-full">{promptInput}</div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col">
      {attachmentChip && <div className="border-b border-border px-4 py-2">{attachmentChip}</div>}

      <Conversation>
        <ConversationContent>
          {isLoadingHistory ? (
            <>
              <MessageSkeleton align="end" />
              <MessageSkeleton align="start" />
            </>
          ) : (
            messages.map((message, index) => {
              const isLastAssistantTurn =
                message.role === "assistant" && !message.pending && message.serverId !== undefined;
              const isFinalMessage = index === messages.length - 1;

              return (
                <div key={message.id} className="flex flex-col gap-2">
                  <ChatMessageBubble message={message} />
                  {isLastAssistantTurn && !isFinalMessage && (
                    <Checkpoint>
                      <CheckpointIcon />
                      <CheckpointTrigger tooltip="Restore conversation to this point" onClick={() => handleRestore(message.serverId!)}>
                        Restore here
                      </CheckpointTrigger>
                    </Checkpoint>
                  )}
                </div>
              );
            })
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      <div className="p-4">{promptInput}</div>
    </div>
  );
}
