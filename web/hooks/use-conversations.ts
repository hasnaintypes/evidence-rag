import { useCallback, useEffect, useState } from "react";
import { listConversations } from "@/lib/api";
import type { Conversation } from "@/lib/types";

export function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(() => {
    setIsLoading(true);
    return listConversations()
      .then(setConversations)
      .catch(() => setConversations([]))
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

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
