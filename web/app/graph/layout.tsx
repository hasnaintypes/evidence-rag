import { AppShellLayout } from "@/components/layout/app-shell-layout";

export default function GraphLayout({ children }: { children: React.ReactNode }) {
  return <AppShellLayout>{children}</AppShellLayout>;
}
