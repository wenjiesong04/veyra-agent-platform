"""Persist Project-scoped Builder conversations outside Runtime and Factory."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0020_builder_conversations"
down_revision: str | None = "local_0019_edit_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "builder_conversations",
        sa.Column("conversation_id", sa.Text(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("projects.project_id"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("last_activity_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_builder_conversations_project_activity",
        "builder_conversations",
        ["project_id", "last_activity_at"],
    )
    op.create_table(
        "builder_operations",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Text(),
            sa.ForeignKey("builder_conversations.conversation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "retry_of",
            sa.Text(),
            sa.ForeignKey("builder_operations.operation_id"),
            nullable=True,
        ),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("diagnostic_json", sa.Text(), nullable=False),
        sa.Column("proposal_id", sa.Text(), nullable=True),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("factory_session_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_builder_operations_conversation",
        "builder_operations",
        ["conversation_id", "created_at"],
    )
    op.create_table(
        "builder_messages",
        sa.Column("message_id", sa.Text(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Text(),
            sa.ForeignKey("builder_conversations.conversation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "operation_id",
            sa.Text(),
            sa.ForeignKey("builder_operations.operation_id"),
            nullable=True,
        ),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence",
            name="uq_builder_messages_sequence",
        ),
    )
    op.create_index(
        "ix_builder_messages_conversation_sequence",
        "builder_messages",
        ["conversation_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_builder_messages_conversation_sequence", table_name="builder_messages"
    )
    op.drop_table("builder_messages")
    op.drop_index("ix_builder_operations_conversation", table_name="builder_operations")
    op.drop_table("builder_operations")
    op.drop_index(
        "ix_builder_conversations_project_activity",
        table_name="builder_conversations",
    )
    op.drop_table("builder_conversations")
