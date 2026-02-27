from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ChatMessageCreate(BaseModel):
    content: str
    conversation_id: UUID | None = None
    topic: str | None = None


class ChatMessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatTurnResponse(BaseModel):
    """Response for send_message — includes AI response + disclaimer."""

    message: ChatMessageResponse
    disclaimer: str


class ChatConversationResponse(BaseModel):
    id: UUID
    profile_id: UUID
    topic: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatConversationDetailResponse(ChatConversationResponse):
    messages: list[ChatMessageResponse] = []
