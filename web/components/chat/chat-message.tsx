import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/types";
import { SourceList } from "@/components/chat/source-list";

export function ChatMessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground",
          message.error && "bg-destructive/10 text-destructive"
        )}
      >
        {message.pending ? (
          <span className="text-muted-foreground">Thinking…</span>
        ) : (
          <>
            {message.content}
            {!isUser && message.sources && message.sources.length > 0 && (
              <SourceList sources={message.sources} />
            )}
          </>
        )}
      </div>
    </div>
  );
}
