"""Keep deleted Builder conversations recoverable in local Trash."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0024_builder_conversation_trash"
down_revision: str | None = "local_0023_builder_harness_receipts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "builder_conversations",
        sa.Column("removed_at", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_builder_conversations_project_trash",
        "builder_conversations",
        ["project_id", "removed_at", "last_activity_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_builder_conversations_project_trash",
        table_name="builder_conversations",
    )
    op.drop_column("builder_conversations", "removed_at")
