"use client";

import { memo, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { BookOpenIcon } from "lucide-react";
import { Message, MessageContent, MessageResponse } from "@/components/ai-elements/message";
import { AttachmentChips } from "@/components/chat/attachment-chips";
import { FaithfulnessCard, parseFaithfulnessGate } from "@/components/chat/faithfulness-card";
import { ThinkingIndicator } from "@/components/chat/thinking-indicator";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import type { DocumentStatus } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

function sourceHref(document: string, page: number | null, token: string | null) {
  // token is required by the backend (see server/src/security.py) - a
  // null token (shouldn't happen from the real API) just produces a link
  // the backend will reject with 403 rather than a broken URL.
  const url = `${API_BASE_URL}/source/${encodeURIComponent(document)}?token=${encodeURIComponent(token ?? "")}`;
  return page ? `${url}#page=${page}` : url;
}

const CITATION_MARKER_RE = /\[(\d+)\]/g;

// The model is instructed (see query_pipeline.py's generation prompt
// instruction 6) to inline [N] markers citing a numbered source - turns
// each in-range one into a markdown link Streamdown already knows how to
// parse as an anchor, which `CiteLink` below then intercepts instead of
// letting it navigate. Bounds-checked here too (not just server-side,
// see _sanitize_citation_markers) since a document's own text could
// coincidentally contain a bracketed number that isn't really a citation.
function linkifyCitations(content: string, maxIndex: number): string {
  return content.replace(CITATION_MARKER_RE, (match, n) =>
    Number(n) >= 1 && Number(n) <= maxIndex ? `[[${n}]](#cite-${n})` : match,
  );
}

function CiteLink({
  href,
  children,
  sources,
  onSelectSource,
}: {
  href?: string;
  children?: ReactNode;
  sources: ChatMessage["sources"];
  onSelectSource: (index: number) => void;
}) {
  const match = /^#cite-(\d+)$/.exec(href ?? "");
  if (!match) {
    // Not a citation link - a real markdown link in the answer text,
    // render it normally.
    return (
      <a href={href} target="_blank" rel="noreferrer">
        {children}
      </a>
    );
  }
  const index = Number(match[1]);
  const exists = sources?.some((s) => s.index === index);
  if (!exists) return <>{children}</>; // out-of-range already sanitized server-side, but guard anyway

  return (
    <button
      type="button"
      onClick={() => onSelectSource(index)}
      className="citation-marker mx-0.5 inline-flex"
    >
      <Badge variant="secondary" className="rounded-full px-1.5 text-[10px]">
        {index}
      </Badge>
    </button>
  );
}

function ChatMessageBubbleImpl({
  message,
  docStatuses = {},
  onRetry,
  advancedMode = true,
}: {
  message: ChatMessage;
  docStatuses?: Record<string, DocumentStatus>;
  onRetry?: () => void;
  advancedMode?: boolean;
}) {
  const isUser = message.role === "user";
  const [sheetOpen, setSheetOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState<number | null>(null);
  const sourceRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const gate = !isUser ? parseFaithfulnessGate(message.content) : null;

  function openSources(index: number | null) {
    setHighlightedIndex(index);
    setSheetOpen(true);
  }

  // Scrolls the clicked source into view once the sheet's content has
  // actually mounted/settled - a plain scrollIntoView on click would run
  // before the sheet's own open transition (components/ui/sheet.tsx's
  // 200ms) has laid anything out.
  useEffect(() => {
    if (!sheetOpen || highlightedIndex == null) return;
    const id = setTimeout(() => {
      sourceRefs.current[highlightedIndex]?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }, 220);
    return () => clearTimeout(id);
  }, [sheetOpen, highlightedIndex]);

  if (message.pending) {
    return (
      <Message from="assistant">
        <MessageContent>
          <ThinkingIndicator advancedMode={advancedMode} />
        </MessageContent>
      </Message>
    );
  }

  return (
    <Message from={message.role}>
      {isUser && message.attachments && message.attachments.length > 0 && (
        <AttachmentChips attachments={message.attachments} statuses={docStatuses} />
      )}

      {gate ? (
        <MessageContent>
          <FaithfulnessCard
            claims={gate.claims}
            onRetry={onRetry}
            onReviewSources={() => openSources(null)}
            hasSources={!!message.sources?.length}
          />
        </MessageContent>
      ) : (
        <MessageContent
          className={cn(
            !isUser && "chat-prose",
            message.error && "bg-destructive/10 text-destructive",
          )}
        >
          <MessageResponse
            components={{
              a: (props) => (
                <CiteLink {...props} sources={message.sources} onSelectSource={openSources} />
              ),
            }}
          >
            {linkifyCitations(message.content, message.sources?.length ?? 0)}
          </MessageResponse>
        </MessageContent>
      )}

      {!isUser && message.sources && message.sources.length > 0 && (
        <button
          type="button"
          onClick={() => openSources(null)}
          className="flex w-fit items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <BookOpenIcon className="size-3.5" />
          Used {message.sources.length} source{message.sources.length === 1 ? "" : "s"}
        </button>
      )}

      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent className="flex flex-col gap-0 p-0 sm:max-w-md">
          <SheetHeader className="border-b border-border">
            <SheetTitle>Sources</SheetTitle>
            <SheetDescription>
              {message.sources?.length ?? 0} passage
              {(message.sources?.length ?? 0) === 1 ? "" : "s"} used for this answer
            </SheetDescription>
          </SheetHeader>
          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
            {message.sources?.map((source) => (
              <div
                key={source.index}
                ref={(el) => {
                  sourceRefs.current[source.index] = el;
                }}
                className={cn(
                  "flex flex-col gap-2 rounded-lg border p-3 transition-colors",
                  highlightedIndex === source.index
                    ? "border-primary/50 bg-accent"
                    : "border-border bg-card/40",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="flex min-w-0 items-center gap-2 text-sm font-medium">
                    <Badge variant="secondary" className="shrink-0 rounded-full">
                      {source.index}
                    </Badge>
                    <span className="truncate">
                      {source.document}
                      {source.page != null ? ` · p.${source.page}` : ""}
                    </span>
                  </span>
                </div>
                {source.section && (
                  <p className="truncate text-xs font-medium text-muted-foreground">
                    {source.section}
                  </p>
                )}
                <blockquote className="border-l-2 border-muted pl-3 text-xs leading-relaxed text-muted-foreground [&_*]:my-0">
                  <MessageResponse>{source.snippet}</MessageResponse>
                </blockquote>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-fit"
                  nativeButton={false}
                  render={
                    <a
                      href={sourceHref(source.document, source.page, source.source_token)}
                      target="_blank"
                      rel="noreferrer"
                    />
                  }
                >
                  Open source document
                </Button>
              </div>
            ))}
          </div>
        </SheetContent>
      </Sheet>
    </Message>
  );
}

export const ChatMessageBubble = memo(ChatMessageBubbleImpl);
