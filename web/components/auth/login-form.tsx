"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { toast } from "@/hooks/use-toast";
import { cn } from "cn";

import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { SubmitButton } from "@/components/auth/submit-button";
import { signInWithPassword } from "@/lib/auth";

export function LoginForm({ className, ...props }: React.ComponentProps<"form">) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await signInWithPassword(email, password);
      toast.success("Signed in.");
      router.push("/chat/new");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className={cn("flex flex-col gap-5", className)} onSubmit={handleSubmit} {...props}>
      <FieldGroup>
        <div className="flex flex-col items-center gap-4 text-center">
          <Link href="/" className="flex flex-col items-center gap-3">
            <Image
              src="/logo.png"
              alt="EvidenceRAG"
              width={48}
              height={48}
              className="size-12 rounded-full border border-border bg-card object-cover p-1.5"
            />
            <span className="font-medium text-foreground">EvidenceRAG</span>
          </Link>
          <h1 className="text-2xl font-bold text-foreground">Login to your account</h1>
          <p className="text-sm text-balance text-muted-foreground">
            Enter your email below to login to your account
          </p>
        </div>

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

        <Field>
          <div className="flex items-center">
            <FieldLabel htmlFor="password">Password</FieldLabel>
            <Link
              href="/reset-password"
              className="ml-auto text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
            >
              Forgot your password?
            </Link>
          </div>
          <Input
            id="password"
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            className="h-10"
          />
        </Field>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Field>
          <SubmitButton pending={isSubmitting}>
            {isSubmitting ? "Signing in…" : "Sign in"}
          </SubmitButton>
          <FieldDescription className="text-center">
            Don&apos;t have an account? <Link href="/sign-up">Sign up</Link>
          </FieldDescription>
        </Field>
      </FieldGroup>
    </form>
  );
}
