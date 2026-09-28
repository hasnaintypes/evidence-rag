"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { Network, MessagesSquare, Plus, FileText, Settings, HelpCircle, LogOut, ChevronsUpDown } from "lucide-react";
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
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
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

  const userSummary = (
    <>
      <Avatar>
        <AvatarImage src={avatarUrl(fullName ?? user?.email)} alt={name} />
        <AvatarFallback>{name.charAt(0).toUpperCase()}</AvatarFallback>
      </Avatar>
      <div className="grid flex-1 text-left text-sm leading-tight group-data-[collapsible=icon]:hidden">
        <span className="truncate font-medium">{name}</span>
        <span className="truncate text-xs text-muted-foreground">{user?.email}</span>
      </div>
    </>
  );

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
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <SidebarMenuButton
                    size="lg"
                    className="data-popup-open:bg-sidebar-accent data-popup-open:text-sidebar-accent-foreground"
                  />
                }
              >
                {userSummary}
                <ChevronsUpDown className="ml-auto size-4 shrink-0 text-muted-foreground group-data-[collapsible=icon]:hidden" />
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="min-w-56 rounded-lg"
                side="top"
                align="start"
                sideOffset={8}
              >
                <DropdownMenuGroup>
                  <DropdownMenuLabel className="p-0 font-normal">
                    <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">{userSummary}</div>
                  </DropdownMenuLabel>
                </DropdownMenuGroup>
                <DropdownMenuSeparator />
                <DropdownMenuGroup>
                  <DropdownMenuItem disabled>
                    <Settings />
                    Settings
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    render={
                      <a href="https://github.com/hasnaintypes/evidence-rag#readme" target="_blank" rel="noreferrer" />
                    }
                  >
                    <HelpCircle />
                    Help
                  </DropdownMenuItem>
                </DropdownMenuGroup>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onClick={() => signOut().then(() => router.push("/sign-in"))}>
                  <LogOut />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
