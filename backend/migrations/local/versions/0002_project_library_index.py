"""Add local Project, Agent Library, file, blob, and idempotency indexes.

Revision ID: local_0002_project_library_index
Revises: local_0001_scaffold_baseline
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0002_project_library_index"
down_revision: str | None = "local_0001_scaffold_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("project_id", sa.Text(), primary_key=True),
        sa.Column("root_path", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("manifest_hash", sa.Text(), nullable=False),
        sa.Column("indexed_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "agents",
        sa.Column("agent_id", sa.Text(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("projects.project_id"),
            nullable=False,
        ),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_file_hash", sa.Text(), nullable=False),
        sa.Column("indexed_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("project_id", "slug"),
    )
    op.create_table(
        "agent_drafts",
        sa.Column(
            "agent_id", sa.Text(), sa.ForeignKey("agents.agent_id"), primary_key=True
        ),
        sa.Column("draft_id", sa.Text(), nullable=False, unique=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("source_json", sa.Text(), nullable=False),
        sa.Column("source_file_hash", sa.Text(), nullable=False),
        sa.Column("etag", sa.Text(), nullable=False),
    )
    op.create_table(
        "agent_versions",
        sa.Column("version_id", sa.Text(), primary_key=True),
        sa.Column(
            "agent_id", sa.Text(), sa.ForeignKey("agents.agent_id"), nullable=False
        ),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.Column("behavior_hash", sa.Text(), nullable=False),
        sa.Column("lock_hash", sa.Text(), nullable=False),
        sa.Column("file_hash", sa.Text(), nullable=False),
        sa.Column("source_json", sa.Text(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("agent_id", "file_hash"),
    )
    op.create_table(
        "blobs",
        sa.Column("digest", sa.Text(), primary_key=True),
        sa.Column("byte_length", sa.Integer(), nullable=False),
        sa.Column("object_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "files",
        sa.Column("file_id", sa.Text(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("projects.project_id"),
            nullable=False,
        ),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column(
            "current_blob_digest",
            sa.Text(),
            sa.ForeignKey("blobs.digest"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("project_id", "relative_path"),
    )
    op.create_table(
        "file_versions",
        sa.Column(
            "file_id", sa.Text(), sa.ForeignKey("files.file_id"), primary_key=True
        ),
        sa.Column(
            "blob_digest", sa.Text(), sa.ForeignKey("blobs.digest"), primary_key=True
        ),
        sa.Column("observed_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "agent_version_files",
        sa.Column(
            "version_id",
            sa.Text(),
            sa.ForeignKey("agent_versions.version_id"),
            primary_key=True,
        ),
        sa.Column(
            "file_id", sa.Text(), sa.ForeignKey("files.file_id"), primary_key=True
        ),
    )
    op.create_table(
        "idempotency_records",
        sa.Column("scope", sa.Text(), primary_key=True),
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("response_json", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    for table in (
        "idempotency_records",
        "agent_version_files",
        "file_versions",
        "files",
        "blobs",
        "agent_versions",
        "agent_drafts",
        "agents",
        "projects",
    ):
        op.drop_table(table)
