import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class ReportAnalysis(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "report_analyses"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unknown")
    original_filename: Mapped[str | None] = mapped_column(Text)
    analysis_result: Mapped[dict | None] = mapped_column(JSONB)
    extracted_facts: Mapped[list] = mapped_column(JSONB, server_default="[]")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)

    # Relationships
    profile = relationship("Profile", back_populates="report_analyses")

    __table_args__ = (
        Index("idx_reports_profile", "profile_id"),
        Index("idx_reports_status", "profile_id", "status"),
    )
