"""Memory trace model for recording memory extraction and retrieval events."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MemoryTrace(Base):
    """Append-only log of memory system events for debugging and evaluation.

    Records two event types:
    - ``retrieval``: memories fetched before an agent turn (query, results, scores)
    - ``extraction``: facts extracted after a session (input, facts, Mem0 decisions)
    """

    __tablename__ = "memory_traces"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    session_type: Mapped[str] = mapped_column(Text, nullable=False)  # diagnosis, chat
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)  # retrieval, extraction
    turn_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_memory_traces_session", "session_id", "created_at"),
        Index("idx_memory_traces_profile", "profile_id", "created_at"),
    )
