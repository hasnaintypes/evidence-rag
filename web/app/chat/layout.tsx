"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AppSidebar } from "@/components/chat/app-sidebar";
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/hooks/use-auth";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { session, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !session) {
      router.replace("/sign-in");
    }
  }, [isLoading, session, router]);

  if (isLoading || !session) {
    return (
      <div className="flex flex-1">
        <div className="hidden w-64 shrink-0 flex-col gap-4 border-r border-border p-3 sm:flex">
          <Skeleton className="h-6 w-28" />
          <div className="flex flex-col gap-2">
            <Skeleton className="h-7 w-full" />
            <Skeleton className="h-7 w-full" />
          </div>
          <div className="flex flex-col gap-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-7 w-full" />
            <Skeleton className="h-7 w-full" />
            <Skeleton className="h-7 w-full" />
          </div>
        </div>
        <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 p-4">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-24 w-2/3" />
          <Skeleton className="ml-auto h-16 w-1/2" />
        </div>
      </div>
    );
  }

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <SidebarTrigger className="m-2" />
        {children}
      </SidebarInset>
    </SidebarProvider>
  );
}
