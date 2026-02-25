from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatConversation


class ChatService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_recent_conversations(
        self, profile_id: UUID, limit: int = 10
    ) -> list[ChatConversation]:
        result = await self.db.execute(
            select(ChatConversation)
            .where(ChatConversation.profile_id == profile_id)
            .order_by(ChatConversation.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
