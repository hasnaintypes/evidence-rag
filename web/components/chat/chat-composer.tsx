"use client";

import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { useRouter } from "next/navigation";
import { toast } from "@/hooks/use-toast";
import {
  PromptInput,
  PromptInputProvider,
  PromptInputBody,
  PromptInputTextarea,
  PromptInputHeader,
  PromptInputFooter,
  PromptInputTools,
  PromptInputButton,
  PromptInputSubmit,
} from "@/components/ai-elements/prompt-input";
import {
  Attachments,
  Attachment,
  AttachmentPreview,
  AttachmentInfo,
  AttachmentRemove,
} from "@/components/ai-elements/attachments";
import {
  EvidenceMark,
  ChatGreeting,
  ComposerSuggestions,
} from "@/components/chat/chat-empty-state";
import { ChatHeader } from "@/components/chat/chat-header";
import { SourceCountBadge } from "@/components/chat/source-count-badge";
import { AttachmentProgressRing } from "@/components/chat/attachment-progress-ring";
import { AttachExistingDocumentPicker } from "@/components/chat/attach-existing-document-picker";
import { createConversation, subscribeToDocumentStatus, uploadDocument } from "@/lib/api";
import { stashPendingFirstMessage } from "@/lib/pending-first-message";
import { useAuth } from "@/hooks/use-auth";
import { useAdvancedMode } from "@/hooks/use-advanced-mode";
import { useConversationsStore } from "@/stores/conversations-store";
import {
  ACCEPTED_DOCUMENT_EXTENSIONS,
  MAX_CONVERSATION_DOCS,
  type DocumentRecord,
} from "@/lib/types";
import { Paperclip } from "lucide-react";

type PendingAttachment = {
  localId: string;
  filename: string;
  mediaType: string;
  docId: string | null;
  isUploading: boolean;
  progress: { indexed: number; total: number } | null;
};

function displayName(
  user: { email?: string; user_metadata?: { full_name?: string } } | null | undefined,
): string {
  const fullName = user?.user_metadata?.full_name?.trim();
  if (fullName) return fullName.split(" ")[0];
  if (!user?.email) return "there";
  const local = user.email.split("@")[0];
  return local.charAt(0).toUpperCase() + local.slice(1);
}

// The compose screen for a brand-new chat: no conversation exists yet.
// Documents are attached here (not via the sidebar), up to
// MAX_CONVERSATION_DOCS - the conversation's retrieval is scoped to
// exactly this set once created. Each file starts uploading the moment
// it's picked - not on submit - so by the time the user finishes typing
// their first question, processing is already underway (or done). Submit
// is blocked until every upload resolves.
export function ChatComposer() {
  const router = useRouter();
  const { user } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const removedIds = useRef<Set<string>>(new Set());
  const statusUnsubscribes = useRef<Record<string, () => void>>({});
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [advancedMode, setAdvancedMode] = useAdvancedMode();

  const isUploading = attachments.some((a) => a.isUploading);

  useEffect(() => {
    const unsubscribes = statusUnsubscribes.current;
    return () => {
      Object.values(unsubscribes).forEach((unsubscribe) => unsubscribe());
    };
  }, []);

  async function startUpload(file: File) {
    const localId = crypto.randomUUID();
    setAttachments((prev) => [
      ...prev,
      {
        localId,
        filename: file.name,
        mediaType: file.type,
        docId: null,
        isUploading: true,
        progress: null,
      },
    ]);
    try {
      // Upload only - returns right away. A document that still needs
      // embedding keeps isUploading true (so the chip keeps its spinner),
      // but the wait for "done" is now event-driven over
      // subscribeToDocumentStatus's SSE stream instead of a client poll.
      const { docId, status } = await uploadDocument(file);
      if (removedIds.current.has(localId)) return;

      if (status === "ready") {
        setAttachments((prev) =>
          prev.map((a) => (a.localId === localId ? { ...a, docId, isUploading: false } : a)),
        );
        return;
      }

      statusUnsubscribes.current[docId] = subscribeToDocumentStatus(docId, (docStatus) => {
        if (removedIds.current.has(localId)) {
          statusUnsubscribes.current[docId]?.();
          delete statusUnsubscribes.current[docId];
          return;
        }
        if (docStatus.status === "ready") {
          setAttachments((prev) =>
            prev.map((a) =>
              a.localId === localId ? { ...a, docId, isUploading: false, progress: null } : a,
            ),
          );
          delete statusUnsubscribes.current[docId];
        } else if (docStatus.status === "failed") {
          toast.error(`Couldn't index "${file.name}".`);
          setAttachments((prev) => prev.filter((a) => a.localId !== localId));
          delete statusUnsubscribes.current[docId];
        } else {
          setAttachments((prev) =>
            prev.map((a) =>
              a.localId === localId
                ? {
                    ...a,
                    progress: { indexed: docStatus.chunks_indexed, total: docStatus.chunks_total },
                  }
                : a,
            ),
          );
        }
      });
    } catch {
      if (removedIds.current.has(localId)) return;
      toast.error(`Couldn't attach "${file.name}".`);
      setAttachments((prev) => prev.filter((a) => a.localId !== localId));
    }
  }

  function handleFileSelected(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    const freeSlots = MAX_CONVERSATION_DOCS - attachments.length;
    if (files.length > freeSlots) {
      toast.error(`You can attach at most ${MAX_CONVERSATION_DOCS} documents per chat.`);
    }
    files.slice(0, freeSlots).forEach(startUpload);
  }

  function handleRemoveAttachment(localId: string) {
    removedIds.current.add(localId);
    setAttachments((prev) => prev.filter((a) => a.localId !== localId));
  }

  function handleAttachExisting(doc: DocumentRecord) {
    if (attachments.length >= MAX_CONVERSATION_DOCS) {
      toast.error(`You can attach at most ${MAX_CONVERSATION_DOCS} documents per chat.`);
      return;
    }
    // Already indexed (that's what made it selectable in the picker in
    // the first place) - attaches straight in as "ready", no upload or
    // status watch needed.
    setAttachments((prev) => [
      ...prev,
      {
        localId: doc.doc_id,
        filename: doc.filename,
        mediaType: "",
        docId: doc.doc_id,
        isUploading: false,
        progress: null,
      },
    ]);
  }

  async function handleSubmit({ text }: { text: string }) {
    if (isSubmitting) return;
    const trimmed = text.trim();
    if (!trimmed) {
      toast.error("Type a question first.");
      return;
    }
    if (attachments.length === 0) {
      toast.error("Attach at least one document to chat about.");
      return;
    }
    if (isUploading || attachments.some((a) => !a.docId)) {
      toast.error("Still processing your documents - hang on.");
      return;
    }

    setIsSubmitting(true);
    try {
      const docIds = attachments.map((a) => a.docId!);
      const conversation = await createConversation(docIds);
      useConversationsStore.getState().insertOptimistic({
        id: conversation.id,
        title: null,
        pinned: false,
        created_at: conversation.created_at,
        updated_at: conversation.updated_at,
      });
      // Navigate the instant the conversation exists, rather than blocking
      // here on the full reply - ChatPanel picks the message back up via
      // takePendingFirstMessage() and sends it itself, so the user sees
      // the real conversation (their message + the thinking state) right
      // away instead of staring at this same screen through the whole
      // first response.
      stashPendingFirstMessage(conversation.id, trimmed);
      router.push(`/chat/${conversation.id}`);
    } catch {
      toast.error("Couldn't start the chat.");
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <ChatHeader
        title="New chat"
        advancedMode={advancedMode}
        onAdvancedModeChange={setAdvancedMode}
      />
      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center gap-7 px-4">
        <EvidenceMark />
        <ChatGreeting name={displayName(user)} />

        <PromptInputProvider>
          <div className="flex w-full flex-col gap-4">
            <PromptInput onSubmit={handleSubmit}>
              {attachments.length > 0 && (
                <PromptInputHeader>
                  <Attachments variant="card">
                    {attachments.map((a) => (
                      <Attachment
                        key={a.localId}
                        data={{
                          type: "file",
                          id: a.docId ?? a.localId,
                          filename: a.filename,
                          mediaType: a.mediaType,
                          url: "",
                        }}
                        onRemove={() => handleRemoveAttachment(a.localId)}
                      >
                        <AttachmentPreview>
                          {a.isUploading && a.progress && (
                            <AttachmentProgressRing
                              indexed={a.progress.indexed}
                              total={a.progress.total}
                            />
                          )}
                        </AttachmentPreview>
                        <AttachmentInfo />
                        <AttachmentRemove />
                      </Attachment>
                    ))}
                  </Attachments>
                </PromptInputHeader>
              )}
              <PromptInputBody>
                <PromptInputTextarea
                  placeholder="Ask a question about your documents…"
                  disabled={isSubmitting}
                />
              </PromptInputBody>
              <PromptInputFooter>
                <PromptInputTools>
                  <PromptInputButton
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isSubmitting || attachments.length >= MAX_CONVERSATION_DOCS}
                    tooltip={
                      attachments.length >= MAX_CONVERSATION_DOCS
                        ? `Max ${MAX_CONVERSATION_DOCS} documents per chat`
                        : "Attach a document"
                    }
                  >
                    <Paperclip className="size-4" />
                  </PromptInputButton>
                  <AttachExistingDocumentPicker
                    excludeDocIds={attachments.map((a) => a.docId).filter((id) => id !== null)}
                    disabled={isSubmitting || attachments.length >= MAX_CONVERSATION_DOCS}
                    onSelect={handleAttachExisting}
                  />
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept={ACCEPTED_DOCUMENT_EXTENSIONS}
                    multiple
                    className="hidden"
                    onChange={handleFileSelected}
                  />
                  <SourceCountBadge count={attachments.length} max={MAX_CONVERSATION_DOCS} />
                </PromptInputTools>
                <PromptInputSubmit
                  status={isSubmitting ? "submitted" : undefined}
                  disabled={isSubmitting || isUploading}
                />
              </PromptInputFooter>
            </PromptInput>

            <ComposerSuggestions />
          </div>
        </PromptInputProvider>
      </div>
    </div>
  );
}
