import uuid

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user, CurrentUser
from api.schemas import ChatMessageIn, ConversationCreate
from src.query_pipeline import process_chat_query
from src.storage.database import (
    create_conversation,
    list_conversations,
    get_conversation,
    delete_conversation,
    insert_message,
    get_conversation_messages,
    touch_conversation,
)

router = APIRouter()

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
async def create_conversation_endpoint(body: ConversationCreate, user: CurrentUser = Depends(get_current_user)):
    conversation_id = uuid.uuid4().hex
    create_conversation(conversation_id, user_id=user.id, doc_id=body.doc_id)
    return get_conversation(conversation_id)


@router.get("/conversations")
async def list_conversations_endpoint(user: CurrentUser = Depends(get_current_user)):
    """Sidebar conversation list, newest-first, each with its document's filename attached."""
    return {"conversations": list_conversations(user.id)}


@router.get("/conversations/{conversation_id}")
async def get_conversation_endpoint(conversation_id: str, user: CurrentUser = Depends(get_current_user)):
    conversation = _get_owned_conversation(conversation_id, user)
    return {"conversation": conversation, "messages": get_conversation_messages(conversation_id)}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation_endpoint(conversation_id: str, user: CurrentUser = Depends(get_current_user)):
    _get_owned_conversation(conversation_id, user)
    delete_conversation(conversation_id)
    return {"status": "deleted"}


@router.post("/conversations/{conversation_id}/messages")
async def send_message_endpoint(
    conversation_id: str, body: ChatMessageIn, user: CurrentUser = Depends(get_current_user)
):
    """
    Replaces the old flat POST /chat: scoped to one conversation's document
    (doc_id), and folds recent turns into the prompt so follow-ups work.
    """
    conversation = _get_owned_conversation(conversation_id, user)

    history_rows = get_conversation_messages(conversation_id, limit=HISTORY_TURNS)
    history = [{"role": m["role"], "content": m["content"]} for m in history_rows]

    insert_message(conversation_id, role="user", content=body.message)

    try:
        result = process_chat_query(
            body.message,
            advanced_mode=body.advanced_mode,
            doc_id=conversation["doc_id"],
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
