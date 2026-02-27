from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.core import AgentCore
from app.api.deps import (
    get_agent_core,
    get_context_builder,
    get_memory_extractor,
    get_verified_profile,
)
from app.core.database import get_db
from app.models.chat import ChatConversation
from app.models.profile import Profile
from app.schemas.chat import (
    ChatConversationDetailResponse,
    ChatConversationResponse,
    ChatMessageCreate,
    ChatTurnResponse,
)
from app.schemas.common import PaginatedResponse
from app.services.chat import ChatService
from app.services.context_builder import ContextBuilder
from app.services.memory_extractor import MemoryExtractor

router = APIRouter(prefix="/profiles/{pid}/chat", tags=["chat"])


def _build_service(
    db: AsyncSession,
    agent_core: AgentCore,
    context_builder: ContextBuilder,
    memory_extractor: MemoryExtractor,
) -> ChatService:
    return ChatService(
        db=db,
        agent_core=agent_core,
        context_builder=context_builder,
        memory_extractor=memory_extractor,
    )


@router.post("", response_model=ChatTurnResponse, status_code=201)
async def send_message(
    data: ChatMessageCreate,
    background_tasks: BackgroundTasks,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
    agent_core: AgentCore = Depends(get_agent_core),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> ChatTurnResponse:
    """Send a chat message. Creates a new conversation or continues an existing one."""
    svc = _build_service(db, agent_core, context_builder, memory_extractor)
    conversation, turn_response = await svc.send_message(
        profile,
        data.content,
        conversation_id=data.conversation_id,
        topic=data.topic,
    )

    background_tasks.add_task(
        memory_extractor.extract_and_store,
        profile_id=profile.id,
        messages=[
            {"role": "user", "content": data.content},
            {"role": "assistant", "content": turn_response.message.content},
        ],
        source=f"chat:{conversation.id}",
        category="general",
    )

    return turn_response


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
