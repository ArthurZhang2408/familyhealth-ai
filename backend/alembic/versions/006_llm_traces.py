"""llm traces

Revision ID: 006
Revises: 005
Create Date: 2026-03-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "006"
down_revision: str = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_traces",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("session_type", sa.Text(), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("turn_index", sa.Integer(), nullable=True),
        sa.Column("round_index", sa.Integer(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("messages_in", postgresql.JSONB(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("response_tool_calls", postgresql.JSONB(), nullable=True),
        sa.Column("finish_reason", sa.Text(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_llm_traces_session", "llm_traces", ["session_id", "created_at"])
    op.create_index("idx_llm_traces_type", "llm_traces", ["session_type", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_llm_traces_type")
    op.drop_index("idx_llm_traces_session")
    op.drop_table("llm_traces")
