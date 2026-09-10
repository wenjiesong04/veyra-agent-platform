"""Persist local Agent conversations separately from Project source."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0015_agent_conversations"
down_revision: str | None = "local_0014_workflow_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_conversations",
        sa.Column("conversation_id", sa.Text(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("projects.project_id"),
            nullable=False,
        ),
        sa.Column(
            "agent_id", sa.Text(), sa.ForeignKey("agents.agent_id"), nullable=False
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_agent_conversations_agent_updated",
        "agent_conversations",
        ["project_id", "agent_id", "updated_at"],
    )
    op.create_table(
        "agent_conversation_messages",
        sa.Column("message_id", sa.Text(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Text(),
            sa.ForeignKey("agent_conversations.conversation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence",
            name="uq_agent_conversation_messages_sequence",
        ),
    )
    op.create_index(
        "ix_agent_conversation_messages_conversation_sequence",
        "agent_conversation_messages",
        ["conversation_id", "sequence"],
    )
    op.add_column(
        "runtime_runs", sa.Column("conversation_id", sa.Text(), nullable=True)
    )
    op.create_index("ix_runtime_runs_conversation", "runtime_runs", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_runtime_runs_conversation", table_name="runtime_runs")
    op.drop_column("runtime_runs", "conversation_id")
    op.drop_index(
        "ix_agent_conversation_messages_conversation_sequence",
        table_name="agent_conversation_messages",
    )
    op.drop_table("agent_conversation_messages")
    op.drop_index(
        "ix_agent_conversations_agent_updated", table_name="agent_conversations"
    )
    op.drop_table("agent_conversations")
