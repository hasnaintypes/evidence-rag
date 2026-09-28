"use client";

import { Message, MessageContent, MessageResponse } from "@/components/ai-elements/message";
import { Reasoning, ReasoningTrigger, ReasoningContent } from "@/components/ai-elements/reasoning";
import { Sources, SourcesTrigger, SourcesContent } from "@/components/ai-elements/sources";
import { InlineCitation, InlineCitationCard, InlineCitationCardBody } from "@/components/ai-elements/inline-citation";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Badge } from "@/components/ui/badge";
import { HoverCardTrigger } from "@/components/ui/hover-card";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

function sourceHref(document: string, page: number | null) {
  const url = `${API_BASE_URL}/source/${encodeURIComponent(document)}`;
  return page ? `${url}#page=${page}` : url;
}

export function ChatMessageBubble({ message }: { message: ChatMessage }) {
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
      <MessageContent className={cn(message.error && "bg-destructive/10 text-destructive")}>
        <MessageResponse>{message.content}</MessageResponse>
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
                        href={sourceHref(source.document, source.page)}
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
                    <p className="mb-1 truncate text-sm font-medium leading-tight">{source.section}</p>
                    <p className="line-clamp-4 text-sm leading-relaxed text-muted-foreground">{source.snippet}</p>
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
