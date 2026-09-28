"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { Network, MessagesSquare, Plus, FileText, Settings, HelpCircle, LogOut, ChevronRight } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarFooter,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { signOut } from "@/lib/auth";
import { useAuth } from "@/hooks/use-auth";
import { useConversations } from "@/hooks/use-conversations";

const NAV_LINKS = [
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/graph", label: "Entity graph", icon: Network },
];

function displayName(email: string | undefined, fullName: string | undefined): string {
  if (fullName) return fullName;
  if (!email) return "Account";
  return email.split("@")[0];
}

function avatarUrl(seed: string | undefined): string {
  return `https://api.dicebear.com/9.x/initials/svg?seed=${encodeURIComponent(seed ?? "?")}&backgroundType=gradientLinear`;
}

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const params = useParams<{ conversationId?: string }>();

  const { user } = useAuth();
  const { conversations, isLoading } = useConversations();

  const fullName = (user?.user_metadata as { full_name?: string } | undefined)?.full_name;
  const name = displayName(user?.email, fullName);

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <div className="flex items-center justify-between px-1 py-1">
          <Link
            href="/"
            className="cursor-pointer px-1 text-xl font-bold tracking-tight group-data-[collapsible=icon]:hidden"
          >
            EvidenceRAG
          </Link>
          <SidebarTrigger />
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu className="gap-1.5">
              <SidebarMenuItem>
                <SidebarMenuButton isActive={pathname === "/chat/new"} tooltip="New chat" render={<Link href="/chat/new" />}>
                  <Plus />
                  <span>New chat</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              {NAV_LINKS.map((link) => (
                <SidebarMenuItem key={link.href}>
                  <SidebarMenuButton isActive={pathname === link.href} tooltip={link.label} render={<Link href={link.href} />}>
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
                <p className="px-2 py-1.5 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
                  No conversations yet.
                </p>
              ) : (
                conversations.map((conversation) => (
                  <SidebarMenuItem key={conversation.id}>
                    <SidebarMenuButton
                      isActive={params.conversationId === conversation.id}
                      tooltip={conversation.title ?? conversation.filename ?? undefined}
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

      <SidebarFooter>
        <Popover>
          <PopoverTrigger className="flex w-full cursor-pointer items-center gap-2 rounded-md p-2 text-left hover:bg-sidebar-accent">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={avatarUrl(fullName ?? user?.email)} alt="" className="size-7 shrink-0 rounded-full" />
            <div className="min-w-0 flex-1 group-data-[collapsible=icon]:hidden">
              <p className="truncate text-xs font-medium text-sidebar-foreground">{name}</p>
              <p className="truncate text-[0.65rem] text-muted-foreground">Free plan</p>
            </div>
            <ChevronRight className="size-3.5 shrink-0 text-muted-foreground group-data-[collapsible=icon]:hidden" />
          </PopoverTrigger>
          <PopoverContent side="right" align="end" className="w-64 p-1.5">
            <div className="flex items-center gap-2.5 px-2 py-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={avatarUrl(fullName ?? user?.email)} alt="" className="size-9 shrink-0 rounded-full" />
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-foreground">{name}</p>
                <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
              </div>
            </div>
            <div className="my-1 h-px bg-border" />
            <button
              className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:cursor-not-allowed"
              disabled
            >
              <Settings className="size-3.5" />
              Settings
            </button>
            <a
              href="https://github.com/hasnaintypes/evidence-rag#readme"
              target="_blank"
              rel="noreferrer"
              className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <HelpCircle className="size-3.5" />
              Help
            </a>
            <div className="my-1 h-px bg-border" />
            <button
              onClick={() => signOut().then(() => router.push("/sign-in"))}
              className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-destructive hover:bg-destructive/10"
            >
              <LogOut className="size-3.5" />
              Log out
            </button>
          </PopoverContent>
        </Popover>
      </SidebarFooter>
    </Sidebar>
  );
}
