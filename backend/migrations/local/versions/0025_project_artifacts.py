"""Project-scoped runtime artifacts on the local object store."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0025_project_artifacts"
down_revision: str | None = "local_0024_builder_conversation_trash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_artifacts",
        sa.Column("artifact_id", sa.Text(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("projects.project_id"),
            nullable=False,
        ),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_ref", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_project_artifacts_project_created",
        "project_artifacts",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_artifacts_project_created", table_name="project_artifacts"
    )
    op.drop_table("project_artifacts")
