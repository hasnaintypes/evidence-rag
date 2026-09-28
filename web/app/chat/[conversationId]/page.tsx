"use client";

import { use } from "react";
import { ChatPanel } from "@/components/chat/chat-panel";

export default function ConversationPage({
  params,
}: {
  params: Promise<{ conversationId: string }>;
}) {
  const { conversationId } = use(params);
  return <ChatPanel key={conversationId} conversationId={conversationId} />;
}
