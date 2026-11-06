from typing import Any, Optional
from pydantic import BaseModel, Field


class ChatMessageIn(BaseModel):
    message: str
    advanced_mode: bool = True


class ConversationCreate(BaseModel):
    doc_ids: list[str] = Field(min_length=1, max_length=5)


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    pinned: Optional[bool] = None


class AddConversationDocument(BaseModel):
    doc_id: str


class DocumentRename(BaseModel):
    filename: str = Field(min_length=1, max_length=255)


class ConversationOut(BaseModel):
    id: str
    doc_ids: list[str]
    filenames: list[Optional[str]] = []
    pinned: bool = False
    title: Optional[str] = None
    created_at: Any
    updated_at: Any


class MessageOut(BaseModel):
    id: int
    conversation_id: str
    role: str
    content: str
    sources: list = []
    faithfulness_score: Optional[float] = None
    created_at: Any


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]


class ConversationListOut(BaseModel):
    conversations: list[ConversationOut]


class ChatReplyOut(MessageOut):
    """POST /conversations/{id}/messages's response shape - a message
    row plus the extra explainability fields query_pipeline.py attaches
    (telemetry, chunks_matrix, thinking) that the frontend's chat panel
    reads directly. Kept as its own schema rather than reusing MessageOut
    as-is, since a bare response_model=MessageOut here would silently
    strip these fields instead of validating them (#56)."""

    telemetry: dict = {}
    chunks_matrix: list = []
    thinking: str = ""
