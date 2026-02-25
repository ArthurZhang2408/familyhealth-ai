from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_verified_profile
from app.core.database import get_db
from app.models.profile import Profile
from app.models.report import ReportAnalysis
from app.schemas.common import PaginatedResponse
from app.schemas.report import ReportAnalysisResponse, ReportCreate

router = APIRouter(prefix="/profiles/{pid}/reports", tags=["reports"])


@router.post("", response_model=ReportAnalysisResponse, status_code=201)
async def create_report(
    data: ReportCreate,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
) -> ReportAnalysisResponse:
    """Create a report analysis record. AI analysis will be triggered in a future release."""
    report = ReportAnalysis(profile_id=profile.id, **data.model_dump())
    db.add(report)
    await db.flush()
    await db.refresh(report)
    return ReportAnalysisResponse.model_validate(report)


@router.get("", response_model=PaginatedResponse[ReportAnalysisResponse])
async def list_reports(
    profile: Profile = Depends(get_verified_profile),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ReportAnalysisResponse]:
    """List all report analyses for the profile."""
    base_query = select(ReportAnalysis).where(ReportAnalysis.profile_id == profile.id)

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        base_query.offset((page - 1) * per_page)
        .limit(per_page)
        .order_by(ReportAnalysis.created_at.desc())
    )
    reports = result.scalars().all()

    return PaginatedResponse(
        items=[ReportAnalysisResponse.model_validate(r) for r in reports],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{rid}", response_model=ReportAnalysisResponse)
async def get_report(
    rid: UUID,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
) -> ReportAnalysisResponse:
    """Get specific analysis result."""
    result = await db.execute(
        select(ReportAnalysis).where(
            ReportAnalysis.id == rid, ReportAnalysis.profile_id == profile.id
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return ReportAnalysisResponse.model_validate(report)


@router.post("/{rid}/reanalyze", response_model=ReportAnalysisResponse)
async def reanalyze_report(
    rid: UUID,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
) -> ReportAnalysisResponse:
    """Re-trigger analysis on an existing report. AI analysis will be added in a future release."""
    result = await db.execute(
        select(ReportAnalysis).where(
            ReportAnalysis.id == rid, ReportAnalysis.profile_id == profile.id
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    report.status = "pending"
    report.analysis_result = None
    report.extracted_facts = []
    report.error_message = None
    await db.flush()
    await db.refresh(report)
    return ReportAnalysisResponse.model_validate(report)
