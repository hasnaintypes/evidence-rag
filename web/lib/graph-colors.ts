// Categorical palette for the entity graph. The real data model has no
// entity "type" (server/src/graph.py extracts flat co-occurring entity
// names, not a person/org/concept taxonomy) - documents are the one
// categorical dimension every GraphNode actually carries (doc_id), so
// nodes/the legend are colored by contributing document instead of a
// fabricated type.
const PALETTE = [
  "oklch(0.72 0.14 237)", // blue
  "oklch(0.75 0.15 150)", // green
  "oklch(0.78 0.15 80)", // amber
  "oklch(0.75 0.12 330)", // pink
  "oklch(0.72 0.16 300)", // purple
  "oklch(0.75 0.13 195)", // cyan
];

export function colorForDocId(docId: string, allDocIds: string[]): string {
  const index = allDocIds.indexOf(docId);
  return PALETTE[(index < 0 ? 0 : index) % PALETTE.length];
}

export function distinctDocIds(docIds: string[]): string[] {
  return Array.from(new Set(docIds)).sort();
}

// Inserts an alpha channel into one of this module's `oklch(l c h)`
// strings (`oklch(l c h / a%)`), for a tinted badge background behind the
// same solid color used for its text/dot.
export function withAlpha(oklchColor: string, alphaPercent: number): string {
  return oklchColor.replace(")", ` / ${alphaPercent}%)`);
}
