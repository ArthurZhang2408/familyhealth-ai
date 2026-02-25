"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-02-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- profiles --
    op.create_table(
        "profiles",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("relationship", sa.String(20), nullable=False),
        sa.Column("sex", sa.String(10), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("blood_type", sa.String(3), nullable=True),
        sa.Column("allergies", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("current_medications", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("medical_conditions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "family_medical_history", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("emergency_contacts", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_profiles_account",
        "profiles",
        ["account_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_profiles_allergies", "profiles", ["allergies"], postgresql_using="gin")
    op.create_index(
        "idx_profiles_conditions", "profiles", ["medical_conditions"], postgresql_using="gin"
    )

    # -- diagnosis_sessions --
    op.create_table(
        "diagnosis_sessions",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("chief_complaint", sa.Text(), nullable=True),
        sa.Column("differential_diagnoses", postgresql.JSONB(), server_default="[]"),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_diag_sessions_profile", "diagnosis_sessions", ["profile_id"])
    op.create_index("idx_diag_sessions_status", "diagnosis_sessions", ["profile_id", "status"])

    # -- diagnosis_messages --
    op.create_table(
        "diagnosis_messages",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["session_id"], ["diagnosis_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_diag_msgs_session", "diagnosis_messages", ["session_id", "created_at"])

    # -- report_analyses --
    op.create_table(
        "report_analyses",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("original_filename", sa.Text(), nullable=True),
        sa.Column("analysis_result", postgresql.JSONB(), nullable=True),
        sa.Column("extracted_facts", postgresql.JSONB(), server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_reports_profile", "report_analyses", ["profile_id"])
    op.create_index("idx_reports_status", "report_analyses", ["profile_id", "status"])

    # -- chat_conversations --
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_chat_convos_profile", "chat_conversations", ["profile_id", "updated_at"])

    # -- chat_messages --
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["chat_conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_chat_msgs_convo", "chat_messages", ["conversation_id", "created_at"])

    # -- action_log (append-only) --
    op.create_table(
        "action_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_action_log_profile", "action_log", ["profile_id", "created_at"])
    op.create_index("idx_action_log_type", "action_log", ["action_type", "created_at"])


def downgrade() -> None:
    op.drop_table("action_log")
    op.drop_table("chat_messages")
    op.drop_table("chat_conversations")
    op.drop_table("report_analyses")
    op.drop_table("diagnosis_messages")
    op.drop_table("diagnosis_sessions")
    op.drop_table("profiles")
