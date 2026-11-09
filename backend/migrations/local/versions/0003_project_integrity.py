"""Harden local Project indexes for idempotency and write recovery."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0003_project_integrity"
down_revision: str | None = "local_0002_project_library_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "idempotency_records",
        sa.Column("request_digest", sa.Text(), nullable=False, server_default=""),
    )
    op.create_table(
        "draft_write_intents",
        sa.Column("intent_id", sa.Text(), primary_key=True),
        sa.Column(
            "agent_id", sa.Text(), sa.ForeignKey("agents.agent_id"), nullable=False
        ),
        sa.Column("previous_source_text", sa.Text(), nullable=False),
        sa.Column("intended_source_text", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("draft_write_intents")
    op.drop_column("idempotency_records", "request_digest")
