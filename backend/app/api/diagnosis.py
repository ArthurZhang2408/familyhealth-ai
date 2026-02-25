from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_verified_profile
from app.core.database import get_db
from app.models.diagnosis import DiagnosisMessage, DiagnosisSession
from app.models.profile import Profile
from app.schemas.common import PaginatedResponse
from app.schemas.diagnosis import (
    DiagnosisMessageCreate,
    DiagnosisMessageResponse,
    DiagnosisSessionCreate,
    DiagnosisSessionDetailResponse,
    DiagnosisSessionResponse,
    DiagnosisSessionUpdate,
)

router = APIRouter(prefix="/profiles/{pid}/diagnosis", tags=["diagnosis"])


@router.post("", response_model=DiagnosisSessionResponse, status_code=201)
async def create_session(
    data: DiagnosisSessionCreate,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
) -> DiagnosisSessionResponse:
    """Start a new diagnosis session."""
    session = DiagnosisSession(profile_id=profile.id, chief_complaint=data.chief_complaint)
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return DiagnosisSessionResponse.model_validate(session)


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
            DiagnosisSession.id == sid, DiagnosisSession.profile_id == profile.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Diagnosis session not found")
    return DiagnosisSessionDetailResponse.model_validate(session)


@router.post("/{sid}/messages", response_model=DiagnosisMessageResponse, status_code=201)
async def send_message(
    sid: UUID,
    data: DiagnosisMessageCreate,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
) -> DiagnosisMessageResponse:
    """Send a message in a diagnosis session. AI response will be added in a future release."""
    result = await db.execute(
        select(DiagnosisSession).where(
            DiagnosisSession.id == sid, DiagnosisSession.profile_id == profile.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Diagnosis session not found")
    if session.status != "active":
        raise HTTPException(status_code=400, detail="Session is not active")

    message = DiagnosisMessage(session_id=sid, role="user", content=data.content)
    db.add(message)
    await db.flush()
    await db.refresh(message)
    return DiagnosisMessageResponse.model_validate(message)


@router.patch("/{sid}", response_model=DiagnosisSessionResponse)
async def update_session(
    sid: UUID,
    data: DiagnosisSessionUpdate,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
) -> DiagnosisSessionResponse:
    """Update session: close/resolve, add resolution notes."""
    result = await db.execute(
        select(DiagnosisSession).where(
            DiagnosisSession.id == sid, DiagnosisSession.profile_id == profile.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Diagnosis session not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(session, field, value)
    if data.status in ("resolved", "abandoned"):
        session.resolved_at = func.now()
    await db.flush()
    await db.refresh(session)
    return DiagnosisSessionResponse.model_validate(session)
