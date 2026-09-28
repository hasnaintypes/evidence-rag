"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { Network, MessagesSquare, Plus, FileText } from "lucide-react";
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
import { signOut } from "@/lib/auth";
import { useConversations } from "@/hooks/use-conversations";

const NAV_LINKS = [
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/graph", label: "Entity graph", icon: Network },
];

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const params = useParams<{ conversationId?: string }>();

  const { conversations, isLoading } = useConversations();

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
                <SidebarMenuButton isActive={pathname === "/chat/new"} render={<Link href="/chat/new" />}>
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
