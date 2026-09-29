"""Add optimistic-concurrency revisioning to Cloud Project replicas."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "community_0010_project_sync_revision"
down_revision: str | None = "community_0009_cloud_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cloud_projects",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("cloud_projects", "revision")
