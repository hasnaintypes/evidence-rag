"use client";

import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { useFadeText } from "@/hooks/use-fade-text";
import { cn } from "@/lib/utils";

// Shared by the empty new-chat screen and an active conversation - matches
// the Documents/Entity Graph pages' header convention
// (border-b border-border px-4 py-3) so the chat body reads consistently
// with the rest of the app.
export function ChatHeader({
  title,
  subtitle,
  advancedMode,
  onAdvancedModeChange,
}: {
  title: string;
  subtitle?: string;
  advancedMode: boolean;
  onAdvancedModeChange: (value: boolean) => void;
}) {
  // A conversation's title can change under this component (e.g. the
  // LLM-generated title arriving after the first reply) - fade it instead
  // of an instant/jarring text snap.
  const { displayText, fading, fadeMs } = useFadeText(title);

  return (
    <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
      <div className="min-w-0">
        <h1
          className={cn(
            "truncate text-sm font-semibold transition-opacity",
            fading ? "opacity-0" : "opacity-100",
          )}
          style={{ transitionDuration: `${fadeMs}ms` }}
        >
          {displayText}
        </h1>
        {subtitle && <p className="truncate text-xs text-muted-foreground">{subtitle}</p>}
      </div>
      <Label htmlFor="advanced-mode" className="shrink-0 text-xs text-muted-foreground">
        Advanced mode
        <Switch
          id="advanced-mode"
          checked={advancedMode}
          onCheckedChange={onAdvancedModeChange}
          title="Reranking + the retrieval-confidence gate run only in advanced mode."
        />
      </Label>
    </header>
  );
}
