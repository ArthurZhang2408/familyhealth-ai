from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_context_builder,
    get_llm_router,
    get_memory_extractor,
    get_verified_profile,
)
from app.core.database import get_db
from app.models.profile import Profile
from app.schemas.common import PaginatedResponse
from app.schemas.diagnosis import (
    DiagnosisMessageCreate,
    DiagnosisSessionCreate,
    DiagnosisSessionDetailResponse,
    DiagnosisSessionResponse,
    DiagnosisSessionUpdate,
    DiagnosisTurnResponse,
)
from app.services.context_builder import ContextBuilder
from app.services.diagnosis import DiagnosisService
from app.services.llm import LLMRouter
from app.services.memory_extractor import MemoryExtractor

router = APIRouter(prefix="/profiles/{pid}/diagnosis", tags=["diagnosis"])


def _build_service(
    db: AsyncSession,
    llm_router: LLMRouter,
    context_builder: ContextBuilder,
    memory_extractor: MemoryExtractor,
) -> DiagnosisService:
    return DiagnosisService(
        db=db,
        llm_router=llm_router,
        context_builder=context_builder,
        memory_extractor=memory_extractor,
    )


@router.post("", response_model=DiagnosisTurnResponse, status_code=201)
async def create_session(
    data: DiagnosisSessionCreate,
    background_tasks: BackgroundTasks,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> DiagnosisTurnResponse:
    """Start a new diagnosis session. Returns first AI response with assessment state."""
    svc = _build_service(db, llm_router, context_builder, memory_extractor)
    session, turn_response = await svc.create_session(profile, data.chief_complaint)
    await db.commit()

    # Background memory extraction
    background_tasks.add_task(
        svc.extract_memories_background,
        profile_id=profile.id,
        user_content=data.chief_complaint,
        assistant_content=turn_response.message.content,
        session_id=session.id,
    )

    return turn_response


@router.get("", response_model=PaginatedResponse[DiagnosisSessionResponse])
async def list_sessions(
    profile: Profile = Depends(get_verified_profile),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> PaginatedResponse[DiagnosisSessionResponse]:
    """List diagnosis sessions for the profile."""
    svc = _build_service(db, llm_router, context_builder, memory_extractor)
    return await svc.list_sessions(profile.id, status, page, per_page)


@router.get("/{sid}", response_model=DiagnosisSessionDetailResponse)
async def get_session(
    sid: UUID,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> DiagnosisSessionDetailResponse:
    """Get session details with full message history."""
    svc = _build_service(db, llm_router, context_builder, memory_extractor)
    session = await svc.get_session(sid, profile.id)
    if not session:
        raise HTTPException(status_code=404, detail="Diagnosis session not found")
    return DiagnosisSessionDetailResponse.model_validate(session)


@router.post("/{sid}/messages", response_model=DiagnosisTurnResponse, status_code=201)
async def send_message(
    sid: UUID,
    data: DiagnosisMessageCreate,
    background_tasks: BackgroundTasks,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> DiagnosisTurnResponse:
    """Send a message in a diagnosis session. Returns AI response with assessment state."""
    svc = _build_service(db, llm_router, context_builder, memory_extractor)
    session = await svc.get_session(sid, profile.id)
    if not session:
        raise HTTPException(status_code=404, detail="Diagnosis session not found")

    turn_response = await svc.send_message(session, profile, data.content)
    await db.commit()

    # Background memory extraction
    background_tasks.add_task(
        svc.extract_memories_background,
        profile_id=profile.id,
        user_content=data.content,
        assistant_content=turn_response.message.content,
        session_id=session.id,
    )

    return turn_response


@router.patch("/{sid}", response_model=DiagnosisSessionResponse)
async def update_session(
    sid: UUID,
    data: DiagnosisSessionUpdate,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> DiagnosisSessionResponse:
    """Update session: close/resolve, add resolution notes."""
    svc = _build_service(db, llm_router, context_builder, memory_extractor)
    session = await svc.get_session(sid, profile.id)
    if not session:
        raise HTTPException(status_code=404, detail="Diagnosis session not found")

    if data.status == "resolved":
        session = await svc.close_session(session, profile, data.resolution_notes)
    elif data.status == "abandoned":
        from sqlalchemy import func

        session.status = "abandoned"
        session.resolved_at = func.now()
        if data.resolution_notes:
            session.resolution_notes = data.resolution_notes
        await db.flush()
    else:
        # Generic field update
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(session, field, value)
        await db.flush()

    await db.commit()
    await db.refresh(session)
    return DiagnosisSessionResponse.model_validate(session)
