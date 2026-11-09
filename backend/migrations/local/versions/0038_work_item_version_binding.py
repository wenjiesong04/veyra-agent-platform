"""Pin WorkItems and retain the identity of dispatch/retry attempts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0038_work_item_version_binding"
down_revision: str | None = "local_0037_entity_revision_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Historical rows do not establish a committed binding; never guess latest.
    op.add_column("work_items", sa.Column("agent_version_id", sa.Text(), nullable=True))
    op.add_column(
        "work_items", sa.Column("agent_source_hash", sa.Text(), nullable=True)
    )
    op.add_column(
        "work_item_attempts", sa.Column("operation", sa.Text(), nullable=True)
    )
    op.add_column(
        "work_item_attempts", sa.Column("previous_run_id", sa.Text(), nullable=True)
    )
    op.add_column(
        "work_item_attempts", sa.Column("request_key", sa.Text(), nullable=True)
    )
    op.add_column(
        "work_item_attempts", sa.Column("error_code", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("work_item_attempts", "error_code")
    op.drop_column("work_item_attempts", "request_key")
    op.drop_column("work_item_attempts", "previous_run_id")
    op.drop_column("work_item_attempts", "operation")
    op.drop_column("work_items", "agent_source_hash")
    op.drop_column("work_items", "agent_version_id")
