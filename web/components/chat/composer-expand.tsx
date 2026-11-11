"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { Maximize2, Minimize2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePromptInputController } from "@/components/ai-elements/prompt-input";

// Grows the SAME composer textarea in place (just a taller max-height on
// the one PromptInputTextarea, nothing new mounted on top of it) rather
// than opening a second box - the toggle only appears once there's enough
// text to actually want more room, or once already expanded (so there's
// still a way back to collapse after trimming the text back down).
const EXPAND_THRESHOLD = 160;

export function ComposerExpand({
  enabled = true,
  children,
}: {
  // False on a screen with no conversation content yet (a new/empty chat) -
  // there's nothing to need more room for yet, so no toggle ever renders
  // there regardless of how much has been typed.
  enabled?: boolean;
  children: (state: { expanded: boolean; shouldShowToggle: boolean }) => ReactNode;
}) {
  const { textInput } = usePromptInputController();
  const [expanded, setExpanded] = useState(false);
  const shouldShowToggle = enabled && (expanded || textInput.value.length > EXPAND_THRESHOLD);

  return (
    <>
      {shouldShowToggle && (
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="absolute top-1.5 right-1.5 z-10 text-muted-foreground hover:text-foreground"
          onClick={() => setExpanded((v) => !v)}
          title={expanded ? "Collapse composer" : "Expand composer"}
        >
          {expanded ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
        </Button>
      )}
      {children({ expanded, shouldShowToggle })}
    </>
  );
}
