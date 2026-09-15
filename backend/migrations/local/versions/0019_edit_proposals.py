"""Persist reviewed source changes outside Project files."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0019_edit_proposals"
down_revision: str | None = "local_0018_mcp_streamable_http"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "edit_proposals",
        sa.Column("proposal_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("rejected", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_edit_proposals_target",
        "edit_proposals",
        ["project_id", "target_kind", "target_id"],
    )


def downgrade() -> None:
    op.drop_table("edit_proposals")
