from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.diagnosis import DiagnosisSession


class DiagnosisService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_active_sessions(self, profile_id: UUID) -> list[DiagnosisSession]:
        result = await self.db.execute(
            select(DiagnosisSession).where(
                DiagnosisSession.profile_id == profile_id,
                DiagnosisSession.status == "active",
            )
        )
        return list(result.scalars().all())
