import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship as sa_relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Profile(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "profiles"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    relationship: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    sex: Mapped[str | None] = mapped_column(String(10))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    blood_type: Mapped[str | None] = mapped_column(String(3))
    allergies: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    current_medications: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    medical_conditions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    family_medical_history: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    emergency_contacts: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships — lazy="raise" prevents accidental eager loading;
    # use .options(selectinload(...)) on queries that need them.
    diagnosis_sessions = sa_relationship(
        "DiagnosisSession", back_populates="profile", lazy="raise"
    )
    report_analyses = sa_relationship("ReportAnalysis", back_populates="profile", lazy="raise")
    chat_conversations = sa_relationship(
        "ChatConversation", back_populates="profile", lazy="raise"
    )

    __table_args__ = (
        Index("idx_profiles_account", "account_id", postgresql_where=(deleted_at.is_(None))),
        Index("idx_profiles_allergies", "allergies", postgresql_using="gin"),
        Index("idx_profiles_conditions", "medical_conditions", postgresql_using="gin"),
    )
