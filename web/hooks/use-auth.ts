import { useAuthStore } from "@/stores/auth-store";

// Thin hook-shaped alias over the Zustand store, matching the app's other
// hooks/use-*.ts naming so components don't need to know it's Zustand
// underneath.
export function useAuth() {
  return useAuthStore();
}
