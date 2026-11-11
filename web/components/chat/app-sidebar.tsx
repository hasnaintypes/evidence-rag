"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { toast } from "@/hooks/use-toast";
import {
  Network,
  MessagesSquare,
  Plus,
  FileText,
  Search,
  Settings,
  LogOut,
  MoreHorizontal,
  Pin,
  PinOff,
  Pencil,
  Trash2,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarFooter,
  SidebarSeparator,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { SettingsDialog } from "@/components/settings/settings-dialog";
import { signOut } from "@/lib/auth";
import { deleteConversation, updateConversation } from "@/lib/api";
import { avatarUrl, cn, groupConversationsByDate } from "@/lib/utils";
import { useAuth } from "@/hooks/use-auth";
import { useFadeText } from "@/hooks/use-fade-text";
import { useConversationsStore } from "@/stores/conversations-store";
import type { ConversationListItem } from "@/lib/types";

const NAV_LINKS = [
  { href: "/documents", label: "Library", icon: FileText },
  { href: "/graph", label: "Knowledge Graph", icon: Network },
];

function displayName(email: string | undefined, fullName: string | undefined): string {
  if (fullName) return fullName;
  if (!email) return "Account";
  return email.split("@")[0];
}

// A conversation's title can change under an already-rendered row (e.g.
// the LLM-generated title arriving after the first reply, see
// chat-header.tsx's matching fade) - a separate component so each row's
// fade state is its own, rather than hooks called inside a directly-
// invoked renderConversationItem() for every item in a .map().
function ConversationTitle({ title }: { title: string }) {
  const { displayText, fading, fadeMs } = useFadeText(title);
  return (
    <span
      className={cn("truncate transition-opacity", fading ? "opacity-0" : "opacity-100")}
      style={{ transitionDuration: `${fadeMs}ms` }}
    >
      {displayText}
    </span>
  );
}

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const params = useParams<{ conversationId?: string }>();

  const { user, session } = useAuth();
  const { conversations, isLoading, hasMore, fetchInitial, loadMore, patch, remove } =
    useConversationsStore();
  const sentinelRef = useRef<HTMLDivElement>(null);

  // ChatLayout no longer gates its render on auth resolving (see the
  // removed skeleton-flash gate), so AppSidebar can mount before `session`
  // is populated - the conversations fetch would otherwise run once with
  // no bearer token and nothing would ever retry it.
  useEffect(() => {
    if (session) fetchInitial();
  }, [session, fetchInitial]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) loadMore();
      },
      { root: sentinel.closest("[data-sidebar=content]") },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadMore]);

  const [renameTarget, setRenameTarget] = useState<ConversationListItem | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<ConversationListItem | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [search, setSearch] = useState("");

  const metadata = user?.user_metadata as { full_name?: string; avatar_seed?: string } | undefined;
  const fullName = metadata?.full_name;
  const name = displayName(user?.email, fullName);
  const avatarSeed = metadata?.avatar_seed ?? fullName ?? user?.email;

  async function handleTogglePin(conversation: ConversationListItem) {
    const wasPinned = conversation.pinned;
    patch(conversation.id, { pinned: !wasPinned });
    try {
      await updateConversation(conversation.id, { pinned: !wasPinned });
    } catch {
      patch(conversation.id, { pinned: wasPinned });
      toast.error("Couldn't update this chat.");
    }
  }

  function openRename(conversation: ConversationListItem) {
    setRenameTarget(conversation);
    setRenameValue(conversation.title ?? "");
  }

  async function submitRename() {
    if (!renameTarget) return;
    const title = renameValue.trim();
    if (!title) return;
    const previousTitle = renameTarget.title;
    patch(renameTarget.id, { title });
    setRenameTarget(null);
    try {
      await updateConversation(renameTarget.id, { title });
    } catch {
      patch(renameTarget.id, { title: previousTitle });
      toast.error("Couldn't rename this chat.");
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    const target = deleteTarget;
    const wasActive = params.conversationId === target.id;
    remove(target.id);
    setDeleteTarget(null);
    if (wasActive) router.push("/chat/new");
    try {
      await deleteConversation(target.id);
    } catch {
      toast.error("Couldn't delete this chat.");
      useConversationsStore.getState().fetchInitial(); // simplest correct rollback - resync from the server
    }
  }

  const filteredConversations = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return conversations;
    return conversations.filter((c) => (c.title ?? "New chat").toLowerCase().includes(query));
  }, [conversations, search]);

  const sortedConversations = useMemo(
    () =>
      [...filteredConversations].sort(
        (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
      ),
    [filteredConversations],
  );

  const pinnedConversations = sortedConversations.filter((c) => c.pinned);
  const unpinnedGroups = useMemo(
    () => groupConversationsByDate(sortedConversations.filter((c) => !c.pinned)),
    [sortedConversations],
  );

  function renderConversationItem(conversation: ConversationListItem) {
    return (
      <SidebarMenuItem key={conversation.id}>
        <SidebarMenuButton
          isActive={params.conversationId === conversation.id}
          tooltip={conversation.title ?? "New chat"}
          render={<Link href={`/chat/${conversation.id}`} />}
        >
          <MessagesSquare />
          <ConversationTitle title={conversation.title ?? "New chat"} />
        </SidebarMenuButton>
        <DropdownMenu>
          <DropdownMenuTrigger render={<SidebarMenuAction showOnHover />}>
            <MoreHorizontal />
            <span className="sr-only">Chat options</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="right" sideOffset={8}>
            <DropdownMenuItem onClick={() => handleTogglePin(conversation)}>
              {conversation.pinned ? <PinOff /> : <Pin />}
              {conversation.pinned ? "Unpin" : "Pin"}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => openRename(conversation)}>
              <Pencil />
              Rename
            </DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onClick={() => setDeleteTarget(conversation)}>
              <Trash2 />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    );
  }

  return (
    <Sidebar collapsible="icon" variant="inset">
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
        <SidebarGroup className="gap-2">
          <SidebarGroupContent className="flex flex-col gap-2">
            <Button
              render={<Link href="/chat/new" />}
              nativeButton={false}
              className="w-full justify-start group-data-[collapsible=icon]:w-8 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
            >
              <Plus />
              <span className="group-data-[collapsible=icon]:hidden">New chat</span>
            </Button>
            <div className="relative group-data-[collapsible=icon]:hidden">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search conversations"
                aria-label="Search conversations"
                className="h-8 pl-8"
              />
            </div>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu className="gap-1.5">
              {NAV_LINKS.map((link) => (
                <SidebarMenuItem key={link.href}>
                  <SidebarMenuButton
                    isActive={pathname === link.href}
                    tooltip={link.label}
                    render={<Link href={link.href} />}
                  >
                    <link.icon />
                    <span>{link.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {isLoading ? (
          <SidebarGroup>
            <SidebarGroupLabel>Conversations</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {Array.from({ length: 6 }).map((_, i) => (
                  <SidebarMenuItem key={i}>
                    <SidebarMenuSkeleton showIcon />
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ) : sortedConversations.length === 0 ? (
          <SidebarGroup>
            <SidebarGroupLabel>Conversations</SidebarGroupLabel>
            <SidebarGroupContent>
              <p className="px-2 py-1.5 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
                {search.trim() ? "No conversations match." : "No conversations yet."}
              </p>
            </SidebarGroupContent>
          </SidebarGroup>
        ) : (
          <>
            {pinnedConversations.length > 0 && (
              <SidebarGroup>
                <SidebarGroupLabel>Pinned</SidebarGroupLabel>
                <SidebarGroupContent>
                  <SidebarMenu>{pinnedConversations.map(renderConversationItem)}</SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            )}
            {unpinnedGroups.map((group) => (
              <SidebarGroup key={group.label}>
                <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
                <SidebarGroupContent>
                  <SidebarMenu>{group.items.map(renderConversationItem)}</SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            ))}
          </>
        )}
        {hasMore && <div ref={sentinelRef} className="h-px shrink-0" aria-hidden="true" />}
      </SidebarContent>

      <SidebarSeparator className="mx-0" />
      <SidebarFooter>
        <div className="flex items-center gap-2 px-1 py-1">
          <Avatar>
            <AvatarImage src={avatarUrl(avatarSeed)} alt={name} />
            <AvatarFallback>{name.charAt(0).toUpperCase()}</AvatarFallback>
          </Avatar>
          <div className="grid flex-1 text-left text-sm leading-tight group-data-[collapsible=icon]:hidden">
            <span className="truncate font-medium">{name}</span>
            <span className="truncate text-xs text-muted-foreground">{user?.email}</span>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="shrink-0 text-muted-foreground group-data-[collapsible=icon]:hidden"
                />
              }
            >
              <Settings className="size-4" />
              <span className="sr-only">Account menu</span>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" side="top" sideOffset={8} className="w-48">
              <DropdownMenuItem onClick={() => setSettingsOpen(true)}>
                <Settings />
                Settings
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" onClick={() => signOut()}>
                <LogOut />
                Log out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </SidebarFooter>

      <Dialog open={!!renameTarget} onOpenChange={(open) => !open && setRenameTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename this chat</DialogTitle>
          </DialogHeader>
          <Input
            value={renameValue}
            onChange={(event) => setRenameValue(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && submitRename()}
            autoFocus
          />
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
            <Button onClick={submitRename} disabled={!renameValue.trim()}>
              Rename
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this chat?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {`"${deleteTarget?.title ?? "This chat"}" and all its messages will be permanently deleted.`}
          </p>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
            <Button variant="destructive" onClick={confirmDelete}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} user={user} />
    </Sidebar>
  );
}
