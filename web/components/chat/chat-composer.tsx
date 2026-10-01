"use client";

import { useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  PromptInput,
  PromptInputBody,
  PromptInputTextarea,
  PromptInputHeader,
  PromptInputFooter,
  PromptInputTools,
  PromptInputButton,
  PromptInputSubmit,
} from "@/components/ai-elements/prompt-input";
import { Attachments, Attachment, AttachmentPreview, AttachmentInfo, AttachmentRemove } from "@/components/ai-elements/attachments";
import { createConversation, sendMessage, uploadDocument } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import { MAX_CONVERSATION_DOCS } from "@/lib/types";
import { Loader2, Paperclip } from "lucide-react";

const ACCEPTED_EXTENSIONS = ".md,.pdf,.docx,.xlsx,.xls,.csv";

type PendingAttachment = {
  localId: string;
  file: File;
  docId: string | null;
  isUploading: boolean;
};

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
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isUploading = attachments.some((a) => a.isUploading);

  async function startUpload(file: File) {
    const localId = crypto.randomUUID();
    setAttachments((prev) => [...prev, { localId, file, docId: null, isUploading: true }]);
    const toastId = toast.loading(`Processing "${file.name}"…`);
    try {
      const result = await uploadDocument(file, (indexed, total) => {
        if (removedIds.current.has(localId) || total === 0) return;
        toast.loading(`Processing "${file.name}" (${indexed}/${total} chunks)…`, { id: toastId });
      });
      if (removedIds.current.has(localId)) return;
      setAttachments((prev) => prev.map((a) => (a.localId === localId ? { ...a, docId: result.docId, isUploading: false } : a)));
      toast.success(`"${file.name}" is ready.`, { id: toastId });
    } catch {
      if (removedIds.current.has(localId)) return;
      toast.error(`Couldn't process "${file.name}".`, { id: toastId });
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
      await sendMessage(conversation.id, trimmed, true);
      router.push(`/chat/${conversation.id}`);
    } catch {
      toast.error("Couldn't start the chat.");
      setIsSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center gap-6 px-4">
      <div className="flex items-center gap-2 text-3xl font-semibold tracking-tight text-foreground">
        Good {timeOfDayGreeting()}, {displayName(user)}
      </div>

      <div className="w-full">
        <PromptInput onSubmit={handleSubmit}>
          {attachments.length > 0 && (
            <PromptInputHeader>
              <Attachments variant="card">
                {attachments.map((a) => (
                  <Attachment
                    key={a.localId}
                    data={{ type: "file", id: a.docId ?? a.localId, filename: a.file.name, mediaType: a.file.type, url: "" }}
                    onRemove={() => handleRemoveAttachment(a.localId)}
                  >
                    <AttachmentPreview
                      fallbackIcon={a.isUploading ? <Loader2 className="size-3 animate-spin text-muted-foreground" /> : undefined}
                    />
                    <AttachmentInfo />
                    <AttachmentRemove />
                  </Attachment>
                ))}
              </Attachments>
            </PromptInputHeader>
          )}
          <PromptInputBody>
            <PromptInputTextarea placeholder="Ask a question about your documents…" disabled={isSubmitting} />
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
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_EXTENSIONS}
                multiple
                className="hidden"
                onChange={handleFileSelected}
              />
            </PromptInputTools>
            <PromptInputSubmit status={isSubmitting ? "submitted" : undefined} disabled={isSubmitting || isUploading} />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  );
}
