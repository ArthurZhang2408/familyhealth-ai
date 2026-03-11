"""add onboarding fields to profiles

Revision ID: 005
Revises: 004
Create Date: 2026-03-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "005"
down_revision: str = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("height_cm", sa.Float(), nullable=True))
    op.add_column("profiles", sa.Column("weight_kg", sa.Float(), nullable=True))
    op.add_column("profiles", sa.Column("smoking_status", sa.String(10), nullable=True))
    op.add_column("profiles", sa.Column("alcohol_frequency", sa.String(15), nullable=True))
    op.add_column("profiles", sa.Column("is_pregnant", sa.Boolean(), nullable=True))
    op.add_column(
        "profiles",
        sa.Column("surgical_history", JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("profiles", "surgical_history")
    op.drop_column("profiles", "is_pregnant")
    op.drop_column("profiles", "alcohol_frequency")
    op.drop_column("profiles", "smoking_status")
    op.drop_column("profiles", "weight_kg")
    op.drop_column("profiles", "height_cm")
