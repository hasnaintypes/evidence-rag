import uuid

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user, CurrentUser
from api.schemas import ChatMessageIn, ConversationCreate, ConversationUpdate, AddConversationDocument
from src.query_pipeline import process_chat_query
from src.storage.database import (
    create_conversation,
    list_conversations,
    get_conversation,
    delete_conversation,
    add_document_to_conversation,
    update_conversation,
    insert_message,
    get_conversation_messages,
    touch_conversation,
    delete_messages_after,
)

router = APIRouter()

# Plain `def`, not `async def`, on every route below: they all call
# synchronous/blocking code (psycopg2, the Gemini SDK) and FastAPI runs
# `async def` handlers directly on the single event loop with no
# automatic thread offload - a blocking call in one would stall every
# other concurrent request. Plain `def` handlers get dispatched to
# FastAPI's thread pool instead.

HISTORY_TURNS = 6  # prior turns folded into the generation prompt - bounded so the prompt doesn't grow unbounded over a long conversation
TITLE_MAX_CHARS = 60


def _get_owned_conversation(conversation_id: str, user: CurrentUser) -> dict:
    """Raises 404 (not 403) for a conversation that exists but belongs to
    someone else - doesn't confirm to a caller that a given ID exists at all."""
    conversation = get_conversation(conversation_id)
    if not conversation or conversation["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


@router.post("/conversations")
def create_conversation_endpoint(body: ConversationCreate, user: CurrentUser = Depends(get_current_user)):
    conversation_id = uuid.uuid4().hex
    return create_conversation(conversation_id, user_id=user.id, doc_ids=body.doc_ids)


@router.get("/conversations")
def list_conversations_endpoint(user: CurrentUser = Depends(get_current_user)):
    """Sidebar conversation list, newest-first, each with its document's filename attached."""
    return {"conversations": list_conversations(user.id)}


@router.get("/conversations/{conversation_id}")
def get_conversation_endpoint(conversation_id: str, user: CurrentUser = Depends(get_current_user)):
    conversation = _get_owned_conversation(conversation_id, user)
    return {"conversation": conversation, "messages": get_conversation_messages(conversation_id)}


@router.delete("/conversations/{conversation_id}")
def delete_conversation_endpoint(conversation_id: str, user: CurrentUser = Depends(get_current_user)):
    _get_owned_conversation(conversation_id, user)
    delete_conversation(conversation_id)
    return {"status": "deleted"}


@router.patch("/conversations/{conversation_id}")
def update_conversation_endpoint(
    conversation_id: str, body: ConversationUpdate, user: CurrentUser = Depends(get_current_user)
):
    matched = update_conversation(conversation_id, user_id=user.id, title=body.title, pinned=body.pinned)
    if not matched:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"status": "updated"}


@router.post("/conversations/{conversation_id}/documents")
def add_conversation_document_endpoint(
    conversation_id: str, body: AddConversationDocument, user: CurrentUser = Depends(get_current_user)
):
    try:
        return add_document_to_conversation(conversation_id, user_id=user.id, doc_id=body.doc_id)
    except ValueError as e:
        detail = str(e)
        status_code = 404 if detail == "Conversation not found." else 400
        raise HTTPException(status_code=status_code, detail=detail)


@router.post("/conversations/{conversation_id}/checkpoints/{message_id}/restore")
def restore_checkpoint_endpoint(
    conversation_id: str, message_id: int, user: CurrentUser = Depends(get_current_user)
):
    """Rewinds the conversation to right after message_id, deleting
    everything sent after it, so the user can continue from that point."""
    _get_owned_conversation(conversation_id, user)
    delete_messages_after(conversation_id, message_id)
    return {"messages": get_conversation_messages(conversation_id)}


@router.post("/conversations/{conversation_id}/messages")
def send_message_endpoint(
    conversation_id: str, body: ChatMessageIn, user: CurrentUser = Depends(get_current_user)
):
    """
    Replaces the old flat POST /chat: scoped to one conversation's documents
    (doc_ids, up to 5), and folds recent turns into the prompt so follow-ups work.
    """
    conversation = _get_owned_conversation(conversation_id, user)

    history_rows = get_conversation_messages(conversation_id, limit=HISTORY_TURNS)
    history = [{"role": m["role"], "content": m["content"]} for m in history_rows]

    insert_message(conversation_id, role="user", content=body.message)

    try:
        result = process_chat_query(
            body.message,
            advanced_mode=body.advanced_mode,
            doc_ids=conversation["doc_ids"],
            history=history,
        )
    except Exception as e:
        result = {
            "reply": f"An error occurred: {str(e)}",
            "thinking": "Pipeline failure.",
            "telemetry": {},
            "chunks_matrix": [],
            "sources": [],
            "faithfulness": {"score": None, "unsupported_claims": []},
        }

    assistant_message = insert_message(
        conversation_id,
        role="assistant",
        content=result["reply"],
        sources=result.get("sources", []),
        faithfulness_score=(result.get("faithfulness") or {}).get("score"),
    )

    # touch_conversation only sets the title if it's still unset (COALESCE),
    # so it's safe to pass a candidate title on every message, not just the first.
    touch_conversation(conversation_id, title=body.message[:TITLE_MAX_CHARS])

    return {
        **assistant_message,
        "telemetry": result.get("telemetry", {}),
        "chunks_matrix": result.get("chunks_matrix", []),
        "thinking": result.get("thinking", ""),
    }
