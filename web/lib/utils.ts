export { cn } from "cn";

// Deterministic avatar for a given seed (name/email/random shuffle string) -
// no upload/storage needed, matches every other identicon in the app.
export function avatarUrl(seed: string | undefined): string {
  return `https://api.dicebear.com/9.x/initials/svg?seed=${encodeURIComponent(seed ?? "?")}&backgroundType=gradientLinear`;
}

const CONVERSATION_DATE_GROUP_ORDER = [
  "Today",
  "Yesterday",
  "Previous 7 Days",
  "Previous 30 Days",
  "Older",
] as const;

export type ConversationDateGroup = (typeof CONVERSATION_DATE_GROUP_ORDER)[number];

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

export function conversationDateGroup(
  isoTimestamp: string,
  now: Date = new Date(),
): ConversationDateGroup {
  const dayDiff = Math.round(
    (startOfDay(now).getTime() - startOfDay(new Date(isoTimestamp)).getTime()) / 86_400_000,
  );
  if (dayDiff <= 0) return "Today";
  if (dayDiff === 1) return "Yesterday";
  if (dayDiff <= 7) return "Previous 7 Days";
  if (dayDiff <= 30) return "Previous 30 Days";
  return "Older";
}

// Buckets already-sorted-newest-first items by `conversationDateGroup`,
// preserving each bucket's relative order and only returning non-empty
// buckets in CONVERSATION_DATE_GROUP_ORDER.
export function groupConversationsByDate<T extends { updated_at: string }>(
  items: T[],
): { label: ConversationDateGroup; items: T[] }[] {
  const buckets = new Map<ConversationDateGroup, T[]>();
  for (const item of items) {
    const label = conversationDateGroup(item.updated_at);
    const bucket = buckets.get(label);
    if (bucket) bucket.push(item);
    else buckets.set(label, [item]);
  }
  return CONVERSATION_DATE_GROUP_ORDER.filter((label) => buckets.has(label)).map((label) => ({
    label,
    items: buckets.get(label)!,
  }));
}
