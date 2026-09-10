"""Persist WorkItem leases and classified local execution attempts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0016_orchestrator_leases"
down_revision: str | None = "local_0015_agent_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "work_items",
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("work_items", sa.Column("lease_token", sa.Text(), nullable=True))
    op.add_column("work_items", sa.Column("lease_expires_at", sa.Text(), nullable=True))
    op.add_column("work_items", sa.Column("failure_class", sa.Text(), nullable=True))
    op.create_table(
        "work_item_attempts",
        sa.Column("attempt_id", sa.Text(), primary_key=True),
        sa.Column(
            "work_item_id",
            sa.Text(),
            sa.ForeignKey("work_items.work_item_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("lease_token", sa.Text(), nullable=False),
        sa.Column("failure_class", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "work_item_id",
            "attempt_number",
            name="uq_work_item_attempt_number",
        ),
    )
    op.create_index(
        "ix_work_item_attempts_work_item_created",
        "work_item_attempts",
        ["work_item_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_work_item_attempts_work_item_created",
        table_name="work_item_attempts",
    )
    op.drop_table("work_item_attempts")
    op.drop_column("work_items", "failure_class")
    op.drop_column("work_items", "lease_expires_at")
    op.drop_column("work_items", "lease_token")
    op.drop_column("work_items", "attempt_number")
