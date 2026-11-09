"""Persist per-artifact Local sync checkpoints without copying payloads."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0031_project_artifact_sync_state"
down_revision: str | None = "local_0030_project_sync_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_artifact_sync_states",
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("artifact_kind", sa.Text(), nullable=False),
        sa.Column("artifact_id", sa.Text(), nullable=False),
        sa.Column("local_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cloud_revision", sa.Integer(), nullable=True),
        sa.Column("local_content_hash", sa.Text(), nullable=True),
        sa.Column("last_synced_hash", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False, server_default="local_only"),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_synced_at", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.project_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("project_id", "artifact_kind", "artifact_id"),
    )
    op.create_index(
        "ix_project_artifact_sync_states_project_state",
        "project_artifact_sync_states",
        ["project_id", "state"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_artifact_sync_states_project_state",
        table_name="project_artifact_sync_states",
    )
    op.drop_table("project_artifact_sync_states")
