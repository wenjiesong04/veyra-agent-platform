"""Persist local metadata needed to coordinate Project Replica sync."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0030_project_sync_state"
down_revision: str | None = "local_0029_provider_credential_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_sync_states",
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("projects.project_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "sync_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("state", sa.Text(), nullable=False, server_default="local_only"),
        sa.Column("cloud_revision", sa.Integer(), nullable=True),
        sa.Column("local_metadata_hash", sa.Text(), nullable=True),
        sa.Column("last_synced_hash", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.Text(), nullable=True),
        sa.Column("pending_operation", sa.Text(), nullable=True),
        sa.Column("remote_name", sa.Text(), nullable=True),
        sa.Column("remote_description", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
    )
    op.execute(
        """
        INSERT INTO project_sync_states(project_id, local_metadata_hash)
        SELECT project_id, manifest_hash FROM projects
        """
    )


def downgrade() -> None:
    op.drop_table("project_sync_states")
