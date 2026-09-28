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

  return { documents, isLoading, refresh };
}
