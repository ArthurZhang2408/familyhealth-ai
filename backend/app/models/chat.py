import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class ChatConversation(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "chat_conversations"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    topic: Mapped[str | None] = mapped_column(Text)

    # Relationships
    profile = relationship("Profile", back_populates="chat_conversations")
    messages = relationship(
        "ChatMessage",
        back_populates="conversation",
        lazy="selectin",
        order_by="ChatMessage.created_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (Index("idx_chat_convos_profile", "profile_id", "updated_at"),)


class ChatMessage(UUIDPrimaryKey, Base):
    __tablename__ = "chat_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_parts: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    conversation = relationship("ChatConversation", back_populates="messages")

    __table_args__ = (Index("idx_chat_msgs_convo", "conversation_id", "created_at"),)
