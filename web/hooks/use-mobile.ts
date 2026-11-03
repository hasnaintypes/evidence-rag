import * as React from "react"

const MOBILE_BREAKPOINT = 768

// useSyncExternalStore reads the live value during render/commit instead of
// an effect calling setState after the fact - the correct way to subscribe
// to a browser-only API (matchMedia) without the extra render pass an
// effect-based setState would cause.
function subscribe(onChange: () => void) {
  const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
  mql.addEventListener("change", onChange)
  return () => mql.removeEventListener("change", onChange)
}

function getSnapshot() {
  return window.innerWidth < MOBILE_BREAKPOINT
}

function getServerSnapshot() {
  return false
}

export function useIsMobile() {
  return React.useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}
