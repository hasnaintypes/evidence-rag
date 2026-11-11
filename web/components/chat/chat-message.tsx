"use client";

import { memo } from "react";
import type { ReactNode } from "react";
import { Message, MessageContent, MessageResponse } from "@/components/ai-elements/message";
import { AttachmentChips } from "@/components/chat/attachment-chips";
import { Reasoning, ReasoningTrigger, ReasoningContent } from "@/components/ai-elements/reasoning";
import { Sources, SourcesTrigger, SourcesContent } from "@/components/ai-elements/sources";
import {
  InlineCitation,
  InlineCitationCard,
  InlineCitationCardBody,
} from "@/components/ai-elements/inline-citation";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Badge } from "@/components/ui/badge";
import { HoverCardTrigger } from "@/components/ui/hover-card";
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
}: {
  href?: string;
  children?: ReactNode;
  sources: ChatMessage["sources"];
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
  const source = sources?.find((s) => s.index === index);
  if (!source) return <>{children}</>; // out-of-range already sanitized server-side, but guard anyway

  return (
    <InlineCitation>
      <InlineCitationCard>
        <HoverCardTrigger
          render={
            <a
              href={sourceHref(source.document, source.page, source.source_token)}
              target="_blank"
              rel="noreferrer"
              className="citation-marker"
            />
          }
        >
          <Badge variant="secondary" className="mx-0.5 rounded-full px-1.5 text-[10px]">
            {index}
          </Badge>
        </HoverCardTrigger>
        <InlineCitationCardBody>
          <p className="mb-1 truncate text-sm font-medium leading-tight">{source.section}</p>
          <p className="line-clamp-4 text-sm leading-relaxed text-muted-foreground">
            {source.snippet}
          </p>
        </InlineCitationCardBody>
      </InlineCitationCard>
    </InlineCitation>
  );
}

function ChatMessageBubbleImpl({
  message,
  docStatuses = {},
}: {
  message: ChatMessage;
  docStatuses?: Record<string, DocumentStatus["status"]>;
}) {
  const isUser = message.role === "user";

  if (message.pending) {
    return (
      <Message from="assistant">
        <MessageContent>
          <Shimmer duration={1.2}>Thinking…</Shimmer>
        </MessageContent>
      </Message>
    );
  }

  return (
    <Message from={message.role}>
      {isUser && message.attachments && message.attachments.length > 0 && (
        <AttachmentChips attachments={message.attachments} statuses={docStatuses} />
      )}

      <MessageContent className={cn(message.error && "bg-destructive/10 text-destructive")}>
        <MessageResponse
          components={{ a: (props) => <CiteLink {...props} sources={message.sources} /> }}
        >
          {linkifyCitations(message.content, message.sources?.length ?? 0)}
        </MessageResponse>
      </MessageContent>

      {!isUser && message.thinking && (
        <Reasoning defaultOpen={false}>
          <ReasoningTrigger />
          <ReasoningContent>{message.thinking}</ReasoningContent>
        </Reasoning>
      )}

      {!isUser && message.sources && message.sources.length > 0 && (
        <Sources>
          <SourcesTrigger count={message.sources.length} />
          <SourcesContent>
            {message.sources.map((source) => (
              <InlineCitation key={source.index}>
                <InlineCitationCard>
                  <HoverCardTrigger
                    render={
                      <a
                        href={sourceHref(source.document, source.page, source.source_token)}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-2 text-xs hover:text-foreground"
                      />
                    }
                  >
                    <Badge variant="secondary" className="rounded-full">
                      {source.index}
                    </Badge>
                    <span className="truncate font-medium">
                      {source.document}
                      {source.page != null ? ` · p.${source.page}` : ""}
                    </span>
                  </HoverCardTrigger>
                  <InlineCitationCardBody>
                    <p className="mb-1 truncate text-sm font-medium leading-tight">
                      {source.section}
                    </p>
                    <p className="line-clamp-4 text-sm leading-relaxed text-muted-foreground">
                      {source.snippet}
                    </p>
                  </InlineCitationCardBody>
                </InlineCitationCard>
              </InlineCitation>
            ))}
          </SourcesContent>
        </Sources>
      )}
    </Message>
  );
}

export const ChatMessageBubble = memo(ChatMessageBubbleImpl);
