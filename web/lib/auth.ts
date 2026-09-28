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

export async function signUp(email: string, password: string, fullName: string) {
  const { error } = await supabase.auth.signUp({
    email,
    password,
    options: { data: { full_name: fullName } },
  });
  if (error) throw error;
}

export async function signOut() {
  const { error } = await supabase.auth.signOut();
  if (error) throw error;
}
