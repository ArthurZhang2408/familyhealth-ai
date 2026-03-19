import asyncio
import json
import logging
import time
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)

from app.core.rate_limit import limiter
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.core import AgentCore
from app.agents.types import AgentEvent, AgentEventType
from app.api.deps import (
    get_agent_core,
    get_context_builder,
    get_memory_extractor,
    get_memory_service,
    get_verified_profile,
)
from app.api.upload_helpers import read_image_parts
from app.core.database import async_session_factory, get_db
from app.models.diagnosis import DiagnosisSession
from app.models.profile import Profile
from app.schemas.action_log import ActionType
from app.schemas.common import PaginatedResponse
from app.schemas.diagnosis import (
    DiagnosisSessionCreate,
    DiagnosisSessionDetailResponse,
    DiagnosisSessionRename,
    DiagnosisSessionResponse,
    DiagnosisSessionUpdate,
    DiagnosisTurnResponse,
)
from app.services.action_log import ActionLogService
from app.services.context_builder import ContextBuilder
from app.services.diagnosis import DiagnosisService
from app.services.memory import MemoryService
from app.services.memory_extractor import MemoryExtractor

router = APIRouter(prefix="/profiles/{pid}/diagnosis", tags=["diagnosis"])


def _build_service(
    db: AsyncSession,
    agent_core: AgentCore,
    context_builder: ContextBuilder,
    memory_extractor: MemoryExtractor,
) -> DiagnosisService:
    return DiagnosisService(
        db=db,
        agent_core=agent_core,
        context_builder=context_builder,
        memory_extractor=memory_extractor,
    )


@router.post("/create", response_model=DiagnosisSessionDetailResponse, status_code=201)
async def create_session_only(
    data: DiagnosisSessionCreate,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
    agent_core: AgentCore = Depends(get_agent_core),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> DiagnosisSessionDetailResponse:
    """Create a diagnosis session without generating an AI response.

    Used by the streaming flow: create → navigate → stream first message.
    """
    svc = _build_service(db, agent_core, context_builder, memory_extractor)
    session = await svc.create_session_only(profile, data.chief_complaint)
    return DiagnosisSessionDetailResponse.model_validate(session)


@router.post("", response_model=DiagnosisTurnResponse, status_code=201)
async def create_session(
    data: DiagnosisSessionCreate,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
    agent_core: AgentCore = Depends(get_agent_core),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> DiagnosisTurnResponse:
    """Start a new diagnosis session. Returns first AI response with assessment state."""
    svc = _build_service(db, agent_core, context_builder, memory_extractor)
    session, turn_response = await svc.create_session(profile, data.chief_complaint)

    # Memory extraction is handled by the service layer (consolidated
    # narrative on assessment delivery), not per-turn API-layer extraction.

    return turn_response


@router.get("", response_model=PaginatedResponse[DiagnosisSessionResponse])
async def list_sessions(
    profile: Profile = Depends(get_verified_profile),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[DiagnosisSessionResponse]:
    """List diagnosis sessions for the profile."""
    base_query = select(DiagnosisSession).where(DiagnosisSession.profile_id == profile.id)
    if status:
        base_query = base_query.where(DiagnosisSession.status == status)

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        base_query.offset((page - 1) * per_page)
        .limit(per_page)
        .order_by(DiagnosisSession.created_at.desc())
    )
    sessions = result.scalars().all()

    return PaginatedResponse(
        items=[DiagnosisSessionResponse.model_validate(s) for s in sessions],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{sid}", response_model=DiagnosisSessionDetailResponse)
async def get_session(
    sid: UUID,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
) -> DiagnosisSessionDetailResponse:
    """Get session details with full message history."""
    result = await db.execute(
        select(DiagnosisSession).where(
            DiagnosisSession.id == sid,
            DiagnosisSession.profile_id == profile.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Diagnosis session not found")
    return DiagnosisSessionDetailResponse.model_validate(session)


@router.post("/{sid}/messages", response_model=DiagnosisTurnResponse, status_code=201)
async def send_message(
    sid: UUID,
    content: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
    agent_core: AgentCore = Depends(get_agent_core),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> DiagnosisTurnResponse:
    """Send a message with optional image attachments in a diagnosis session."""
    image_parts = await read_image_parts(files)
    svc = _build_service(db, agent_core, context_builder, memory_extractor)
    session = await svc.get_session(sid, profile.id)
    if not session:
        raise HTTPException(status_code=404, detail="Diagnosis session not found")

    turn_response = await svc.send_message(
        session, profile, content, image_parts=image_parts or None
    )

    # Memory extraction is handled by the service layer (consolidated
    # narrative on assessment delivery), not per-turn API-layer extraction.

    return turn_response


_diag_stream_logger = logging.getLogger(__name__)

_DIAG_SENTINEL = object()


@router.post("/stream")
@limiter.limit("20/minute")
async def stream_diagnosis(
    request: Request,
    content: str = Form(...),
    session_id: UUID | None = Form(None),
    chief_complaint: str | None = Form(None),
    structured_response: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
    profile: Profile = Depends(get_verified_profile),
    agent_core: AgentCore = Depends(get_agent_core),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> StreamingResponse:
    """Send a diagnosis message with SSE streaming response.

    Mirrors the chat /stream endpoint: optional session_id creates a new
    session on the fly. Processing runs in a background task with its own
    db session — survives client disconnect.
    """
    image_parts = await read_image_parts(files)
    profile_id = profile.id
    parsed_structured_response: dict | None = None
    if structured_response:
        try:
            parsed_structured_response = json.loads(structured_response)
        except (json.JSONDecodeError, TypeError):
            _diag_stream_logger.warning(
                "Invalid structured_response JSON: %s", structured_response
            )

    queue: asyncio.Queue = asyncio.Queue()

    async def _process():
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
                    session_id=session_id,
                    chief_complaint=chief_complaint,
                    image_parts=image_parts or None,
                    structured_response=parsed_structured_response,
                ):
                    queue.put_nowait(event)
                    if event.type == AgentEventType.DONE:
                        done_data = event.data
            except Exception:
                _diag_stream_logger.exception("Diagnosis stream processing failed")
                queue.put_nowait(
                    AgentEvent(type=AgentEventType.ERROR, data={"message": "Processing failed"})
                )
            finally:
                # Memory extraction is handled by the service layer
                # (consolidated narrative on assessment delivery).
                queue.put_nowait(_DIAG_SENTINEL)

    asyncio.create_task(_process())

    async def event_generator():
        stream_start = time.monotonic()
        events_sent = 0
        client_disconnected = False
        last_event_type = None
        try:
            while True:
                item = await queue.get()
                if item is _DIAG_SENTINEL:
                    break
                last_event_type = item.type.value
                payload = {"type": item.type.value, **item.data}
                yield f"data: {json.dumps(payload)}\n\n"
                events_sent += 1
        except asyncio.CancelledError:
            client_disconnected = True
        finally:
            elapsed = int((time.monotonic() - stream_start) * 1000)
            if client_disconnected:
                _diag_stream_logger.warning(
                    "SSE client disconnected after %dms (%d events sent, last=%s)",
                    elapsed,
                    events_sent,
                    last_event_type,
                )
            else:
                _diag_stream_logger.info(
                    "SSE stream completed in %dms (%d events sent)",
                    elapsed,
                    events_sent,
                )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{sid}/messages/stream")
@limiter.limit("20/minute")
async def send_message_stream(
    request: Request,
    sid: UUID,
    content: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    profile: Profile = Depends(get_verified_profile),
    agent_core: AgentCore = Depends(get_agent_core),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> StreamingResponse:
    """Legacy per-session stream endpoint. Delegates to /stream."""
    image_parts = await read_image_parts(files)
    profile_id = profile.id

    queue: asyncio.Queue = asyncio.Queue()

    async def _process():
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
                    session_id=sid,
                    image_parts=image_parts or None,
                ):
                    queue.put_nowait(event)
                    if event.type == AgentEventType.DONE:
                        done_data = event.data
            except Exception:
                _diag_stream_logger.exception("Diagnosis stream processing failed")
                queue.put_nowait(
                    AgentEvent(type=AgentEventType.ERROR, data={"message": "Processing failed"})
                )
            finally:
                # Memory extraction is handled by the service layer
                # (consolidated narrative on assessment delivery).
                queue.put_nowait(_DIAG_SENTINEL)

    asyncio.create_task(_process())

    async def event_generator():
        stream_start = time.monotonic()
        events_sent = 0
        client_disconnected = False
        last_event_type = None
        try:
            while True:
                item = await queue.get()
                if item is _DIAG_SENTINEL:
                    break
                last_event_type = item.type.value
                payload = {"type": item.type.value, **item.data}
                yield f"data: {json.dumps(payload)}\n\n"
                events_sent += 1
        except asyncio.CancelledError:
            client_disconnected = True
        finally:
            elapsed = int((time.monotonic() - stream_start) * 1000)
            if client_disconnected:
                _diag_stream_logger.warning(
                    "SSE client disconnected after %dms (%d events sent, last=%s, session=%s)",
                    elapsed,
                    events_sent,
                    last_event_type,
                    sid,
                )
            else:
                _diag_stream_logger.info(
                    "SSE stream completed in %dms (%d events sent, session=%s)",
                    elapsed,
                    events_sent,
                    sid,
                )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.patch("/{sid}", response_model=DiagnosisSessionResponse)
async def update_session(
    sid: UUID,
    data: DiagnosisSessionUpdate,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
    agent_core: AgentCore = Depends(get_agent_core),  # singletons; needed for close_session
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> DiagnosisSessionResponse:
    """Update session: close/resolve, add resolution notes."""
    svc = _build_service(db, agent_core, context_builder, memory_extractor)
    session = await svc.get_session(sid, profile.id)
    if not session:
        raise HTTPException(status_code=404, detail="Diagnosis session not found")

    if data.status == "resolved":
        session = await svc.close_session(session, profile, data.resolution_notes)
    elif data.status == "abandoned":
        session.status = "abandoned"
        session.resolved_at = func.now()
        if data.resolution_notes:
            session.resolution_notes = data.resolution_notes
        await db.flush()
    else:
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(session, field, value)
        await db.flush()

    await db.refresh(session)
    return DiagnosisSessionResponse.model_validate(session)


@router.patch("/{sid}/rename", response_model=DiagnosisSessionResponse)
async def rename_session(
    sid: UUID,
    data: DiagnosisSessionRename,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
) -> DiagnosisSessionResponse:
    """Rename a diagnosis session (update title only)."""
    result = await db.execute(
        select(DiagnosisSession).where(
            DiagnosisSession.id == sid,
            DiagnosisSession.profile_id == profile.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Diagnosis session not found")

    session.title = data.title
    await db.flush()
    await db.refresh(session)
    return DiagnosisSessionResponse.model_validate(session)


@router.delete("/{sid}", status_code=204)
async def delete_session(
    sid: UUID,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
    memory_service: MemoryService = Depends(get_memory_service),
) -> None:
    """Delete a diagnosis session and its associated memories.

    Hard-deletes the session record (messages cascade via FK).
    Also deletes any Mem0 memories extracted from this session.
    """
    result = await db.execute(
        select(DiagnosisSession).where(
            DiagnosisSession.id == sid,
            DiagnosisSession.profile_id == profile.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Diagnosis session not found")

    chief_complaint = session.chief_complaint
    await db.delete(session)

    # Delete memories extracted from this session (best-effort).
    # Agent saves use :agent suffix, narrative uses :narrative suffix.
    # Also clean up legacy format (no suffix) from pre-agent-driven sessions.
    memories_deleted = 0
    try:
        memories_deleted += await memory_service.delete_by_source(
            profile.id, f"diagnosis:{sid}:narrative"
        )
        memories_deleted += await memory_service.delete_by_source(
            profile.id, f"diagnosis:{sid}:agent"
        )
        memories_deleted += await memory_service.delete_by_source(
            profile.id, f"diagnosis:{sid}"
        )
    except Exception:
        _diag_stream_logger.warning(
            "Failed to delete memories for diagnosis %s, session deleted anyway", sid
        )

    # Log the deletion
    try:
        log_svc = ActionLogService(db)
        await log_svc.log(
            profile_id=profile.id,
            account_id=profile.account_id,
            action_type=ActionType.DIAGNOSIS_DELETED,
            payload={
                "session_id": str(sid),
                "chief_complaint": chief_complaint,
                "memories_deleted": memories_deleted,
            },
        )
    except Exception:
        _diag_stream_logger.warning("Action logging failed for diagnosis deletion %s", sid)
