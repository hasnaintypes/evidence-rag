from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.deps import get_current_user, get_rate_limited_chat_user, CurrentUser
from api.schemas import (
    ChatMessageIn,
    ChatReplyOut,
    ConversationCreate,
    ConversationDetailOut,
    ConversationListOut,
    ConversationOut,
    ConversationUpdate,
    AddConversationDocument,
)
from api.services.conversation_service import ConversationService

router = APIRouter()

# Plain `def`, not `async def`, on every route below: they all call
# synchronous/blocking code (psycopg2, the Gemini SDK) and FastAPI runs
# `async def` handlers directly on the single event loop with no
# automatic thread offload - a blocking call in one would stall every
# other concurrent request. Plain `def` handlers get dispatched to
# FastAPI's thread pool instead.


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation_endpoint(body: ConversationCreate, user: CurrentUser = Depends(get_current_user)):
    return ConversationService.create(body.doc_ids, user)


@router.get("/conversations", response_model=ConversationListOut)
def list_conversations_endpoint(
    limit: int = 30, cursor: Optional[str] = None, user: CurrentUser = Depends(get_current_user)
):
    return ConversationService.list_for_user(user, limit=limit, cursor=cursor)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation_endpoint(conversation_id: str, user: CurrentUser = Depends(get_current_user)):
    return ConversationService.get_with_messages(conversation_id, user)


@router.delete("/conversations/{conversation_id}")
def delete_conversation_endpoint(conversation_id: str, user: CurrentUser = Depends(get_current_user)):
    return ConversationService.delete(conversation_id, user)


@router.patch("/conversations/{conversation_id}")
def update_conversation_endpoint(
    conversation_id: str, body: ConversationUpdate, user: CurrentUser = Depends(get_current_user)
):
    return ConversationService.update(conversation_id, user, body.title, body.pinned)


@router.post("/conversations/{conversation_id}/documents", response_model=ConversationOut)
def add_conversation_document_endpoint(
    conversation_id: str, body: AddConversationDocument, user: CurrentUser = Depends(get_current_user)
):
    return ConversationService.add_document(conversation_id, body.doc_id, user)


@router.post("/conversations/{conversation_id}/checkpoints/{message_id}/restore")
def restore_checkpoint_endpoint(conversation_id: str, message_id: int, user: CurrentUser = Depends(get_current_user)):
    return ConversationService.restore_checkpoint(conversation_id, message_id, user)


@router.post("/conversations/{conversation_id}/messages", response_model=ChatReplyOut)
def send_message_endpoint(
    conversation_id: str, body: ChatMessageIn, user: CurrentUser = Depends(get_rate_limited_chat_user)
):
    """Non-streaming JSON reply - kept alongside the SSE route below for
    any caller that just wants the final answer in one response (the
    interactive API docs, scripts, other integrations). The web UI itself
    calls /messages/stream instead, for the perceived-latency win of
    showing tokens as they're generated."""
    return ConversationService.send_message(conversation_id, body.message, body.advanced_mode, user)


@router.post("/conversations/{conversation_id}/messages/stream")
def send_message_stream_endpoint(
    conversation_id: str, body: ChatMessageIn, user: CurrentUser = Depends(get_rate_limited_chat_user)
):
    """Server-Sent Events stream of the same reply - see
    ConversationService.send_message_stream()."""
    return StreamingResponse(
        ConversationService.send_message_stream(conversation_id, body.message, body.advanced_mode, user),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
