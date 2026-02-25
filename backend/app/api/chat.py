from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_verified_profile
from app.core.database import get_db
from app.models.chat import ChatConversation, ChatMessage
from app.models.profile import Profile
from app.schemas.chat import (
    ChatConversationDetailResponse,
    ChatConversationResponse,
    ChatMessageCreate,
    ChatMessageResponse,
)
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/profiles/{pid}/chat", tags=["chat"])


@router.post("", response_model=ChatMessageResponse, status_code=201)
async def send_message(
    data: ChatMessageCreate,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
) -> ChatMessageResponse:
    """Send a chat message. Creates a new conversation if topic is provided."""
    conversation = ChatConversation(profile_id=profile.id, topic=data.topic)
    db.add(conversation)
    await db.flush()

    message = ChatMessage(conversation_id=conversation.id, role="user", content=data.content)
    db.add(message)
    await db.flush()
    await db.refresh(message)
    return ChatMessageResponse.model_validate(message)


@router.get("", response_model=PaginatedResponse[ChatConversationResponse])
async def list_conversations(
    profile: Profile = Depends(get_verified_profile),
    topic: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ChatConversationResponse]:
    """List chat conversations for the profile."""
    base_query = select(ChatConversation).where(ChatConversation.profile_id == profile.id)
    if topic:
        base_query = base_query.where(ChatConversation.topic.ilike(f"%{topic}%"))

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        base_query.offset((page - 1) * per_page)
        .limit(per_page)
        .order_by(ChatConversation.updated_at.desc())
    )
    conversations = result.scalars().all()

    return PaginatedResponse(
        items=[ChatConversationResponse.model_validate(c) for c in conversations],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{cid}", response_model=ChatConversationDetailResponse)
async def get_conversation(
    cid: UUID,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
) -> ChatConversationDetailResponse:
    """Get messages for a specific conversation."""
    result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == cid, ChatConversation.profile_id == profile.id
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ChatConversationDetailResponse.model_validate(conversation)
