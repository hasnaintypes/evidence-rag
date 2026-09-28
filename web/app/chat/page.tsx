import { ChatPanel } from "@/components/chat/chat-panel";
import { AppSidebar } from "@/components/chat/app-sidebar";
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar";

export default function ChatPage() {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <SidebarTrigger className="m-2" />
        <ChatPanel />
      </SidebarInset>
    </SidebarProvider>
  );
}
