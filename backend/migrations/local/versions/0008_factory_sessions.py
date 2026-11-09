"""Persist Project-scoped Factory conversations without provider reasoning."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0008_factory_sessions"
down_revision: str | None = "local_0007_agent_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "factory_sessions",
        sa.Column("session_id", sa.Text(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("projects.project_id"),
            nullable=False,
        ),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("ready", sa.Integer(), nullable=False),
        sa.Column("next_prompt", sa.Text(), nullable=False),
        sa.Column("resource_plan_json", sa.Text(), nullable=False),
        sa.Column("blueprint_json", sa.Text(), nullable=True),
        sa.Column("diagnostics_json", sa.Text(), nullable=False),
        sa.Column("missing_capabilities_json", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_factory_sessions_project_updated",
        "factory_sessions",
        ["project_id", "updated_at"],
    )
    op.create_table(
        "factory_messages",
        sa.Column("message_id", sa.Text(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Text(),
            sa.ForeignKey("factory_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "session_id", "sequence", name="uq_factory_messages_session_sequence"
        ),
    )
    op.create_index(
        "ix_factory_messages_session_sequence",
        "factory_messages",
        ["session_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_factory_messages_session_sequence", table_name="factory_messages")
    op.drop_table("factory_messages")
    op.drop_index("ix_factory_sessions_project_updated", table_name="factory_sessions")
    op.drop_table("factory_sessions")
