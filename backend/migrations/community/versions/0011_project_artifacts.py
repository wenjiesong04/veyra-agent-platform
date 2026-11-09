"""Persist portable Project Artifact replicas in the Cloud account lineage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "community_0011_project_artifacts"
down_revision: str | None = "community_0010_project_sync_revision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_artifacts",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_kind", sa.String(length=32), nullable=False),
        sa.Column("artifact_id", sa.String(length=160), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("immutable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["cloud_projects.project_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("project_id", "artifact_kind", "artifact_id"),
    )
    op.create_index(
        "ix_project_artifacts_project_updated",
        "project_artifacts",
        ["project_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_artifacts_project_updated", table_name="project_artifacts"
    )
    op.drop_table("project_artifacts")
