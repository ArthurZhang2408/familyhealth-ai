"""add title to diagnosis_sessions

Revision ID: 004
Revises: 003
Create Date: 2026-03-09

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004"
down_revision: str = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("diagnosis_sessions", sa.Column("title", sa.Text(), nullable=True))
    # Backfill title from chief_complaint for existing rows
    op.execute("UPDATE diagnosis_sessions SET title = chief_complaint WHERE title IS NULL")


def downgrade() -> None:
    op.drop_column("diagnosis_sessions", "title")
