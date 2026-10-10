"use client";

import { Loader2, AlertCircle } from "lucide-react";
import { Attachments, Attachment, AttachmentPreview, AttachmentInfo } from "@/components/ai-elements/attachments";
import type { DocumentStatus } from "@/lib/api";

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
        const status = statuses[attachment.docId];
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
                status === "processing" ? (
                  <Loader2 className="size-4 animate-spin text-muted-foreground" />
                ) : status === "failed" ? (
                  <AlertCircle className="size-4 text-destructive" />
                ) : undefined
              }
            />
            <AttachmentInfo />
            {status === "processing" && <span className="text-xs text-muted-foreground">Indexing…</span>}
            {status === "failed" && <span className="text-xs text-destructive">Couldn't index</span>}
          </Attachment>
        );
      })}
    </Attachments>
  );
}
