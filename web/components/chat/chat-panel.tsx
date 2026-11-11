"use client";

import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { toast } from "@/hooks/use-toast";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  PromptInput,
  PromptInputProvider,
  PromptInputBody,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputTools,
  PromptInputButton,
  PromptInputSubmit,
} from "@/components/ai-elements/prompt-input";
import { Checkpoint, CheckpointIcon, CheckpointTrigger } from "@/components/ai-elements/checkpoint";
import { ChatMessageBubble } from "@/components/chat/chat-message";
import { AttachmentChips } from "@/components/chat/attachment-chips";
import {
  EvidenceMark,
  ChatGreeting,
  ComposerSuggestions,
} from "@/components/chat/chat-empty-state";
import { ChatHeader } from "@/components/chat/chat-header";
import { SourceCountBadge } from "@/components/chat/source-count-badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  addDocumentToConversation,
  getConversation,
  getDocumentStatus,
  restoreCheckpoint,
  sendMessage,
  subscribeToDocumentStatus,
  uploadDocument,
  type DocumentStatus,
} from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import { useAdvancedMode } from "@/hooks/use-advanced-mode";
import { useConversationsStore } from "@/stores/conversations-store";
import { MAX_CONVERSATION_DOCS } from "@/lib/types";
import type {
  ChatMessage,
  Conversation as ConversationRecord,
  ConversationMessage,
} from "@/lib/types";
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
    faithfulness:
      m.faithfulness_score !== null
        ? { score: m.faithfulness_score, unsupported_claims: [] }
        : undefined,
  };
}

function MessageSkeleton({ align }: { align: "start" | "end" }) {
  return (
    <div className={`flex w-full ${align === "end" ? "justify-end" : "justify-start"}`}>
      <div className="flex flex-col gap-2">
        <Skeleton className="h-4 w-64" />
        <Skeleton className="h-4 w-52" />
        <Skeleton className="h-4 w-36" />
      </div>
    </div>
  );
}

function displayName(
  user: { email?: string; user_metadata?: { full_name?: string } } | null | undefined,
): string {
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
  const [isSending, setIsSending] = useState(false);
  const [isAttaching, setIsAttaching] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<
    { docId: string; filename: string }[]
  >([]);
  const [docStatuses, setDocStatuses] = useState<Record<string, DocumentStatus["status"]>>({});
  const statusUnsubscribes = useRef<Record<string, () => void>>({});
  const [advancedMode, setAdvancedMode] = useAdvancedMode();

  useEffect(() => {
    getConversation(conversationId)
      .then(({ conversation: conv, messages: history }) => {
        setConversation(conv);
        setMessages(history.map(fromServerMessage));

        // A document can still be indexing from a previous visit (closed
        // the tab, or the SSE connection dropped) - reconcile against the
        // current server state instead of assuming "ready" just because
        // there's no live subscription for it yet.
        conv.doc_ids.forEach((docId, index) => {
          getDocumentStatus(docId)
            .then((docStatus) => {
              if (docStatus.status !== "processing") return;
              setDocStatuses((prev) => ({ ...prev, [docId]: "processing" }));
              watchDocumentStatus(docId, conv.filenames[index] ?? docId);
            })
            .catch(() => {});
        });
      })
      .catch(() => toast.error("Couldn't load this conversation."))
      .finally(() => setIsLoadingHistory(false));
  }, [conversationId]);

  useEffect(() => {
    const unsubscribes = statusUnsubscribes.current;
    return () => {
      Object.values(unsubscribes).forEach((unsubscribe) => unsubscribe());
    };
  }, []);

  function watchDocumentStatus(docId: string, filename: string) {
    statusUnsubscribes.current[docId]?.();
    statusUnsubscribes.current[docId] = subscribeToDocumentStatus(docId, (status) => {
      setDocStatuses((prev) => ({ ...prev, [docId]: status.status }));
      if (status.status === "ready") {
        toast.success(`"${filename}" finished indexing - ready to search.`);
        delete statusUnsubscribes.current[docId];
      } else if (status.status === "failed") {
        toast.error(`Couldn't index "${filename}".`);
        delete statusUnsubscribes.current[docId];
      }
    });
  }

  async function handleSubmit({ text }: { text: string }) {
    const trimmed = text.trim();
    if (!trimmed || isSending) return;

    const userMessage: ChatMessage = {
      id: nextMessageId(),
      role: "user",
      content: trimmed,
      attachments: pendingAttachments.length > 0 ? pendingAttachments : undefined,
    };
    const pendingId = nextMessageId();

    setMessages((prev) => [
      ...prev,
      userMessage,
      { id: pendingId, role: "assistant", content: "", pending: true },
    ]);
    setPendingAttachments([]);
    setIsSending(true);

    try {
      const result = await sendMessage(conversationId, trimmed, advancedMode);
      setMessages((prev) =>
        prev.map((m) => (m.id === pendingId ? { ...fromServerMessage(result), id: pendingId } : m)),
      );
      if (result.title) {
        setConversation((prev) => (prev ? { ...prev, title: result.title! } : prev));
        useConversationsStore.getState().patch(conversationId, { title: result.title });
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Something went wrong reaching the server.";
      toast.error(message);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === pendingId ? { ...m, content: message, pending: false, error: true } : m,
        ),
      );
    } finally {
      setIsSending(false);
    }
  }

  async function handleAttachFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setIsAttaching(true);
    try {
      // Upload only - returns as soon as the file is saved and the fast
      // parse/chunk phase is done. Embedding runs as a server-side
      // background job (see /upload), so it's never waited on here: the
      // file is attached and usable right away, and docStatuses/the SSE
      // watch below just reflects when it finishes indexing.
      const { docId, status } = await uploadDocument(file);
      const updated = await addDocumentToConversation(conversationId, docId);
      setConversation(updated);
      setPendingAttachments((prev) => [...prev, { docId, filename: file.name }]);
      toast.success(`"${file.name}" attached.`);

      if (status === "processing") {
        setDocStatuses((prev) => ({ ...prev, [docId]: "processing" }));
        watchDocumentStatus(docId, file.name);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : `Couldn't attach "${file.name}".`;
      toast.error(message);
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

  const docCount = conversation?.doc_ids.length ?? 0;
  const atDocCap = docCount >= MAX_CONVERSATION_DOCS;

  const promptInput = (
    <PromptInput onSubmit={handleSubmit}>
      {pendingAttachments.length > 0 && (
        <div className="px-3 pt-3">
          <AttachmentChips attachments={pendingAttachments} statuses={docStatuses} />
        </div>
      )}
      <PromptInputBody>
        <PromptInputTextarea placeholder="Ask a question…" disabled={isSending} />
      </PromptInputBody>
      <PromptInputFooter>
        <PromptInputTools>
          <PromptInputButton
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isSending || isAttaching || atDocCap}
            tooltip={
              atDocCap ? `Max ${MAX_CONVERSATION_DOCS} documents per chat` : "Attach a document"
            }
          >
            {isAttaching ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Paperclip className="size-4" />
            )}
          </PromptInputButton>
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS}
            className="hidden"
            onChange={handleAttachFile}
          />
          <SourceCountBadge count={docCount} max={MAX_CONVERSATION_DOCS} />
        </PromptInputTools>
        <PromptInputSubmit status={isSending ? "submitted" : undefined} disabled={isSending} />
      </PromptInputFooter>
    </PromptInput>
  );

  // Empty conversation: centered greeting + prompt input, like a fresh
  // chat landing screen. Once the first message goes out, the layout
  // below takes over - scrollable history with the input pinned to the bottom.
  // Only this branch wraps promptInput in PromptInputProvider, lifting its
  // textInput state so a suggestion-card click can prefill it (see
  // ai-elements/prompt-input.tsx's controller) - the active-conversation
  // branch below renders the same promptInput element uncontrolled.
  const headerTitle = conversation?.title ?? conversation?.filenames[0] ?? "Chat";

  if (!isLoadingHistory && messages.length === 0) {
    return (
      <div className="flex h-full min-h-0 flex-1 flex-col">
        <ChatHeader
          title={headerTitle}
          advancedMode={advancedMode}
          onAdvancedModeChange={setAdvancedMode}
        />
        <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center gap-7 px-4">
          <EvidenceMark />
          <ChatGreeting name={displayName(user)} />
          <PromptInputProvider>
            <div className="flex w-full flex-col gap-4">
              {promptInput}
              <ComposerSuggestions />
            </div>
          </PromptInputProvider>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <ChatHeader
        title={headerTitle}
        subtitle={
          docCount > 0 ? `${docCount} document${docCount === 1 ? "" : "s"} attached` : undefined
        }
        advancedMode={advancedMode}
        onAdvancedModeChange={setAdvancedMode}
      />
      <div className="mx-auto flex w-full max-w-3xl min-h-0 flex-1 flex-col">
        <Conversation>
          <ConversationContent>
            {isLoadingHistory ? (
              <>
                <MessageSkeleton align="end" />
                <MessageSkeleton align="start" />
                <MessageSkeleton align="end" />
                <MessageSkeleton align="start" />
              </>
            ) : (
              messages.map((message, index) => {
                const isLastAssistantTurn =
                  message.role === "assistant" &&
                  !message.pending &&
                  message.serverId !== undefined;
                const isFinalMessage = index === messages.length - 1;

                // Narrowed to just this message's own attachments so a
                // docStatuses update only changes the prop reference (and
                // defeats ChatMessageBubble's memo) for the message that
                // actually cares, not every bubble in the list.
                const relevantStatuses = message.attachments
                  ? Object.fromEntries(
                      message.attachments
                        .filter((a) => a.docId in docStatuses)
                        .map((a) => [a.docId, docStatuses[a.docId]]),
                    )
                  : undefined;

                return (
                  <div key={message.id} className="flex flex-col gap-2">
                    <ChatMessageBubble message={message} docStatuses={relevantStatuses} />
                    {isLastAssistantTurn && !isFinalMessage && (
                      <Checkpoint>
                        <CheckpointIcon />
                        <CheckpointTrigger
                          tooltip="Restore conversation to this point"
                          onClick={() => handleRestore(message.serverId!)}
                        >
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
    </div>
  );
}
