"use client";

import { useState } from "react";
import { ChevronDownIcon, TriangleAlertIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// The faithfulness hard gate's withheld-answer message is a single plain
// template string built server-side (see query_pipeline.py's
// faithfulness_gated branch) - the backend doesn't expose unsupported_claims
// as structured data on this endpoint (ConversationMessage only carries
// faithfulness_score, see lib/types.ts), so the claims list is parsed back
// out of that known template rather than rendered as dense prose. If the
// template text changes server-side, this falls back to returning null and
// the message renders as plain prose instead of breaking.
const GATE_RE =
  /did not pass the faithfulness check[\s\S]*?Unsupported claims flagged by the judge:\n([\s\S]*?)\n\nThe sources below/;

export function parseFaithfulnessGate(content: string): { claims: string[] } | null {
  const match = GATE_RE.exec(content);
  if (!match) return null;
  const body = match[1].trim();
  if (body === "(none listed)") return { claims: [] };
  const claims = body
    .split("\n")
    .map((line) => line.replace(/^-\s*/, "").trim())
    .filter(Boolean);
  return { claims };
}

export function FaithfulnessCard({
  claims,
  onRetry,
  onReviewSources,
  hasSources,
}: {
  claims: string[];
  onRetry?: () => void;
  onReviewSources?: () => void;
  hasSources?: boolean;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
      <div className="flex items-start gap-2.5">
        <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <div className="flex flex-col gap-1">
          <p className="font-sans text-sm font-semibold text-foreground">
            Answer could not be verified
          </p>
          <p className="text-xs leading-relaxed text-muted-foreground">
            The generated response made claims the retrieved sources don&apos;t fully support, so
            it&apos;s being withheld rather than shown as if it were reliable.
          </p>
        </div>
      </div>

      {claims.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="flex items-center gap-1.5 font-sans text-xs font-semibold text-foreground"
          >
            <ChevronDownIcon
              className={cn("size-3.5 transition-transform", open && "rotate-180")}
            />
            {open ? "Hide" : "Show"} unsupported claims ({claims.length})
          </button>
          {open && (
            <ul className="mt-2 flex flex-col gap-1.5">
              {claims.map((claim, i) => (
                <li
                  key={i}
                  className="relative pl-3.5 text-xs leading-relaxed text-muted-foreground before:absolute before:top-[0.45em] before:left-0 before:size-1 before:rounded-full before:bg-amber-500"
                >
                  {claim}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="flex gap-2">
        {onRetry && (
          <Button type="button" size="sm" variant="secondary" onClick={onRetry}>
            Retry this question
          </Button>
        )}
        {hasSources && onReviewSources && (
          <Button type="button" size="sm" variant="outline" onClick={onReviewSources}>
            Review sources
          </Button>
        )}
      </div>
    </div>
  );
}
