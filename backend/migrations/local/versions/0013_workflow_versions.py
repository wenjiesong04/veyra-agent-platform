"""Immutable Workflow versions, mirroring Agent commits.

Revision ID: local_0013_workflow_versions
Revises: local_0012_workflow_library
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0013_workflow_versions"
down_revision: str | None = "local_0012_workflow_library"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_versions",
        sa.Column("version_id", sa.Text(), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.Text(),
            sa.ForeignKey("workflows.workflow_id"),
            nullable=False,
        ),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.Column("behavior_hash", sa.Text(), nullable=False),
        sa.Column("lock_hash", sa.Text(), nullable=False),
        sa.Column("file_hash", sa.Text(), nullable=False),
        sa.Column("source_json", sa.Text(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("workflow_id", "file_hash"),
    )
    op.create_table(
        "workflow_version_files",
        sa.Column(
            "version_id",
            sa.Text(),
            sa.ForeignKey("workflow_versions.version_id"),
            primary_key=True,
        ),
        sa.Column(
            "file_id",
            sa.Text(),
            sa.ForeignKey("files.file_id"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("workflow_version_files")
    op.drop_table("workflow_versions")
