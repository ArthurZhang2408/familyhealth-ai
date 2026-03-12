"""LLM trace model for recording every LLM call with full request/response detail."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LLMTrace(Base):
    """Append-only log of every LLM call for debugging and evaluation.

    One row per LLM provider call. Linked to chat/diagnosis sessions
    via session_id (no FK to avoid cross-table coupling).
    """

    __tablename__ = "llm_traces"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_type: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # chat, diagnosis, report, standalone
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    turn_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    round_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)  # cerebras, gemini, qwen
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    task: Mapped[str] = mapped_column(Text, nullable=False)  # LLMTask value
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    messages_in: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_tool_calls: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_llm_traces_session", "session_id", "created_at"),
        Index("idx_llm_traces_type", "session_type", "created_at"),
    )
