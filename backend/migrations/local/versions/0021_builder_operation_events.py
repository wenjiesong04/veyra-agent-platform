"""Persist bounded Builder operation events and Factory candidate identity."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0021_builder_operation_events"
down_revision: str | None = "local_0020_builder_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "builder_operation_events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column(
            "operation_id",
            sa.Text(),
            sa.ForeignKey("builder_operations.operation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("facts_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "operation_id",
            "sequence",
            name="uq_builder_operation_events_sequence",
        ),
    )
    op.create_index(
        "ix_builder_operation_events_operation",
        "builder_operation_events",
        ["operation_id", "sequence"],
    )
    op.add_column(
        "factory_sessions",
        sa.Column("identity_json", sa.Text(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("factory_sessions", "identity_json")
    op.drop_index(
        "ix_builder_operation_events_operation",
        table_name="builder_operation_events",
    )
    op.drop_table("builder_operation_events")
