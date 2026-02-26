from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_agent_core,
    get_context_builder,
    get_memory_extractor,
    get_verified_profile,
)
from app.core.config import settings
from app.core.database import get_db
from app.models.profile import Profile
from app.models.report import ReportAnalysis
from app.schemas.action_log import ActionType
from app.schemas.common import PaginatedResponse
from app.schemas.report import (
    ALLOWED_EXTENSIONS,
    ReportAnalysisResponse,
    ReportCreate,
)
from app.services.action_log import ActionLogService
from app.services.context_builder import ContextBuilder
from app.services.memory_extractor import MemoryExtractor
from app.services.report_analyzer import run_analysis_background
from app.services.report_prompts import REPORT_DISCLAIMER

router = APIRouter(prefix="/profiles/{pid}/reports", tags=["reports"])


def _add_disclaimer(report: ReportAnalysis) -> ReportAnalysisResponse:
    """Convert ORM model to response, injecting disclaimer when analysis exists."""
    resp = ReportAnalysisResponse.model_validate(report)
    if report.analysis_result is not None:
        resp.disclaimer = REPORT_DISCLAIMER
    return resp


def _get_extension(filename: str | None) -> str:
    """Extract lowercase file extension from filename."""
    if not filename:
        return ""
    dot_idx = filename.rfind(".")
    if dot_idx == -1:
        return ""
    return filename[dot_idx:].lower()


def _infer_file_type(filename: str | None) -> str:
    """Infer report file_type from extension."""
    ext = _get_extension(filename)
    if ext == ".pdf":
        return "lab_report"
    if ext in {".jpg", ".jpeg", ".png", ".webp"}:
        return "other"
    return "unknown"


# ---------------------------------------------------------------------------
# Upload (multipart file)
# ---------------------------------------------------------------------------


@router.post("/upload", response_model=ReportAnalysisResponse, status_code=201)
async def upload_report(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
    agent_core=Depends(get_agent_core),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> ReportAnalysisResponse:
    """Upload a medical report file and trigger analysis.

    Accepts PDF, JPEG, PNG, and WebP files up to 20 MB.
    Analysis runs in the background — poll GET /{rid} for results.
    """
    # Validate filename
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    # Validate extension
    ext = _get_extension(file.filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read and validate size
    file_bytes = await file.read()
    if len(file_bytes) > settings.max_report_file_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: "
            f"{settings.max_report_file_size // 1_048_576} MB.",
        )
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Create DB record
    report = ReportAnalysis(
        profile_id=profile.id,
        file_url=f"upload:{file.filename}",
        file_type=_infer_file_type(file.filename),
        original_filename=file.filename,
        status="pending",
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)

    # Log upload action (best-effort)
    try:
        log_svc = ActionLogService(db)
        await log_svc.log(
            profile_id=profile.id,
            account_id=profile.account_id,
            action_type=ActionType.REPORT_UPLOADED,
            payload={
                "report_id": str(report.id),
                "filename": file.filename,
                "file_size": len(file_bytes),
            },
        )
    except Exception:
        pass

    # Schedule background analysis
    background_tasks.add_task(
        run_analysis_background,
        report_id=report.id,
        profile_id=profile.id,
        file_bytes=file_bytes,
        agent_core=agent_core,
        context_builder=context_builder,
        memory_extractor=memory_extractor,
    )

    return _add_disclaimer(report)


# ---------------------------------------------------------------------------
# Create (JSON body — Supabase Storage URL flow)
# ---------------------------------------------------------------------------


@router.post("", response_model=ReportAnalysisResponse, status_code=201)
async def create_report(
    data: ReportCreate,
    background_tasks: BackgroundTasks,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
    agent_core=Depends(get_agent_core),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> ReportAnalysisResponse:
    """Create a report record from a Supabase Storage URL and trigger analysis.

    Analysis runs in the background — poll GET /{rid} for results.
    """
    report = ReportAnalysis(profile_id=profile.id, **data.model_dump())
    db.add(report)
    await db.flush()
    await db.refresh(report)

    # Schedule background analysis (file_bytes=None → service downloads from file_url)
    background_tasks.add_task(
        run_analysis_background,
        report_id=report.id,
        profile_id=profile.id,
        file_bytes=None,
        agent_core=agent_core,
        context_builder=context_builder,
        memory_extractor=memory_extractor,
    )

    return _add_disclaimer(report)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


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
        items=[_add_disclaimer(r) for r in reports],
        total=total,
        page=page,
        per_page=per_page,
    )


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


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
    return _add_disclaimer(report)


# ---------------------------------------------------------------------------
# Reanalyze
# ---------------------------------------------------------------------------


@router.post("/{rid}/reanalyze", response_model=ReportAnalysisResponse)
async def reanalyze_report(
    rid: UUID,
    background_tasks: BackgroundTasks,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
    agent_core=Depends(get_agent_core),
    context_builder: ContextBuilder = Depends(get_context_builder),
    memory_extractor: MemoryExtractor = Depends(get_memory_extractor),
) -> ReportAnalysisResponse:
    """Re-trigger analysis on an existing report."""
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

    # Schedule background analysis
    background_tasks.add_task(
        run_analysis_background,
        report_id=report.id,
        profile_id=profile.id,
        file_bytes=None,
        agent_core=agent_core,
        context_builder=context_builder,
        memory_extractor=memory_extractor,
    )

    return _add_disclaimer(report)
