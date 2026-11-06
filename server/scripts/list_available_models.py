"""
Prints every model this GEMINI_API_KEY can actually call right now, split
into likely text-chat candidates and embedding-capable models - the two
categories src/core/llm.py's generate_chat_response()/
generate_structured_response() and get_embedding() respectively depend on.

Use this to build GEMINI_CHAT_MODEL_CHAIN (see src/core/config.py) from
real, currently-callable model ids instead of guessing from a marketing-
name list, which may not match the literal API model id or may name a
model this key's tier/region can't reach yet.

IMPORTANT: the API's "generateContent" action is shared by every model
that produces content of ANY kind through that one RPC - not just plain
text chat. On a real key, this includes TTS, image-generation ("Nano
Banana"), music generation (Lyria), transcription, and agent-product
models (Antigravity, Deep Research, Computer Use) - none of which behave
like a drop-in chat-completion model for query_pipeline.py's prompts.
This script applies a name-based keyword filter to separate those out,
but it's a heuristic over model names, not a real modality check - still
eyeball the "likely text-chat candidates" list before trusting it, and
check the "excluded" list in case something real got filtered out by a
name that happens to contain one of the keywords.

Deliberately does not rank by price/speed within the likely-candidates
list - that judgment call (how many fallback candidates, in what order)
belongs to whoever edits GEMINI_CHAT_MODEL_CHAIN, not to this script.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.llm import client  # noqa: E402

CHAT_ACTION = "generateContent"
EMBED_ACTION = "embedContent"

# Name fragments that reliably mean "not a plain text-in/text-out chat
# model" on every model id/display name seen so far (TTS, image, music,
# transcription, agent products, live/voice sessions, embodied-reasoning).
# This is a heuristic, not a modality lookup the API exposes directly -
# revisit if a new model line doesn't fit this pattern.
_NON_TEXT_CHAT_KEYWORDS = (
    "tts",
    "image",
    "banana",
    "lyria",
    "transcribe",
    "robotics",
    "computer-use",
    "antigravity",
    "deep-research",
    "live",
)


def _short_id(model_name: str) -> str:
    # The API returns "models/gemini-2.5-flash" - config.py's
    # gemini_chat_model/gemini_embedding_model settings expect the bare
    # id without the "models/" prefix.
    return model_name.removeprefix("models/")


def _looks_like_text_chat(model) -> bool:
    haystack = f"{model.name} {model.display_name or ''}".lower()
    return not any(kw in haystack for kw in _NON_TEXT_CHAT_KEYWORDS)


def main() -> None:
    models = list(client.models.list())

    chat_capable = [m for m in models if CHAT_ACTION in (m.supported_actions or [])]
    embed_models = [m for m in models if EMBED_ACTION in (m.supported_actions or [])]

    likely_text_chat = [m for m in chat_capable if _looks_like_text_chat(m)]
    excluded = [m for m in chat_capable if not _looks_like_text_chat(m)]

    print("Likely text-chat candidates (generateContent, name-filtered):\n")
    for m in likely_text_chat:
        print(f"  {_short_id(m.name):<40} {m.display_name or ''}")

    print(f"\nExcluded by the non-text-chat name filter ({len(excluded)} models) - verify before using:\n")
    for m in excluded:
        print(f"  {_short_id(m.name):<40} {m.display_name or ''}")

    print(f"\nEmbedding-capable models ({EMBED_ACTION}):\n")
    for m in embed_models:
        print(f"  {_short_id(m.name):<40} {m.display_name or ''}")

    if likely_text_chat:
        example_chain = ",".join(_short_id(m.name) for m in likely_text_chat[:4])
        print(f"\nExample GEMINI_CHAT_MODEL_CHAIN value:\n  {example_chain}")


if __name__ == "__main__":
    main()
