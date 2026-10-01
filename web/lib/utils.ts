export { cn } from "cn"

// Deterministic avatar for a given seed (name/email/random shuffle string) -
// no upload/storage needed, matches every other identicon in the app.
export function avatarUrl(seed: string | undefined): string {
  return `https://api.dicebear.com/9.x/initials/svg?seed=${encodeURIComponent(seed ?? "?")}&backgroundType=gradientLinear`
}
