"use client";

// A thin circular progress ring overlaid on a square file-preview tile
// while a document is being embedded - chunks_indexed/chunks_total are
// already streamed live over SSE (see lib/api.ts's subscribeToDocumentStatus),
// this just finally renders them instead of showing a plain static icon
// for the whole indexing window.
export function AttachmentProgressRing({ indexed, total }: { indexed: number; total: number }) {
  const ratio = total > 0 ? Math.min(1, indexed / total) : 0;
  const radius = 15;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - ratio);

  return (
    <svg
      viewBox="0 0 36 36"
      className="absolute inset-0 size-full -rotate-90 text-foreground"
      aria-hidden="true"
    >
      <circle
        cx="18"
        cy="18"
        r={radius}
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.15"
        strokeWidth="3"
      />
      <circle
        cx="18"
        cy="18"
        r={radius}
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        className="transition-[stroke-dashoffset] duration-300 ease-out"
      />
    </svg>
  );
}
