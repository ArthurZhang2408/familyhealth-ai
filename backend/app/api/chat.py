import asyncio
import json
import logging
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.core import AgentCore
from app.agents.types import AgentEvent, AgentEventType
from app.api.deps import (
    get_agent_core,
    get_context_builder,
    get_memory_extractor,
    get_verified_profile,
)
from app.api.upload_helpers import read_image_parts
from app.core.database import async_session_factory, get_db
from app.models.chat import ChatConversation
from app.models.profile import Profile
from app.schemas.chat import (
    ChatConversationDetailResponse,
    ChatConversationResponse,
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
    background_tasks: BackgroundTasks,
    content: str = Form(...),
    conversation_id: UUID | None = Form(None),
    topic: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
    agent_core: AgentCore = Depends(get_agent_core),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> ChatTurnResponse:
    """Send a chat message with optional image attachments."""
    image_parts = await read_image_parts(files)
    svc = _build_service(db, agent_core, context_builder, memory_extractor)
    conversation, turn_response = await svc.send_message(
        profile,
        content,
        conversation_id=conversation_id,
        topic=topic,
        image_parts=image_parts or None,
    )

    background_tasks.add_task(
        memory_extractor.extract_and_store,
        profile_id=profile.id,
        messages=[
            {"role": "user", "content": content},
            {"role": "assistant", "content": turn_response.message.content},
        ],
        source=f"chat:{conversation.id}",
        category="general",
    )

    return turn_response


_stream_logger = logging.getLogger(__name__)

_SENTINEL = object()  # marks end of queue


@router.post("/stream")
async def send_message_stream(
    content: str = Form(...),
    conversation_id: UUID | None = Form(None),
    topic: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
    profile: Profile = Depends(get_verified_profile),
    agent_core: AgentCore = Depends(get_agent_core),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> StreamingResponse:
    """Send a chat message with SSE streaming response.

    Processing runs in a background task with its OWN db session, completely
    independent of the request lifecycle. If the client disconnects (app
    backgrounded), the task continues to completion — messages are always
    persisted. The client can GET the conversation later to see the result.
    """
    image_parts = await read_image_parts(files)
    profile_id = profile.id  # extract before request db session closes

    queue: asyncio.Queue[AgentEvent | object] = asyncio.Queue()

    async def _process():
        """Run the full pipeline with an independent db session."""
        done_data = None
        async with async_session_factory() as task_db:
            try:
                task_db.expire_on_commit = False
                svc = _build_service(task_db, agent_core, context_builder, memory_extractor)
                task_profile = await task_db.get(Profile, profile_id)
                if not task_profile:
                    return

                async for event in svc.send_message_stream(
                    task_profile,
                    content,
                    conversation_id=conversation_id,
                    topic=topic,
                    image_parts=image_parts or None,
                ):
                    queue.put_nowait(event)
                    if event.type == AgentEventType.DONE:
                        done_data = event.data
            except Exception:
                _stream_logger.exception("Stream processing failed")
                queue.put_nowait(
                    AgentEvent(type=AgentEventType.ERROR, data={"message": "Processing failed"})
                )
            finally:
                # Memory extraction (best-effort)
                if done_data and done_data.get("content"):
                    try:
                        await memory_extractor.extract_and_store(
                            profile_id=profile_id,
                            messages=[
                                {"role": "user", "content": content},
                                {"role": "assistant", "content": done_data["content"]},
                            ],
                            source=f"chat:{done_data.get('conversation_id', 'unknown')}",
                            category="general",
                        )
                    except Exception:
                        pass
                queue.put_nowait(_SENTINEL)

    # Task owns its own db session — survives request/client lifecycle
    asyncio.create_task(_process())

    async def event_generator():
        try:
            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    break
                event: AgentEvent = item  # type: ignore[assignment]
                payload = {"type": event.type.value, **event.data}
                yield f"data: {json.dumps(payload)}\n\n"
        except asyncio.CancelledError:
            # Client disconnected — task continues in background
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
