import { useEffect, useState } from "react";

const DEFAULT_FADE_MS = 150;

// Fades text out, swaps it, then fades it in, instead of an instant/jarring
// snap - for a short-lived value (a chat/conversation title) that can
// change under an already-mounted component. Apply the returned `fading`
// flag as an opacity toggle with a matching transition-duration.
export function useFadeText(text: string, ms: number = DEFAULT_FADE_MS) {
  const [displayText, setDisplayText] = useState(text);
  // Starting the fade is a render-time state adjustment from a changed
  // prop (react.dev's "Adjusting state when a prop changes" pattern), not
  // an effect - an effect calling setState synchronously in its body
  // would cascade an extra render for no reason. The effect below only
  // owns the *deferred* swap (inside the setTimeout callback), which is
  // the "calling setState in a callback once an external timer fires"
  // shape effects are actually for.
  const [fading, setFading] = useState(false);
  if (text !== displayText && !fading) {
    setFading(true);
  }

  useEffect(() => {
    if (!fading) return;
    const timeout = setTimeout(() => {
      setDisplayText(text);
      setFading(false);
    }, ms);
    return () => clearTimeout(timeout);
  }, [fading, text, ms]);

  return { displayText, fading, fadeMs: ms };
}
