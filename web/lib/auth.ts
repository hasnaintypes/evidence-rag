import { supabase } from "@/lib/supabase";

// Sign-in/sign-up/sign-out talk directly to Supabase Auth from the
// browser - not proxied through our FastAPI backend. That's the standard
// pattern for this architecture (SPA frontend + separate API backend, no
// server-rendered sessions/cookies): Supabase's SDK already handles token
// issuance, refresh, and storage, and our backend's only job is verifying
// the tokens it's handed (see server/api/deps.py, JWKS-based). Proxying
// auth through our own backend would only be needed for cookie-based SSR
// sessions (@supabase/ssr), which this app doesn't use.

export async function signInWithPassword(email: string, password: string) {
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw error;
}

// emailRedirectTo sends the confirmation link to /auth/confirm (not
// straight to the app) - Supabase's own /verify endpoint establishes a
// session as a side effect of confirming the token, and that page's only
// job is to discard that session and send the user to /sign-in instead, so
// confirming an email doesn't silently log someone in on a shared machine.
export async function signUp(email: string, password: string, fullName: string) {
  const { error } = await supabase.auth.signUp({
    email,
    password,
    options: {
      data: { full_name: fullName },
      emailRedirectTo: `${window.location.origin}/auth/confirm`,
    },
  });
  if (error) throw error;
}

export async function signOut() {
  const { error } = await supabase.auth.signOut();
  if (error) throw error;
}

// Sends a recovery email whose link lands on /update-password with a
// recovery session already established (Supabase appends the token to that
// redirectTo URL and its client picks it up automatically).
export async function resetPasswordForEmail(email: string) {
  const { error } = await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: `${window.location.origin}/update-password`,
  });
  if (error) throw error;
}

// Only valid when called from /update-password's recovery session - there
// is no separate "current password" check here because Supabase's recovery
// link itself is the proof of ownership.
export async function updatePassword(newPassword: string) {
  const { error } = await supabase.auth.updateUser({ password: newPassword });
  if (error) throw error;
}
