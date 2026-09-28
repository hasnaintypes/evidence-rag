import { create } from "zustand";
import type { Session, User } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";

type AuthState = {
  session: Session | null;
  user: User | null;
  isLoading: boolean;
};

export const useAuthStore = create<AuthState>(() => ({
  session: null,
  user: null,
  isLoading: true,
}));

// Module-level subscription (not inside a component) so the store stays in
// sync everywhere it's read - components just read state, they never need
// to call getSession() themselves.
supabase.auth.getSession().then(({ data }) => {
  useAuthStore.setState({ session: data.session, user: data.session?.user ?? null, isLoading: false });
});

supabase.auth.onAuthStateChange((_event, session) => {
  useAuthStore.setState({ session, user: session?.user ?? null, isLoading: false });
});
