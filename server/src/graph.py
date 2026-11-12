from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from src.core.llm import generate_structured_response
from src.storage.database import upsert_entity, upsert_edge, get_children

MIN_SECTION_LENGTH_FOR_EXTRACTION = 100

# Batched (GRAPH_BATCH_SIZE sections per Gemini call) AND concurrent
# (GRAPH_CONCURRENCY batches in flight at once) - same rationale as
# ingestion/pipeline.py's EMBED_BATCH_SIZE/EMBED_CONCURRENCY: one call per
# section was the dominant ingestion cost for any document with many
# sections (50 sections = 50 sequential round trips), and per-request
# latency, not generation compute, is what that cost is made of. A
# structured schema call (like retrieval/reranker.py's batched rerank)
# also removes the need for the free-text regex/repetition-loop parsing
# this module used to do per section - the model is constrained to return
# valid JSON directly.
GRAPH_BATCH_SIZE = 5
GRAPH_CONCURRENCY = 4

GRAPH_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "1-based SECTION number from the prompt."},
                    "entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "2 to 8 key technical terms/named concepts for this section, "
                        "or an empty array if the section has none.",
                    },
                },
                "required": ["index", "entities"],
            },
        }
    },
    "required": ["sections"],
}

GRAPH_PROMPT = """You are extracting key technical terms, part names, or named concepts from \
sections of a technical document, to build an entity-relationship graph.

For each section below, extract 2 to 8 key technical terms or named concepts \
(e.g. "Emergency Stop", "SCARA", "600 hours"). If a section has no meaningful \
technical terms, use an empty array for it.

SECTIONS:
{sections_block}

Return one entry per section listed above - do not skip any."""


def _format_sections_for_extraction(texts: List[str]) -> str:
    parts = []
    for idx, text in enumerate(texts):
        parts.append(f"--- SECTION {idx + 1} ---\n{text[:2000]}")
    return "\n\n".join(parts)


def extract_entities_batch(texts: List[str]) -> List[List[str]]:
    """
    Extracts a small set of key entities/terms for each section's text in
    `texts` via a single batched Gemini call, returning a list of entity
    lists in the same order as `texts` (see retrieval/reranker.py's
    rerank_chunks() for the same batched-structured-output pattern).

    On any failure (API error, malformed/missing JSON) every section falls
    back to an empty entity list - entity extraction is a best-effort
    enrichment step, never allowed to break ingestion. A section the
    model's response simply omits an entry for gets the same empty-list
    fallback, rather than crashing on a missing index.
    """
    if not texts:
        return []

    prompt = GRAPH_PROMPT.format(sections_block=_format_sections_for_extraction(texts))
    # ~150 tokens/section was the old per-call budget for a single
    # section's entity array; sized with headroom per section here since
    # a batch call also repeats the {index, entities} wrapper per entry.
    result = generate_structured_response(
        prompt, response_schema=GRAPH_RESPONSE_SCHEMA, max_tokens=max(300, 200 * len(texts))
    )

    entities_by_index: Dict[int, List[str]] = {}
    if isinstance(result, dict) and isinstance(result.get("sections"), list):
        for entry in result["sections"]:
            if not isinstance(entry, dict):
                continue
            idx = entry.get("index")
            entities = entry.get("entities")
            if isinstance(idx, int) and isinstance(entities, list):
                entities_by_index[idx] = [
                    str(e).strip() for e in entities if isinstance(e, (str, int, float)) and str(e).strip()
                ][:8]

    return [entities_by_index.get(position + 1, []) for position in range(len(texts))]


def build_document_graph(doc_id: str, section_nodes: List[Dict[str, Any]]) -> int:
    """
    Builds the entity graph for every section in `section_nodes`: gathers
    each section's combined text, extracts entities in batches of
    GRAPH_BATCH_SIZE (GRAPH_CONCURRENCY batches concurrently, same pattern
    as ingestion/pipeline.py's embedding batches), then upserts entities
    and their pairwise co-occurrence edges.

    DB writes (upsert_entity/upsert_edge) happen sequentially on the
    calling thread after every batch's LLM call has returned, rather than
    inside the concurrent workers - the concurrency here is for network
    round trips, not for the DB layer, same division as finish_ingest()'s
    concurrent embedding calls followed by a single sequential insert.
    """
    sections: List[tuple] = []
    for section in section_nodes:
        section_id = section["id"] if hasattr(section, "get") else section.id
        children = get_children(section_id)
        combined_text = "\n".join(
            (child.get("content") or "").strip() for child in children if child.get("content")
        ).strip()
        if len(combined_text) >= MIN_SECTION_LENGTH_FOR_EXTRACTION:
            sections.append((section_id, combined_text))

    total = len(section_nodes)
    if not sections:
        print(f"      entity graph: 0/{total} sections had extractable text")
        return total

    batches = [sections[i : i + GRAPH_BATCH_SIZE] for i in range(0, len(sections), GRAPH_BATCH_SIZE)]

    def _run_batch(batch: List[tuple]) -> List[tuple]:
        entity_lists = extract_entities_batch([text for _, text in batch])
        return list(zip([section_id for section_id, _ in batch], entity_lists))

    with ThreadPoolExecutor(max_workers=GRAPH_CONCURRENCY) as executor:
        results = [pair for batch_result in executor.map(_run_batch, batches) for pair in batch_result]

    processed = 0
    for section_id, entity_names in results:
        if len(entity_names) >= 2:
            entity_ids = sorted({upsert_entity(doc_id=doc_id, name=name, node_id=section_id) for name in entity_names})
            for i in range(len(entity_ids)):
                for j in range(i + 1, len(entity_ids)):
                    upsert_edge(doc_id=doc_id, source_entity_id=entity_ids[i], target_entity_id=entity_ids[j])
        processed += 1
        print(f"      entity graph: {processed}/{len(sections)} sections with content processed", end="\r")
    print()
    return total
