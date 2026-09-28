"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useConversations } from "@/hooks/use-conversations";
import { Skeleton } from "@/components/ui/skeleton";

export default function ChatIndexPage() {
  const router = useRouter();
  const { conversations, isLoading } = useConversations();

  useEffect(() => {
    if (!isLoading && conversations.length > 0) {
      router.replace(`/chat/${conversations[0].id}`);
    }
  }, [isLoading, conversations, router]);

  if (isLoading || conversations.length > 0) {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 p-4">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-24 w-2/3" />
        <Skeleton className="ml-auto h-16 w-1/2" />
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center">
      <p className="text-sm font-medium">No conversations yet</p>
      <p className="text-xs text-muted-foreground">Click &ldquo;New chat&rdquo; in the sidebar to pick or upload a document.</p>
    </div>
  );
}
