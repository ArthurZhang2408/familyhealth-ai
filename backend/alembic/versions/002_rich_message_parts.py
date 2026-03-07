"""rich message parts

Revision ID: 002
Revises: 001
Create Date: 2026-03-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "002"
down_revision: str = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- chat_messages: add content_parts + metadata columns --
    op.add_column("chat_messages", sa.Column("content_parts", postgresql.JSONB(), nullable=True))
    op.add_column("chat_messages", sa.Column("metadata", postgresql.JSONB(), nullable=True))

    # -- diagnosis_messages: add content_parts + metadata columns --
    op.add_column(
        "diagnosis_messages", sa.Column("content_parts", postgresql.JSONB(), nullable=True)
    )
    op.add_column("diagnosis_messages", sa.Column("metadata", postgresql.JSONB(), nullable=True))

    # -- Backfill existing rows: content → [{"type": "text", "text": content}] --
    op.execute(
        """
        UPDATE chat_messages
        SET content_parts = jsonb_build_array(jsonb_build_object('type', 'text', 'text', content))
        WHERE content_parts IS NULL
        """
    )
    op.execute(
        """
        UPDATE diagnosis_messages
        SET content_parts = jsonb_build_array(jsonb_build_object('type', 'text', 'text', content))
        WHERE content_parts IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("diagnosis_messages", "metadata")
    op.drop_column("diagnosis_messages", "content_parts")
    op.drop_column("chat_messages", "metadata")
    op.drop_column("chat_messages", "content_parts")
