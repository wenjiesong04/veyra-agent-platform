"""Persist Cloud Project metadata in the server account database lineage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "community_0009_cloud_projects"
down_revision: str | None = "community_0008_plugin_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cloud_projects",
        sa.Column("project_id", sa.String(length=36), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("community_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "schema_version",
            sa.String(length=32),
            nullable=False,
            server_default="cloud.project.v1",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_cloud_projects_owner_updated",
        "cloud_projects",
        ["owner_user_id", "updated_at"],
    )
    op.create_index(
        "ix_cloud_projects_owner_archived",
        "cloud_projects",
        ["owner_user_id", "archived_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_cloud_projects_owner_archived", table_name="cloud_projects")
    op.drop_index("ix_cloud_projects_owner_updated", table_name="cloud_projects")
    op.drop_table("cloud_projects")
