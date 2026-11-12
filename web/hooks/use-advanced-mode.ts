import { useSyncExternalStore } from "react";

const STORAGE_KEY = "evidencerag:advancedMode";

// Defaults to true, matching what every sendMessage() call site hardcoded
// before this toggle existed (see CLAUDE.md's query_pipeline.py notes -
// advanced mode runs reranking plus the retrieval-confidence gate; naive
// mode skips both and always attempts an answer).
const DEFAULT_VALUE = true;

// Module-level cache + subscriber list, same useSyncExternalStore pattern
// as use-mobile.ts's useIsMobile() - reads a browser-only API without a
// setState-in-effect, and keeps every mounted instance of this hook (chat
// composer, chat panel, ...) in sync with one shared, localStorage-backed
// value instead of each holding its own copy.
let cachedValue: boolean | null = null;
const listeners = new Set<() => void>();

function readStored(): boolean {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored !== null ? stored === "true" : DEFAULT_VALUE;
  } catch {
    return DEFAULT_VALUE;
  }
}

function getSnapshot(): boolean {
  if (cachedValue === null) cachedValue = readStored();
  return cachedValue;
}

function getServerSnapshot(): boolean {
  return DEFAULT_VALUE;
}

function subscribe(onStoreChange: () => void) {
  listeners.add(onStoreChange);
  return () => listeners.delete(onStoreChange);
}

function setAdvancedMode(value: boolean) {
  cachedValue = value;
  try {
    window.localStorage.setItem(STORAGE_KEY, String(value));
  } catch {
    // best-effort persistence only
  }
  listeners.forEach((listener) => listener());
}

export function useAdvancedMode() {
  const advancedMode = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return [advancedMode, setAdvancedMode] as const;
}
