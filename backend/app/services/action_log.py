from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_log import ActionLog
from app.schemas.action_log import ActionType


class ActionLogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log(
        self,
        profile_id: UUID,
        account_id: UUID,
        action_type: ActionType,
        payload: dict | None = None,
    ) -> ActionLog:
        """Append a single log entry."""
        entry = ActionLog(
            profile_id=profile_id,
            account_id=account_id,
            action_type=action_type.value,
            payload=payload or {},
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def list_for_profile(
        self,
        profile_id: UUID,
        page: int,
        per_page: int,
        action_type: ActionType | None = None,
    ) -> tuple[list[ActionLog], int]:
        """Return (entries, total_count) for a profile, newest first."""
        base = select(ActionLog).where(ActionLog.profile_id == profile_id)
        if action_type is not None:
            base = base.where(ActionLog.action_type == action_type.value)

        count_result = await self.db.execute(select(func.count()).select_from(base.subquery()))
        total = count_result.scalar_one()

        result = await self.db.execute(
            base.order_by(ActionLog.created_at.desc(), ActionLog.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(result.scalars().all()), total
