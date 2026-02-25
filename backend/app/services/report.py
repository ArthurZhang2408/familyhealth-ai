from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report import ReportAnalysis


class ReportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_pending_reports(self, profile_id: UUID) -> list[ReportAnalysis]:
        result = await self.db.execute(
            select(ReportAnalysis).where(
                ReportAnalysis.profile_id == profile_id,
                ReportAnalysis.status == "pending",
            )
        )
        return list(result.scalars().all())
