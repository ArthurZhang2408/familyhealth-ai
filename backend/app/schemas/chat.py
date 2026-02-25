from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ChatMessageCreate(BaseModel):
    content: str
    topic: str | None = None


class ChatMessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatConversationResponse(BaseModel):
    id: UUID
    profile_id: UUID
    topic: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatConversationDetailResponse(ChatConversationResponse):
    messages: list[ChatMessageResponse] = []
