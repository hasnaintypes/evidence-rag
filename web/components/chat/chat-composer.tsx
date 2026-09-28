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
import { Paperclip } from "lucide-react";

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
// The document is attached here (not via the sidebar) - uploading it,
// creating the conversation, and sending the first message all happen
// together on submit, then we navigate to the real conversation.
export function ChatComposer() {
  const router = useRouter();
  const { user } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [attachedFile, setAttachedFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function handleFileSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) setAttachedFile(file);
  }

  async function handleSubmit({ text }: { text: string }) {
    const trimmed = text.trim();
    if (!trimmed) {
      toast.error("Type a question first.");
      return;
    }
    if (!attachedFile) {
      toast.error("Attach a document to chat about.");
      return;
    }

    setIsSubmitting(true);
    try {
      const { docId } = await uploadDocument(attachedFile);
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
                  data={{ type: "file", id: "pending", filename: attachedFile.name, mediaType: attachedFile.type, url: "" }}
                  onRemove={() => setAttachedFile(null)}
                >
                  <AttachmentPreview />
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
                disabled={isSubmitting}
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
            <PromptInputSubmit status={isSubmitting ? "submitted" : undefined} disabled={isSubmitting} />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  );
}
