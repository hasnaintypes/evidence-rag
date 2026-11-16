"use client";

import { AlertCircle } from "lucide-react";
import {
  Attachments,
  Attachment,
  AttachmentPreview,
  AttachmentInfo,
} from "@/components/ai-elements/attachments";
import { AttachmentProgressRing } from "@/components/chat/attachment-progress-ring";
import type { DocumentStatus } from "@/lib/api";

// A document reads as "attached" the instant it's uploaded - indexing then
// runs in the background, surfaced here as a progress ring over the file
// icon (chunks_indexed/chunks_total, live over SSE) rather than a plain
// spinner, so the wait actually looks like it's going somewhere.
export function AttachmentChips({
  attachments,
  statuses,
}: {
  attachments: { docId: string; filename: string }[];
  statuses: Record<string, DocumentStatus>;
}) {
  if (attachments.length === 0) return null;

  return (
    <Attachments variant="card">
      {attachments.map((attachment) => {
        const docStatus = statuses[attachment.docId];
        const failed = docStatus?.status === "failed";
        const processing = docStatus?.status === "processing";
        return (
          <Attachment
            key={attachment.docId}
            data={{
              type: "file",
              id: attachment.docId,
              filename: attachment.filename,
              mediaType: "application/octet-stream",
              url: "",
            }}
          >
            <AttachmentPreview
              fallbackIcon={
                failed ? <AlertCircle className="size-4 text-destructive" /> : undefined
              }
            >
              {processing && (
                <AttachmentProgressRing
                  indexed={docStatus.chunks_indexed}
                  total={docStatus.chunks_total}
                />
              )}
            </AttachmentPreview>
            <AttachmentInfo />
            {failed && <span className="text-xs text-destructive">Couldn&apos;t index</span>}
          </Attachment>
        );
      })}
    </Attachments>
  );
}
