import { useCallback, useEffect, useState } from "react";
import { listConversations } from "@/lib/api";
import type { Conversation } from "@/lib/types";

export function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Split from `refresh` below so the mount effect can call this directly:
  // it has no synchronous setState call of its own (isLoading already
  // starts true), only ones inside the .then/.catch/.finally callbacks,
  // which run later as microtasks, not synchronously during the effect.
  const fetchConversations = useCallback(() => {
    return listConversations()
      .then(setConversations)
      .catch(() => setConversations([]))
      .finally(() => setIsLoading(false));
  }, []);

  const refresh = useCallback(() => {
    setIsLoading(true);
    return fetchConversations();
  }, [fetchConversations]);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // Patches the local list in place instead of refetching - pin/rename
  // reflect instantly instead of flashing the whole sidebar back to its
  // loading skeleton for a round trip.
  const update = useCallback((id: string, patch: Partial<Conversation>) => {
    setConversations((prev) => prev.map((c) => (c.id === id ? { ...c, ...patch } : c)));
  }, []);

  const remove = useCallback((id: string) => {
    setConversations((prev) => prev.filter((c) => c.id !== id));
  }, []);

  return { conversations, isLoading, refresh, update, remove };
}
