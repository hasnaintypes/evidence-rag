"use client";

import { AlertCircle } from "lucide-react";
import {
  Attachments,
  Attachment,
  AttachmentPreview,
  AttachmentInfo,
} from "@/components/ai-elements/attachments";
import type { DocumentStatus } from "@/lib/api";

// Indexing happens silently in the background (see subscribeToDocumentStatus
// callers) - a document reads as "attached" the instant it's uploaded, with
// no processing/spinner treatment, so the only thing surfaced here is the
// rare terminal failure case.
export function AttachmentChips({
  attachments,
  statuses,
}: {
  attachments: { docId: string; filename: string }[];
  statuses: Record<string, DocumentStatus["status"]>;
}) {
  if (attachments.length === 0) return null;

  return (
    <Attachments variant="card">
      {attachments.map((attachment) => {
        const failed = statuses[attachment.docId] === "failed";
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
            />
            <AttachmentInfo />
            {failed && <span className="text-xs text-destructive">Couldn&apos;t index</span>}
          </Attachment>
        );
      })}
    </Attachments>
  );
}
