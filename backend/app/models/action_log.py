import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ActionLog(Base):
    __tablename__ = "action_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_action_log_profile", "profile_id", "created_at"),
        Index("idx_action_log_type", "action_type", "created_at"),
    )
