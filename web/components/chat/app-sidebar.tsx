"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { Network, MessagesSquare, Plus, Upload } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
} from "@/components/ui/sidebar";
import { createConversation, uploadDocument } from "@/lib/api";
import { signOut } from "@/lib/auth";
import { useConversations } from "@/hooks/use-conversations";
import { useDocuments } from "@/hooks/use-documents";

const NAV_LINKS = [{ href: "/graph", label: "Entity graph", icon: Network }];

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const params = useParams<{ conversationId?: string }>();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { conversations, isLoading, refresh: refreshConversations } = useConversations();
  const { documents, refresh: refreshDocuments } = useDocuments();
  const [isPickingDoc, setIsPickingDoc] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  async function startNewChat() {
    setIsPickingDoc(true);
    await refreshDocuments();
  }

  async function pickDocument(docId: string) {
    const conversation = await createConversation(docId);
    setIsPickingDoc(false);
    refreshConversations();
    router.push(`/chat/${conversation.id}`);
  }

  async function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setIsUploading(true);
    try {
      await uploadDocument(file);
      await refreshDocuments();
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <Sidebar>
      <SidebarHeader>
        <Link href="/" className="px-2 py-1.5 text-sm font-semibold tracking-tight">
          EvidenceRAG
        </Link>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton onClick={startNewChat}>
                  <Plus />
                  <span>New chat</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              {NAV_LINKS.map((link) => (
                <SidebarMenuItem key={link.href}>
                  <SidebarMenuButton isActive={pathname === link.href} render={<Link href={link.href} />}>
                    <link.icon />
                    <span>{link.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {isPickingDoc && (
          <SidebarGroup>
            <SidebarGroupLabel>Pick a document</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton onClick={() => fileInputRef.current?.click()} disabled={isUploading}>
                    <Upload />
                    <span>{isUploading ? "Uploading…" : "Upload new document"}</span>
                  </SidebarMenuButton>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".md,.pdf,.docx,.xlsx,.xls,.csv"
                    className="hidden"
                    onChange={handleFileSelected}
                  />
                </SidebarMenuItem>
                {documents.length === 0 ? (
                  <p className="px-2 py-1.5 text-xs text-muted-foreground">No documents yet - upload one above.</p>
                ) : (
                  documents.map((doc) => (
                    <SidebarMenuItem key={doc.doc_id}>
                      <SidebarMenuButton tooltip={doc.filename} className="text-xs" onClick={() => pickDocument(doc.doc_id)}>
                        <span className="truncate">{doc.filename}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))
                )}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}

        <SidebarGroup>
          <SidebarGroupLabel>Conversations</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <SidebarMenuItem key={i}>
                    <SidebarMenuSkeleton />
                  </SidebarMenuItem>
                ))
              ) : conversations.length === 0 ? (
                <p className="px-2 py-1.5 text-xs text-muted-foreground">No conversations yet.</p>
              ) : (
                conversations.map((conversation) => (
                  <SidebarMenuItem key={conversation.id}>
                    <SidebarMenuButton
                      isActive={params.conversationId === conversation.id}
                      tooltip={conversation.filename ?? undefined}
                      render={<Link href={`/chat/${conversation.id}`} />}
                    >
                      <MessagesSquare />
                      <span className="truncate">{conversation.title ?? conversation.filename ?? "New chat"}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <div className="border-t border-sidebar-border p-2">
        <button
          onClick={() => signOut().then(() => router.push("/sign-in"))}
          className="w-full rounded-md px-2 py-1.5 text-left text-xs text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        >
          Sign out
        </button>
      </div>
    </Sidebar>
  );
}
