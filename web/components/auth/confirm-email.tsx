"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "@/hooks/use-toast";
import { supabase } from "@/lib/supabase";

// Supabase's /auth/v1/verify link both confirms the signup token AND
// establishes a session (appended to this page's URL as a fragment, which
// the Supabase client auto-detects on load - see stores/auth-store.ts). A
// confirmation click isn't a sign-in, so this page's only job is to throw
// that session away and send the person to /sign-in instead.
export function ConfirmEmail() {
  const router = useRouter();
  const [status, setStatus] = useState<"checking" | "invalid">("checking");
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    (async () => {
      const { data } = await supabase.auth.getSession();
      if (!data.session) {
        setStatus("invalid");
        return;
      }
      await supabase.auth.signOut();
      toast.success("Email confirmed - sign in to continue.");
      router.replace("/sign-in");
    })();
  }, [router]);

  if (status === "invalid") {
    return (
      <div className="flex flex-col items-center gap-3 text-center">
        <h1 className="text-2xl font-bold text-foreground">Link expired</h1>
        <p className="text-sm text-balance text-muted-foreground">
          This confirmation link is invalid or has already been used.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-3 text-center">
      <p className="text-sm text-muted-foreground">Confirming your email…</p>
    </div>
  );
}
