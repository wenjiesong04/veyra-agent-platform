"""Persist account-owned Conversations, Messages, and Builder references."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "community_0013_conversations"
down_revision: str | None = "community_0012_cloud_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["community_users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["cloud_projects.project_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index(
        "ix_conversations_owner_activity",
        "conversations",
        ["owner_user_id", "last_activity_at"],
    )
    op.create_index(
        "ix_conversations_owner_project_activity",
        "conversations",
        ["owner_user_id", "project_id", "last_activity_at"],
    )

    op.create_table(
        "conversation_operations",
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("retry_of", sa.String(length=36), nullable=True),
        sa.Column("proposal_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("factory_session_id", sa.String(length=36), nullable=True),
        sa.Column("diagnostic_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.conversation_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["retry_of"], ["conversation_operations.operation_id"]),
        sa.PrimaryKeyConstraint("operation_id"),
    )
    op.create_index(
        "ix_conversation_operations_conversation_created",
        "conversation_operations",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "conversation_messages",
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("operation_id", sa.String(length=36), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("attachments_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.conversation_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["conversation_operations.operation_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("message_id"),
        sa.UniqueConstraint("conversation_id", "sequence"),
    )
    op.create_index(
        "ix_conversation_messages_conversation_sequence",
        "conversation_messages",
        ["conversation_id", "sequence"],
    )
    op.create_index(
        "ix_conversation_messages_conversation_created",
        "conversation_messages",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "conversation_operation_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("facts_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["conversation_operations.operation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("operation_id", "sequence"),
    )
    op.create_index(
        "ix_conversation_operation_events_operation_sequence",
        "conversation_operation_events",
        ["operation_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_operation_events_operation_sequence",
        table_name="conversation_operation_events",
    )
    op.drop_table("conversation_operation_events")
    op.drop_index(
        "ix_conversation_messages_conversation_created",
        table_name="conversation_messages",
    )
    op.drop_index(
        "ix_conversation_messages_conversation_sequence",
        table_name="conversation_messages",
    )
    op.drop_table("conversation_messages")
    op.drop_index(
        "ix_conversation_operations_conversation_created",
        table_name="conversation_operations",
    )
    op.drop_table("conversation_operations")
    op.drop_index("ix_conversations_owner_project_activity", table_name="conversations")
    op.drop_index("ix_conversations_owner_activity", table_name="conversations")
    op.drop_table("conversations")
