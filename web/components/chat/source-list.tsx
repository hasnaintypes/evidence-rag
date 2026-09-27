"use client";

import { useState } from "react";
import type { Source } from "@/lib/types";

// "at least a basic citation list" per the citations feature: each answer
// gets a numbered list of the chunks it was actually generated from (doc
// name, page/section, snippet) so a user can verify a claim against its
// source instead of trusting the model blindly.
export function SourceList({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null;

  return (
    <div className="mt-3 flex flex-col gap-1.5">
      <p className="text-xs font-medium text-muted-foreground">Sources</p>
      <ol className="flex flex-col gap-1.5">
        {sources.map((source) => (
          <SourceItem key={source.index} source={source} />
        ))}
      </ol>
    </div>
  );
}

function SourceItem({ source }: { source: Source }) {
  const [open, setOpen] = useState(false);

  return (
    <li className="overflow-hidden rounded-lg border border-border bg-card text-card-foreground">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs"
      >
        <span className="flex min-w-0 items-center gap-2">
          <span className="inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-[0.7rem] font-medium text-muted-foreground">
            {source.index}
          </span>
          <span className="truncate font-medium">
            {source.document}
            {source.page != null ? ` · p.${source.page}` : ""}
          </span>
        </span>
        <span className="shrink-0 text-muted-foreground">
          {open ? "Hide" : "Show"}
        </span>
      </button>
      {open && (
        <div className="border-t border-border px-3 py-2 text-xs text-muted-foreground">
          <p className="mb-1 font-medium text-foreground">{source.section}</p>
          <p className="leading-relaxed">{source.snippet}</p>
        </div>
      )}
    </li>
  );
}
