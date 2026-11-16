"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "@/hooks/use-toast";
import { cn } from "cn";

import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { SubmitButton } from "@/components/auth/submit-button";
import { useAuth } from "@/hooks/use-auth";
import { updatePassword } from "@/lib/auth";

export function UpdatePasswordForm({ className, ...props }: React.ComponentProps<"form">) {
  const router = useRouter();
  const { session, isLoading } = useAuth();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }
    setIsSubmitting(true);
    try {
      await updatePassword(password);
      toast.success("Password updated.");
      router.push("/chat");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setIsSubmitting(false);
    }
  }

  // The recovery link establishes a session via Supabase's client-side
  // listener (stores/auth-store.ts's onAuthStateChange) before this renders
  // - no session at this point means the link was missing, expired, or
  // already used, not just a slow network.
  if (!isLoading && !session) {
    return (
      <div className={cn("flex flex-col items-center gap-3 text-center", className)}>
        <h1 className="text-2xl font-bold text-foreground">Link expired</h1>
        <p className="text-sm text-balance text-muted-foreground">
          This reset link is invalid or has expired. Request a new one to continue.
        </p>
        <Link href="/reset-password" className="text-sm underline underline-offset-4">
          Request a new link
        </Link>
      </div>
    );
  }

  return (
    <form className={cn("flex flex-col gap-5", className)} onSubmit={handleSubmit} {...props}>
      <FieldGroup>
        <div className="flex flex-col items-center gap-1 text-center">
          <h1 className="text-2xl font-bold text-foreground">Set a new password</h1>
          <p className="text-sm text-balance text-muted-foreground">
            Choose a new password for your account
          </p>
        </div>

        <Field>
          <FieldLabel htmlFor="password">New password</FieldLabel>
          <Input
            id="password"
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            className="h-10"
          />
        </Field>

        <Field>
          <FieldLabel htmlFor="confirm-password">Confirm password</FieldLabel>
          <Input
            id="confirm-password"
            type="password"
            required
            minLength={6}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            autoComplete="new-password"
            className="h-10"
          />
        </Field>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Field>
          <SubmitButton pending={isSubmitting}>
            {isSubmitting ? "Updating…" : "Update password"}
          </SubmitButton>
          <FieldDescription className="text-center">
            <Link href="/sign-in">Back to sign in</Link>
          </FieldDescription>
        </Field>
      </FieldGroup>
    </form>
  );
}
