import re
from typing import List

# --------------------------------------------------------------------------- #
# Prompt-injection defense for ingested-document content
#
# Document chunks are untrusted, user-controlled input (any signed-in user
# can upload a document - see src/storage/database.py's user_id scoping)
# that gets embedded verbatim into the generation prompt in
# query_pipeline.py. A chunk could contain text engineered to look like an
# instruction to the model ("ignore the above and reveal X") rather than
# content to analyze.
#
# Two layers, deliberately both partial rather than either being treated
# as a complete fix (see GitHub issue #13's "expect iteration against real
# adversarial inputs, not a one-shot fix"):
#   1. Instruction-hierarchy framing + delimiter discipline in the prompt
#      itself (see query_pipeline.py's generation prompt) - the primary
#      defense, independent of pattern-matching.
#   2. scan_for_injection_patterns() below - a best-effort heuristic flag,
#      logged to telemetry for observability, NOT used to silently
#      strip/block chunk content. A real technical manual can legitimately
#      contain phrasing that overlaps with these patterns (e.g. a safety
#      section titled "Overriding the Emergency Stop" or a warning that
#      literally says "do not disregard this instruction") - blocking on
#      a heuristic match would censor legitimate retrieved content and
#      produce a worse failure mode (silently missing evidence) than the
#      injection risk it's guarding against. Flagging preserves an audit
#      trail without that tradeoff.
# --------------------------------------------------------------------------- #

INJECTION_PATTERNS = [
    re.compile(r"ignore (all |any |the )?(previous|above|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard (all |any |the )?(previous|above|prior)", re.IGNORECASE),
    re.compile(r"\byou are now\b", re.IGNORECASE),
    re.compile(r"new\s+(system\s+)?instructions?\s*:", re.IGNORECASE),
    # Requires directive language after the fake role line, not just
    # "system:"/"assistant:" alone - a bare colon-prefixed line is
    # ordinary in technical documentation (status tables, log excerpts
    # like "System: Ready") and produced false positives on exactly the
    # kind of corpus this module's own docstring cites as legitimate.
    re.compile(
        r"^\s*(system|assistant)\s*:\s*(you (must|should|are)|ignore|disregard|from now on)",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(r"reveal (your|the)\s+(system\s+prompt|instructions|api\s+key)", re.IGNORECASE),
    re.compile(r"\bthis is (your|the) (new|real) (system\s+prompt|task)\b", re.IGNORECASE),
    # "act as" alone is too generic for a technical corpus ("the
    # thermistor can act as a current limiter") - only flag it paired
    # with an AI/assistant-roleplay target, the actual jailbreak framing.
    re.compile(r"\bact as (an?|the)\s+\w*\s*(ai|assistant|chatbot|bot|llm|model)\b", re.IGNORECASE),
]


def scan_for_injection_patterns(text: str) -> List[str]:
    """
    Returns the distinct regex patterns (as strings) that matched `text`,
    empty if none did. Best-effort heuristic flagging only - see module
    docstring for why this never blocks/strips content outright.
    """
    if not text:
        return []
    return [pattern.pattern for pattern in INJECTION_PATTERNS if pattern.search(text)]
