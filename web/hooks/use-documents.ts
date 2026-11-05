import { useCallback, useState } from "react";
import { getDocuments } from "@/lib/api";
import type { DocumentRecord } from "@/lib/types";

// No auto-fetch on mount - callers (e.g. the "New chat" document picker)
// trigger refresh() only when the list actually needs to be shown, since
// it's not needed on every page that imports this hook.
export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const refresh = useCallback(() => {
    setIsLoading(true);
    return getDocuments()
      .then(setDocuments)
      .catch(() => setDocuments([]))
      .finally(() => setIsLoading(false));
  }, []);

  // Patches the local list in place instead of refetching - same pattern
  // as use-conversations.ts's update()/remove(), so a rename/status change
  // reflects instantly instead of flashing the whole list back to loading.
  const update = useCallback((docId: string, patch: Partial<DocumentRecord>) => {
    setDocuments((prev) => prev.map((d) => (d.doc_id === docId ? { ...d, ...patch } : d)));
  }, []);

  const remove = useCallback((docId: string) => {
    setDocuments((prev) => prev.filter((d) => d.doc_id !== docId));
  }, []);

  const add = useCallback((document: DocumentRecord) => {
    setDocuments((prev) => [document, ...prev]);
  }, []);

  return { documents, isLoading, refresh, update, remove, add };
}
