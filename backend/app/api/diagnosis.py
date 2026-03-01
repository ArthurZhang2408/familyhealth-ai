from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
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
from app.models.diagnosis import DiagnosisSession
from app.models.profile import Profile
from app.schemas.common import PaginatedResponse
from app.api.upload_helpers import read_image_parts
from app.schemas.diagnosis import (
    DiagnosisSessionCreate,
    DiagnosisSessionDetailResponse,
    DiagnosisSessionResponse,
    DiagnosisSessionUpdate,
    DiagnosisTurnResponse,
)
from app.services.context_builder import ContextBuilder
from app.services.diagnosis import DiagnosisService
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


@router.post("", response_model=DiagnosisTurnResponse, status_code=201)
async def create_session(
    data: DiagnosisSessionCreate,
    background_tasks: BackgroundTasks,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
    agent_core: AgentCore = Depends(get_agent_core),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> DiagnosisTurnResponse:
    """Start a new diagnosis session. Returns first AI response with assessment state."""
    svc = _build_service(db, agent_core, context_builder, memory_extractor)
    session, turn_response = await svc.create_session(profile, data.chief_complaint)

    background_tasks.add_task(
        memory_extractor.extract_and_store,
        profile_id=profile.id,
        messages=[
            {"role": "user", "content": data.chief_complaint},
            {"role": "assistant", "content": turn_response.message.content},
        ],
        source=f"diagnosis:{session.id}",
        category="diagnoses",
    )

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
    background_tasks: BackgroundTasks,
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

    background_tasks.add_task(
        memory_extractor.extract_and_store,
        profile_id=profile.id,
        messages=[
            {"role": "user", "content": content},
            {"role": "assistant", "content": turn_response.message.content},
        ],
        source=f"diagnosis:{session.id}",
        category="diagnoses",
    )

    return turn_response


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
