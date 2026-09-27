from typing import Any, Dict, List

# --------------------------------------------------------------------------- #
# Source citations
#
# query_pipeline.py already knows exactly which chunks were used to build
# the final generation prompt (final_context_chunks) - previously that
# metadata was discarded after generation instead of being surfaced to the
# caller, so a user had no way to verify a claim against its source. This
# module reshapes those chunks into a citation-friendly `sources` list for
# the API response and the web UI's citation list: document name,
# location (page/section), and a short snippet, numbered to match the
# "CHUNK N" numbering already used in the generation prompt.
# --------------------------------------------------------------------------- #

SNIPPET_MAX_CHARS = 280


def build_sources(context_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Builds the `sources` array from the chunks actually used to generate
    an answer (or the closest matches found, when the pipeline abstains).

    Each entry: 1-based `index` (matches "CHUNK N" in the generation
    prompt so a UI can align inline citation numbers with this list),
    `document`, `page`, `section`, and a truncated `snippet` of the
    matched text - not the full chunk_text, since this is for a user to
    spot-check a claim, not to re-read the whole chunk.
    """
    sources = []
    for idx, chunk in enumerate(context_chunks):
        sources.append({
            "index": idx + 1,
            "document": chunk.get("source_file", "unknown"),
            "page": chunk.get("page_number"),
            "section": chunk.get("expanded_heading") or chunk.get("heading_path") or "Unknown Section",
            "snippet": _snippet(chunk.get("chunk_text", "")),
        })
    return sources


def _snippet(text: str) -> str:
    text = text.strip()
    if len(text) <= SNIPPET_MAX_CHARS:
        return text
    truncated = text[:SNIPPET_MAX_CHARS].rsplit(" ", 1)[0]
    return f"{truncated}…"
