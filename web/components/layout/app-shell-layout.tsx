"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AppSidebar } from "@/components/chat/app-sidebar";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { useAuth } from "@/hooks/use-auth";

// The persistent sidebar shell every signed-in route sits inside - chat,
// Library, and the Entity Graph all share this one layout instead of each
// page rebuilding its own header/back-link navigation.
export function AppShellLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { session, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !session) {
      router.replace("/sign-in");
    }
  }, [isLoading, session, router]);

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>{children}</SidebarInset>
    </SidebarProvider>
  );
}
