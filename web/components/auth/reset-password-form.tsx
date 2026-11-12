"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { toast } from "@/hooks/use-toast";
import { cn } from "cn";

import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { SubmitButton } from "@/components/auth/submit-button";
import { resetPasswordForEmail } from "@/lib/auth";

export function ResetPasswordForm({ className, ...props }: React.ComponentProps<"form">) {
  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await resetPasswordForEmail(email);
      setSent(true);
      toast.success("Check your email for a reset link.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className={cn("flex flex-col gap-5", className)} onSubmit={handleSubmit} {...props}>
      <FieldGroup>
        <div className="flex flex-col items-center gap-1 text-center">
          <h1 className="text-2xl font-bold text-foreground">Reset your password</h1>
          <p className="text-sm text-balance text-muted-foreground">
            Enter your email and we&apos;ll send you a reset link
          </p>
        </div>

        {sent ? (
          <p className="text-center text-sm text-muted-foreground">
            If an account exists for {email}, a reset link is on its way.
          </p>
        ) : (
          <>
            <Field>
              <FieldLabel htmlFor="email">Email</FieldLabel>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                className="h-10"
              />
            </Field>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <Field>
              <SubmitButton pending={isSubmitting}>
                {isSubmitting ? "Sending…" : "Send reset link"}
              </SubmitButton>
            </Field>
          </>
        )}

        <FieldDescription className="text-center">
          Remembered it after all? <Link href="/sign-in">Sign in</Link>
        </FieldDescription>
      </FieldGroup>
    </form>
  );
}
