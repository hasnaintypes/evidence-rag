"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Network,
  MessagesSquare,
  Plus,
  FileText,
  Settings,
  HelpCircle,
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
} from "@/components/ui/dropdown-menu";
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from "@/components/ui/popover";
import { signOut } from "@/lib/auth";
import { deleteConversation, updateConversation } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import { useConversations } from "@/hooks/use-conversations";
import type { Conversation } from "@/lib/types";

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
  const { conversations, isLoading, refresh } = useConversations();
  const [renameTarget, setRenameTarget] = useState<Conversation | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null);

  const fullName = (user?.user_metadata as { full_name?: string } | undefined)?.full_name;
  const name = displayName(user?.email, fullName);

  async function handleTogglePin(conversation: Conversation) {
    try {
      await updateConversation(conversation.id, { pinned: !conversation.pinned });
      refresh();
    } catch {
      toast.error("Couldn't update this chat.");
    }
  }

  function openRename(conversation: Conversation) {
    setRenameTarget(conversation);
    setRenameValue(conversation.title ?? "");
  }

  async function submitRename() {
    if (!renameTarget) return;
    const title = renameValue.trim();
    if (!title) return;
    try {
      await updateConversation(renameTarget.id, { title });
      setRenameTarget(null);
      refresh();
    } catch {
      toast.error("Couldn't rename this chat.");
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    try {
      await deleteConversation(deleteTarget.id);
      const wasActive = params.conversationId === deleteTarget.id;
      setDeleteTarget(null);
      refresh();
      if (wasActive) router.push("/chat/new");
    } catch {
      toast.error("Couldn't delete this chat.");
    }
  }

  const pinnedConversations = conversations.filter((c) => c.pinned);
  const unpinnedConversations = conversations.filter((c) => !c.pinned);

  function renderConversationItem(conversation: Conversation) {
    return (
      <SidebarMenuItem key={conversation.id}>
        <SidebarMenuButton
          isActive={params.conversationId === conversation.id}
          tooltip={conversation.title ?? conversation.filenames[0] ?? undefined}
          render={<Link href={`/chat/${conversation.id}`} />}
        >
          <MessagesSquare />
          <span className="truncate">{conversation.title ?? conversation.filenames[0] ?? "New chat"}</span>
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

        {isLoading ? (
          <SidebarGroup>
            <SidebarGroupLabel>Conversations</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {Array.from({ length: 3 }).map((_, i) => (
                  <SidebarMenuItem key={i}>
                    <SidebarMenuSkeleton />
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ) : conversations.length === 0 ? (
          <SidebarGroup>
            <SidebarGroupLabel>Conversations</SidebarGroupLabel>
            <SidebarGroupContent>
              <p className="px-2 py-1.5 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
                No conversations yet.
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
            <SidebarGroup>
              <SidebarGroupLabel>Conversations</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>{unpinnedConversations.map(renderConversationItem)}</SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          </>
        )}
      </SidebarContent>

      <SidebarFooter>
        <div className="flex items-center gap-2 px-1 py-1">
          {userSummary}
          <Popover>
            <PopoverTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="shrink-0 text-muted-foreground group-data-[collapsible=icon]:hidden"
                />
              }
            >
              <Settings className="size-4" />
              <span className="sr-only">Settings</span>
            </PopoverTrigger>
            <PopoverContent className="w-56 p-1" side="top" align="end" sideOffset={8}>
              <button
                disabled
                className="flex w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-sm text-foreground opacity-50 disabled:pointer-events-none [&_svg]:size-4"
              >
                <Settings />
                Settings
              </button>
              <a
                href="https://github.com/hasnaintypes/evidence-rag#readme"
                target="_blank"
                rel="noreferrer"
                className="flex w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-sm hover:bg-accent hover:text-accent-foreground [&_svg]:size-4"
              >
                <HelpCircle />
                Help
              </a>
              <div className="my-1 h-px bg-border" />
              <button
                onClick={() => signOut().then(() => router.push("/sign-in"))}
                className="flex w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-sm text-destructive hover:bg-destructive/10 [&_svg]:size-4"
              >
                <LogOut />
                Log out
              </button>
            </PopoverContent>
          </Popover>
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
            {`"${deleteTarget?.title ?? deleteTarget?.filenames[0] ?? "This chat"}" and all its messages will be permanently deleted.`}
          </p>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
            <Button variant="destructive" onClick={confirmDelete}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Sidebar>
  );
}
