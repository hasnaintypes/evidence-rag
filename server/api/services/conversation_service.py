import json
import logging
import uuid
from typing import Any, Dict, Iterator, List, Optional

import structlog
from fastapi import BackgroundTasks, HTTPException
from fastapi.encoders import jsonable_encoder

from api.authz import get_owned_conversation
from api.deps import CurrentUser
from src.query_pipeline import process_chat_query, process_chat_query_stream
from src.core.llm import generate_llm_json, llm_cooldown_remaining_seconds
from src.core.security import generate_source_token

# Same "inherits whatever handler the process entry point set up for the
# root logger" convention as observability.py's "evidence_rag.pipeline"
# logger and llm.py's "evidence_rag.llm" logger.
logger = logging.getLogger("evidence_rag.api")
from src.storage.database import (
    add_document_to_conversation,
    all_documents_accessible,
    create_conversation,
    delete_conversation,
    delete_messages_after,
    get_conversation_messages,
    get_default_conversation_doc_ids,
    get_untitled_chat_numbers,
    insert_message,
    list_conversations,
    replace_fallback_title,
    touch_conversation,
    update_conversation,
)

HISTORY_TURNS = 6  # prior turns folded into the generation prompt - bounded so the prompt doesn't grow unbounded over a long conversation
TITLE_MAX_CHARS = 60

TITLE_PROMPT = """Generate a short, specific title (4-8 words, no quotes, no trailing \
punctuation) for a chat that starts with this question:

{question}

Output ONLY a JSON object of this exact shape, no other text before or after it:
{{"title": "<the title>"}}"""


def _generate_title(user_message: str) -> Optional[str]:
    """LLM-generated short chat title from the first user turn. Best-
    effort, same defensive isinstance-checked-before-use posture as
    evaluation/judge.py's score_faithfulness() - returns None on any
    failure (bad/missing API response, wrong type) so the caller falls
    back to an "Untitled chat" placeholder; never raises, never blocks
    the real reply on this. No server-enforced JSON schema (see
    src/core/llm.py's generate_llm_json() docstring) - the prompt above
    asks for the shape in text instead.

    Skips the call entirely (returns None immediately) if the shared LLM
    endpoint is already cooling down from a 429 - this is the 5th call
    for the same message (query rewriting, reranking, answer generation,
    and faithfulness judging already ran), so it's the cheapest one to
    give up on first instead of burning another round trip that's
    already known to fail."""
    if llm_cooldown_remaining_seconds() > 0:
        return None
    result = generate_llm_json(TITLE_PROMPT.format(question=user_message), max_tokens=50, operation="title_generation")
    if not isinstance(result, dict):
        return None
    title = result.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    return title.strip()[:TITLE_MAX_CHARS]


def _next_untitled_title(user_id: str) -> str:
    """ "Untitled chat" for this user's first one, "Untitled chat 2"/"3"/...
    after that - same incrementing-placeholder convention as a file
    manager's "untitled folder"/"untitled folder 2", so a run of title-
    generation failures (e.g. the free-tier quota exhaustion this project
    keeps hitting) never shows the user their own raw prompt text back as
    a permanent conversation title."""
    used = get_untitled_chat_numbers(user_id)
    if not used:
        return "Untitled chat"
    return f"Untitled chat {max(used) + 1}"


class ConversationService:
    """
    Owns conversation CRUD, chat messages, and checkpoint restore -
    loading the resource, asserting ownership via api/authz.py, then
    acting - so api/routers/conversations.py stays a thin HTTP-shape
    adapter. See GitHub issue #18 / 02-Architecture.md's Proposed Changes.
    """

    @staticmethod
    def create(doc_ids: List[str], user: CurrentUser) -> Dict[str, Any]:
        """
        No document attached (doc_ids empty) resolves to this user's own
        already-indexed documents if they have any, so starting a chat
        never requires picking one first - see
        get_default_conversation_doc_ids()'s docstring for the full
        fallback chain (own documents, then the shared/demo corpus for a
        brand-new account with nothing uploaded yet).
        """
        if not doc_ids:
            doc_ids = get_default_conversation_doc_ids(user.id)
            if not doc_ids:
                raise HTTPException(status_code=400, detail="No documents are available to chat about yet.")
        elif not all_documents_accessible(doc_ids, user.id):
            raise HTTPException(status_code=404, detail="One or more documents were not found.")
        conversation_id = uuid.uuid4().hex
        return create_conversation(conversation_id, user_id=user.id, doc_ids=doc_ids)

    @staticmethod
    def list_for_user(user: CurrentUser, limit: int = 30, cursor: Optional[str] = None) -> Dict[str, Any]:
        """Lightweight, paginated sidebar conversation list - no doc_ids/
        filenames, see get_with_messages()/create() for the full shape a
        single conversation needs. Clamps limit so a caller can't request
        an unbounded page."""
        return list_conversations(user.id, limit=max(1, min(limit, 100)), cursor=cursor)

    @staticmethod
    def get_with_messages(conversation_id: str, user: CurrentUser) -> Dict[str, Any]:
        conversation = get_owned_conversation(conversation_id, user)
        messages = ConversationService._refresh_source_tokens(get_conversation_messages(conversation_id), user)
        return {"conversation": conversation, "messages": messages}

    @staticmethod
    def delete(conversation_id: str, user: CurrentUser) -> Dict[str, Any]:
        get_owned_conversation(conversation_id, user)
        delete_conversation(conversation_id)
        return {"status": "deleted"}

    @staticmethod
    def update(conversation_id: str, user: CurrentUser, title: Optional[str], pinned: Optional[bool]) -> Dict[str, Any]:
        matched = update_conversation(conversation_id, user_id=user.id, title=title, pinned=pinned)
        if not matched:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        return {"status": "updated"}

    @staticmethod
    def add_document(conversation_id: str, doc_id: str, user: CurrentUser) -> Dict[str, Any]:
        """Ownership is asserted via get_owned_conversation() (404 for a
        non-owner/missing conversation), same as every other mutation
        here - add_document_to_conversation() used to fold its own inline
        ownership check into this call instead and reported it by raising
        ValueError("Conversation not found.") for the router to string-
        match back into a 404, the one call site that didn't route
        through api/authz.py like the rest (#54).

        add_document_to_conversation() still raises LookupError (not
        ValueError) if the conversation vanished between the ownership
        check above and its own SELECT (a concurrent delete) - a distinct
        type, not another string to match, so that race still 404s
        instead of surfacing as an unhandled 500."""
        get_owned_conversation(conversation_id, user)
        if not all_documents_accessible([doc_id], user.id):
            raise HTTPException(status_code=404, detail="Document not found.")
        try:
            return add_document_to_conversation(conversation_id, doc_id=doc_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @staticmethod
    def restore_checkpoint(conversation_id: str, message_id: int, user: CurrentUser) -> Dict[str, Any]:
        """Rewinds the conversation to right after message_id, deleting
        everything sent after it, so the user can continue from that point."""
        get_owned_conversation(conversation_id, user)
        delete_messages_after(conversation_id, message_id)
        return {"messages": get_conversation_messages(conversation_id)}

    @staticmethod
    def send_message(
        conversation_id: str, message: str, advanced_mode: bool, user: CurrentUser, background_tasks: BackgroundTasks
    ) -> Dict[str, Any]:
        """
        Replaces the old flat POST /chat: scoped to one conversation's documents
        (doc_ids, up to 5), and folds recent turns into the prompt so follow-ups work.

        A pipeline failure (process_chat_query() raising) is a genuine 500, not a
        200 with a fabricated "An error occurred: ..." reply - that used to be
        stored as if it were a real assistant turn, permanently, indistinguishable
        from an honest answer except by reading the text, and could leak internal
        exception detail into chat history (#52). The exception is logged here
        (process_chat_query()'s own stage-level tracing, via
        src.core.observability.traced_stage, already logged *which stage* failed
        under its own request_id - this is the service-layer record of the
        request that hit it) and a generic message is raised instead; nothing
        gets persisted as the assistant's turn. The user's own message above is
        already inserted by this point and stays - they did send it - the
        conversation just has no reply yet, same as it would if the request
        never reached this far at all.
        """
        conversation = get_owned_conversation(conversation_id, user)

        history_rows = get_conversation_messages(conversation_id, limit=HISTORY_TURNS)
        history = [{"role": m["role"], "content": m["content"]} for m in history_rows]

        insert_message(conversation_id, role="user", content=message)

        # Binds chat_session_id to this request's log context (via
        # structlog.contextvars) for the duration of the pipeline call -
        # every event logged anywhere during process_chat_query(),
        # including ai_tracker.py's per-call events and
        # request_summary.py's end-of-request line, picks this up
        # automatically without query_pipeline.py needing to know or
        # pass a conversation id at all.
        with structlog.contextvars.bound_contextvars(chat_session_id=conversation_id):
            try:
                result = process_chat_query(
                    message,
                    advanced_mode=advanced_mode,
                    doc_ids=conversation["doc_ids"],
                    history=history,
                    user_id=user.id,
                )
            except Exception:
                logger.exception(
                    "process_chat_query failed for conversation_id=%s user_id=%s", conversation_id, user.id
                )
                raise HTTPException(status_code=500, detail="Failed to generate a response. Please try again.")

        reply = ConversationService._persist_reply(conversation_id, message, history, result)
        if len(history) == 0:
            background_tasks.add_task(ConversationService._generate_and_apply_title, conversation_id, message, user.id)
        return reply

    @staticmethod
    def send_message_stream(
        conversation_id: str, message: str, advanced_mode: bool, user: CurrentUser
    ) -> Iterator[str]:
        """
        SSE counterpart to send_message(): same ownership check, history
        fold-in, and user-message insert, but streams the answer back as
        it's generated (via process_chat_query_stream()) instead of
        blocking until generation AND the faithfulness judge both finish.

        Yields Server-Sent Events lines ("data: {json}\\n\\n") of two
        shapes: {"type": "token", "text": str} for each chunk of
        generated text, and exactly one final {"type": "done",
        "message": {...}} carrying the same shape send_message() returns
        as its JSON body. A pipeline failure becomes {"type": "error",
        "detail": ...} instead of an HTTP 500 - by the time any of this
        has streamed, response headers (and likely some body) are already
        sent, so a mid-stream failure can only be reported inside the
        stream itself, never as a different status code (same reasoning
        as send_message()'s docstring for #52, applied to a path that
        can't raise an HTTPException partway through).
        """
        conversation = get_owned_conversation(conversation_id, user)

        history_rows = get_conversation_messages(conversation_id, limit=HISTORY_TURNS)
        history = [{"role": m["role"], "content": m["content"]} for m in history_rows]

        insert_message(conversation_id, role="user", content=message)

        def _events() -> Iterator[str]:
            # Bound for the entire generator body, including every yield
            # below - not just the process_chat_query_stream() call - so
            # chat_session_id stays attached to every log line emitted
            # while the SSE consumer is actively pulling tokens (same
            # intent as send_message()'s plain `with` block above; this
            # one just can't be a single `with` wrapping only the call,
            # since the call itself is a generator this function also
            # yields through).
            with structlog.contextvars.bound_contextvars(chat_session_id=conversation_id):
                try:
                    for event in process_chat_query_stream(
                        message,
                        advanced_mode=advanced_mode,
                        doc_ids=conversation["doc_ids"],
                        history=history,
                        user_id=user.id,
                    ):
                        if event["type"] == "token":
                            yield f"data: {json.dumps({'type': 'token', 'text': event['text']})}\n\n"
                            continue
                        reply_message = ConversationService._persist_reply(
                            conversation_id, message, history, event["result"]
                        )
                        # jsonable_encoder, not a bare json.dumps(reply_message) -
                        # under STORAGE_MODE=supabase, insert_message()'s
                        # RETURNING id, created_at gives psycopg2's native
                        # datetime for created_at (SQLite's equivalent column
                        # is already a string), which json.dumps can't
                        # serialize on its own. The non-streaming
                        # send_message() endpoint doesn't hit this because
                        # response_model=ChatReplyOut already runs every
                        # response through this same FastAPI encoder.
                        payload = jsonable_encoder({"type": "done", "message": reply_message})
                        yield f"data: {json.dumps(payload)}\n\n"
                        # Title generation happens AFTER "done" is already on
                        # the wire, not before it - the client has the real
                        # answer and can render it immediately; this extra
                        # LLM call just trails a few hundred ms behind
                        # on the same connection instead of sitting in front
                        # of the answer (2026-11-15 performance audit finding
                        # #1). No BackgroundTasks needed here since this
                        # generator is still live - send_message()'s
                        # non-streaming twin below uses BackgroundTasks
                        # instead, since it has no way to send anything after
                        # its one response.
                        if len(history) == 0:
                            title = ConversationService._generate_and_apply_title(conversation_id, message, user.id)
                            yield f"data: {json.dumps({'type': 'title', 'title': title})}\n\n"
                except Exception:
                    logger.exception(
                        "process_chat_query_stream failed for conversation_id=%s user_id=%s", conversation_id, user.id
                    )
                    error_payload = {"type": "error", "detail": "Failed to generate a response. Please try again."}
                    yield f"data: {json.dumps(error_payload)}\n\n"

        return _events()

    @staticmethod
    def _persist_reply(conversation_id: str, message: str, history: list, result: Dict[str, Any]) -> Dict[str, Any]:
        """Shared by send_message() and send_message_stream(): stores the
        assistant turn and (first turn only) sets a cheap fallback title -
        see send_message()'s docstring for why a pipeline failure never
        reaches this (nothing is persisted for a failed run).

        Does NOT call the title-generation LLM itself anymore (2026-11-15
        performance audit finding #1: that extra LLM round trip was
        blocking this request/stream's critical path for no good reason -
        title is purely cosmetic and already has this same fallback for
        when generation fails). The real title is generated afterward by
        each caller - send_message_stream() inline after its "done" event
        is already on the wire, send_message() via BackgroundTasks since
        it has no way to send anything after its one response - both
        through _generate_and_apply_title() below."""
        assistant_message = insert_message(
            conversation_id,
            role="assistant",
            content=result["reply"],
            sources=result.get("sources", []),
            faithfulness_score=(result.get("faithfulness") or {}).get("score"),
        )

        # First turn only (history was fetched before this message's own
        # insert_message() call, so an empty history means nothing came
        # before this one). touch_conversation only sets the title if it's
        # still unset (COALESCE), so later turns keep passing None safely.
        is_first_turn = len(history) == 0
        touch_conversation(
            conversation_id,
            title=message[:TITLE_MAX_CHARS] if is_first_turn else None,
        )

        return {
            **assistant_message,
            "telemetry": result.get("telemetry", {}),
            "chunks_matrix": result.get("chunks_matrix", []),
            "thinking": result.get("thinking", ""),
            "title": None,
        }

    @staticmethod
    def _generate_and_apply_title(conversation_id: str, message: str, user_id: str) -> str:
        """Generates the real title and swaps it in for the fallback
        truncation _persist_reply() already set, unless the user renamed
        the conversation in the meantime (replace_fallback_title()'s own
        guard against that race). Returns whichever title is now correct
        - the generated one, the fallback itself if it was never
        replaced, or a fresh "Untitled chat"/"Untitled chat N" placeholder
        if generation failed outright - so send_message_stream() can
        report it to the client without a second DB read.

        The LLM title call can fail for two different reasons seen in
        production (rate-limited 429, or an unparseable JSON response) -
        either way _generate_title() returns None, and this used to leave
        the truncated raw prompt as the permanent title forever. Swapping
        that to an incrementing "Untitled chat" placeholder instead keeps
        a repeat quota failure from making every new conversation's title
        just be whatever the user happened to type first."""
        fallback_title = message[:TITLE_MAX_CHARS]
        generated_title = _generate_title(message)
        if generated_title and generated_title != fallback_title:
            replace_fallback_title(conversation_id, fallback_title, generated_title)
            return generated_title
        if not generated_title:
            untitled_title = _next_untitled_title(user_id)
            replace_fallback_title(conversation_id, fallback_title, untitled_title)
            return untitled_title
        return fallback_title

    @staticmethod
    def _refresh_source_tokens(messages: list, user: CurrentUser) -> list:
        """
        Each stored message's sources carry a source_token signed with the TTL
        in effect at send time (see query_pipeline.py's _build_sources()) - by
        the time a conversation is reopened later, those tokens have likely
        expired. Reissuing them here (ownership was already confirmed by
        get_owned_conversation before this is called) keeps old citation
        links clickable without storing a long-lived token in the DB.
        """
        for message in messages:
            for source in message.get("sources") or []:
                source["source_token"] = generate_source_token(source["document"], user.id)
        return messages
