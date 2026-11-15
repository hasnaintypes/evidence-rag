import { create } from "zustand";
import { listConversations } from "@/lib/api";
import type { ConversationListItem } from "@/lib/types";

type ConversationsState = {
  conversations: ConversationListItem[];
  isLoading: boolean;
  hasMore: boolean;
  nextCursor: string | null;
  // True once fetchInitial() has completed at least once - lets
  // fetchInitial() become a cache-hit no-op on every later mount (the
  // sidebar remounts on every /chat <-> /documents <-> /graph navigation,
  // since those are sibling route segments, not nested ones) instead of
  // re-fetching data that insertOptimistic/patch/remove already keep in
  // sync locally. Pass force:true to bypass the cache (the rollback-resync
  // call below after a failed mutation genuinely needs a fresh fetch).
  loaded: boolean;
  fetchInitial: (opts?: { force?: boolean }) => Promise<void>;
  loadMore: () => Promise<void>;
  insertOptimistic: (conversation: ConversationListItem) => void;
  patch: (id: string, patch: Partial<ConversationListItem>) => void;
  remove: (id: string) => void;
  // Called on sign-out/sign-in-as-a-different-user (stores/auth-store.ts)
  // so the next session doesn't render through a previous user's cache.
  reset: () => void;
};

// Module-level store (not a hook-local fetch) so a conversation created in
// one component (ChatComposer) shows up immediately in another
// (AppSidebar) without a page reload - same reasoning as auth-store.ts's
// module-level session, just with explicit fetch/mutate actions instead of
// a background subscription, since conversations don't have a realtime
// source to subscribe to.
export const useConversationsStore = create<ConversationsState>((set, get) => ({
  conversations: [],
  isLoading: true,
  hasMore: false,
  nextCursor: null,
  loaded: false,

  fetchInitial: async (opts) => {
    if (get().loaded && !opts?.force) return;
    set({ isLoading: true });
    try {
      const page = await listConversations();
      set({
        conversations: page.conversations,
        hasMore: page.has_more,
        nextCursor: page.next_cursor,
        isLoading: false,
        loaded: true,
      });
    } catch {
      set({ conversations: [], hasMore: false, nextCursor: null, isLoading: false, loaded: false });
    }
  },

  loadMore: async () => {
    const { hasMore, nextCursor, conversations } = get();
    if (!hasMore || !nextCursor) return;
    try {
      const page = await listConversations(nextCursor);
      set({
        conversations: [...conversations, ...page.conversations],
        hasMore: page.has_more,
        nextCursor: page.next_cursor,
      });
    } catch {
      // leave hasMore/nextCursor as-is - the next scroll-triggered call retries
    }
  },

  insertOptimistic: (conversation) =>
    set((s) => ({ conversations: [conversation, ...s.conversations] })),

  patch: (id, patch) =>
    set((s) => ({
      conversations: s.conversations.map((c) => (c.id === id ? { ...c, ...patch } : c)),
    })),

  remove: (id) => set((s) => ({ conversations: s.conversations.filter((c) => c.id !== id) })),

  reset: () =>
    set({ conversations: [], isLoading: true, hasMore: false, nextCursor: null, loaded: false }),
}));
