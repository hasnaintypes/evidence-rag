"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Network, MessagesSquare } from "lucide-react";
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
import { getDocuments } from "@/lib/api";
import type { DocumentRecord } from "@/lib/types";

const NAV_LINKS = [
  { href: "/chat", label: "Chat", icon: MessagesSquare },
  { href: "/graph", label: "Entity graph", icon: Network },
];

export function AppSidebar() {
  const pathname = usePathname();
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    getDocuments()
      .then(setDocuments)
      .catch(() => setDocuments([]))
      .finally(() => setIsLoading(false));
  }, []);

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
          <SidebarGroupLabel>Indexed documents</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <SidebarMenuItem key={i}>
                    <SidebarMenuSkeleton />
                  </SidebarMenuItem>
                ))
              ) : documents.length === 0 ? (
                <p className="px-2 py-1.5 text-xs text-muted-foreground">
                  Nothing indexed yet - run the ingestion script.
                </p>
              ) : (
                documents.map((doc) => (
                  <SidebarMenuItem key={doc.doc_id}>
                    <SidebarMenuButton tooltip={doc.filename} className="text-xs">
                      <span className="truncate">{doc.filename}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
