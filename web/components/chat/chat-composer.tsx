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
import { Loader2, Paperclip } from "lucide-react";

const ACCEPTED_EXTENSIONS = ".md,.pdf,.docx,.xlsx,.xls,.csv";

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
// The document is attached here (not via the sidebar). Uploading starts
// the moment a file is picked - not on submit - so by the time the user
// finishes typing their first question, processing is already underway
// (or done). Submit is blocked until that upload resolves.
export function ChatComposer() {
  const router = useRouter();
  const { user } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadGeneration = useRef(0);
  const [attachedFile, setAttachedFile] = useState<File | null>(null);
  const [docId, setDocId] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function startUpload(file: File) {
    const generation = ++uploadGeneration.current;
    setAttachedFile(file);
    setDocId(null);
    setIsUploading(true);
    const toastId = toast.loading(`Processing "${file.name}"…`);
    try {
      const result = await uploadDocument(file);
      if (generation !== uploadGeneration.current) return;
      setDocId(result.docId);
      toast.success(`"${file.name}" is ready - ask your question.`, { id: toastId });
    } catch {
      if (generation !== uploadGeneration.current) return;
      toast.error(`Couldn't process "${file.name}".`, { id: toastId });
      setAttachedFile(null);
    } finally {
      if (generation === uploadGeneration.current) setIsUploading(false);
    }
  }

  function handleFileSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) startUpload(file);
  }

  function handleRemoveAttachment() {
    uploadGeneration.current += 1;
    setAttachedFile(null);
    setDocId(null);
    setIsUploading(false);
  }

  async function handleSubmit({ text }: { text: string }) {
    if (isSubmitting) return;
    const trimmed = text.trim();
    if (!trimmed) {
      toast.error("Type a question first.");
      return;
    }
    if (!attachedFile) {
      toast.error("Attach a document to chat about.");
      return;
    }
    if (isUploading || !docId) {
      toast.error("Still processing the document - hang on.");
      return;
    }

    setIsSubmitting(true);
    try {
      const conversation = await createConversation(docId);
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
          {attachedFile && (
            <PromptInputHeader>
              <Attachments variant="inline">
                <Attachment
                  data={{ type: "file", id: docId ?? "pending", filename: attachedFile.name, mediaType: attachedFile.type, url: "" }}
                  onRemove={handleRemoveAttachment}
                >
                  <AttachmentPreview
                    fallbackIcon={isUploading ? <Loader2 className="size-3 animate-spin text-muted-foreground" /> : undefined}
                  />
                  <AttachmentInfo />
                  <AttachmentRemove />
                </Attachment>
              </Attachments>
            </PromptInputHeader>
          )}
          <PromptInputBody>
            <PromptInputTextarea placeholder="Ask a question about your document…" disabled={isSubmitting} />
          </PromptInputBody>
          <PromptInputFooter>
            <PromptInputTools>
              <PromptInputButton
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isSubmitting || isUploading}
                tooltip="Attach a document"
              >
                <Paperclip className="size-4" />
              </PromptInputButton>
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_EXTENSIONS}
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
