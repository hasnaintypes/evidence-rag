from typing import Any, Optional
from pydantic import BaseModel


class ChatMessageIn(BaseModel):
    message: str
    advanced_mode: bool = True


class ConversationCreate(BaseModel):
    doc_id: str


class ConversationOut(BaseModel):
    id: str
    doc_id: str
    filename: Optional[str] = None
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
