import { create } from "zustand";
import type { Session, User } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";
import { useConversationsStore } from "@/stores/conversations-store";
import { useDocumentsStore } from "@/stores/documents-store";

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
  useAuthStore.setState({
    session: data.session,
    user: data.session?.user ?? null,
    isLoading: false,
  });
});

supabase.auth.onAuthStateChange((_event, session) => {
  const previousUserId = useAuthStore.getState().user?.id ?? null;
  const nextUserId = session?.user?.id ?? null;
  useAuthStore.setState({ session, user: session?.user ?? null, isLoading: false });
  // A sign-out or a sign-in as a different account means the conversations/
  // documents caches below belong to someone else now - reset them so the
  // next session starts from a real fetch instead of rendering through a
  // previous user's cached data.
  if (previousUserId !== nextUserId) {
    useConversationsStore.getState().reset();
    useDocumentsStore.getState().reset();
  }
});
