import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class DiagnosisSession(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "diagnosis_sessions"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    chief_complaint: Mapped[str | None] = mapped_column(Text)
    differential_diagnoses: Mapped[list] = mapped_column(JSONB, server_default="[]")
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    profile = relationship("Profile", back_populates="diagnosis_sessions")
    messages = relationship(
        "DiagnosisMessage",
        back_populates="session",
        lazy="selectin",
        order_by="DiagnosisMessage.created_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("idx_diag_sessions_profile", "profile_id"),
        Index("idx_diag_sessions_status", "profile_id", "status"),
    )


class DiagnosisMessage(UUIDPrimaryKey, Base):
    __tablename__ = "diagnosis_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("diagnosis_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    content_parts: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    session = relationship("DiagnosisSession", back_populates="messages")

    __table_args__ = (Index("idx_diag_msgs_session", "session_id", "created_at"),)
