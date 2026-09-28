"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useConversations } from "@/hooks/use-conversations";
import { Skeleton } from "@/components/ui/skeleton";

export default function ChatIndexPage() {
  const router = useRouter();
  const { conversations, isLoading } = useConversations();

  useEffect(() => {
    if (isLoading) return;
    router.replace(conversations.length > 0 ? `/chat/${conversations[0].id}` : "/chat/new");
  }, [isLoading, conversations, router]);

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 p-4">
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-24 w-2/3" />
      <Skeleton className="ml-auto h-16 w-1/2" />
    </div>
  );
}
