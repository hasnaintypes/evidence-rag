import { create } from "zustand";
import { getDocuments } from "@/lib/api";
import type { DocumentRecord } from "@/lib/types";

type DocumentsState = {
  documents: DocumentRecord[];
  isLoading: boolean;
  hasMore: boolean;
  nextCursor: string | null;
  // Same cache-hit reasoning as stores/conversations-store.ts's `loaded`:
  // every page that lists documents (Library, the Graph doc filter, the
  // "attach existing document" picker) shares this one module-level store
  // instead of each paying its own GET /documents round trip, and
  // fetchInitial() becomes a no-op once a page has already been loaded -
  // add()/update()/remove() below keep it in sync locally instead.
  loaded: boolean;
  fetchInitial: (opts?: { force?: boolean }) => Promise<void>;
  loadMore: () => Promise<void>;
  add: (document: DocumentRecord) => void;
  update: (docId: string, patch: Partial<DocumentRecord>) => void;
  remove: (docId: string) => void;
  // Called on sign-out/sign-in-as-a-different-user (stores/auth-store.ts)
  // so the next session doesn't render through a previous user's cache.
  reset: () => void;
};

export const useDocumentsStore = create<DocumentsState>((set, get) => ({
  documents: [],
  isLoading: true,
  hasMore: false,
  nextCursor: null,
  loaded: false,

  fetchInitial: async (opts) => {
    if (get().loaded && !opts?.force) return;
    set({ isLoading: true });
    try {
      const page = await getDocuments();
      set({
        documents: Array.isArray(page.documents) ? page.documents : [],
        hasMore: page.has_more,
        nextCursor: page.next_cursor,
        isLoading: false,
        loaded: true,
      });
    } catch {
      set({ documents: [], hasMore: false, nextCursor: null, isLoading: false, loaded: false });
    }
  },

  loadMore: async () => {
    const { hasMore, nextCursor, documents } = get();
    if (!hasMore || !nextCursor) return;
    try {
      const page = await getDocuments(nextCursor);
      set({
        documents: Array.isArray(page.documents) ? [...documents, ...page.documents] : documents,
        hasMore: page.has_more,
        nextCursor: page.next_cursor,
      });
    } catch {
      // leave hasMore/nextCursor as-is - the next "Load more" click retries
    }
  },

  add: (document) => set((s) => ({ documents: [document, ...s.documents] })),

  update: (docId, patch) =>
    set((s) => ({
      documents: s.documents.map((d) => (d.doc_id === docId ? { ...d, ...patch } : d)),
    })),

  remove: (docId) => set((s) => ({ documents: s.documents.filter((d) => d.doc_id !== docId) })),

  reset: () =>
    set({ documents: [], isLoading: true, hasMore: false, nextCursor: null, loaded: false }),
}));
