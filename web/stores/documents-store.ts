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
  // Bumped by reset() - fetchAll()'s loop checks this to detect a
  // concurrent reset (e.g. sign-out mid-fetch) instead of trusting
  // get().hasMore alone, which reset() also sets to false and would
  // otherwise read as "pagination finished" rather than "abandoned".
  generation: number;
  fetchInitial: (opts?: { force?: boolean }) => Promise<void>;
  loadMore: () => Promise<void>;
  // Pages in loadMore() a page at a time until hasMore is false - for a
  // consumer that genuinely needs every document (the Graph page's doc
  // filter/filename lookups, which must resolve any document the user
  // owns, not just the first page) rather than one paginated page at a
  // time like the Library page's own "Load more" button.
  fetchAll: (opts?: { force?: boolean }) => Promise<void>;
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
  generation: 0,

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
    const { hasMore, nextCursor } = get();
    if (!hasMore || !nextCursor) return;
    try {
      const page = await getDocuments(nextCursor);
      // Reads `documents` fresh here, not from the closure captured
      // before the await - add()/update()/remove()/reset() can all run
      // on this store while this request is in flight, and a stale
      // pre-await snapshot would silently discard whatever one of those
      // did in the meantime.
      set((s) => ({
        documents: Array.isArray(page.documents)
          ? [...s.documents, ...page.documents]
          : s.documents,
        hasMore: page.has_more,
        nextCursor: page.next_cursor,
      }));
    } catch {
      // leave hasMore/nextCursor as-is - the next "Load more" click retries
    }
  },

  fetchAll: async (opts) => {
    // Captured before any await - if reset() fires while this is in
    // flight (e.g. a concurrent sign-out or a document upload's own
    // reset() call), get().generation will have moved on and every check
    // below bails out instead of continuing to paginate into a store a
    // different "session" now owns, or exiting the loop early believing
    // pagination finished just because reset() also set hasMore: false.
    const generation = get().generation;
    await get().fetchInitial(opts);
    if (get().generation !== generation) return;
    // loadMore() swallows a failed request and leaves hasMore/nextCursor
    // unchanged for a manual retry - detect that here (no cursor
    // progress) and stop, rather than spinning forever retrying the
    // same failing request.
    let previousCursor: string | null = null;
    while (get().hasMore && get().nextCursor !== previousCursor) {
      previousCursor = get().nextCursor;
      await get().loadMore();
      if (get().generation !== generation) return;
    }
  },

  add: (document) => set((s) => ({ documents: [document, ...s.documents] })),

  update: (docId, patch) =>
    set((s) => ({
      documents: s.documents.map((d) => (d.doc_id === docId ? { ...d, ...patch } : d)),
    })),

  remove: (docId) => set((s) => ({ documents: s.documents.filter((d) => d.doc_id !== docId) })),

  reset: () =>
    set((s) => ({
      documents: [],
      isLoading: true,
      hasMore: false,
      nextCursor: null,
      loaded: false,
      generation: s.generation + 1,
    })),
}));
