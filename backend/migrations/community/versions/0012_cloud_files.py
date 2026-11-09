"""Add private Cloud File metadata and Project File references."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "community_0012_cloud_files"
down_revision: str | None = "community_0011_project_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cloud_files",
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["community_users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("file_id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_cloud_files_owner_created",
        "cloud_files",
        ["owner_user_id", "created_at"],
    )
    op.create_index(
        "ix_cloud_files_owner_state",
        "cloud_files",
        ["owner_user_id", "state"],
    )

    op.create_table(
        "cloud_project_file_references",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["cloud_projects.project_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["cloud_files.file_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["community_users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("project_id", "file_id"),
    )
    op.create_index(
        "ix_cloud_project_file_refs_project_created",
        "cloud_project_file_references",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_cloud_project_file_refs_owner_file",
        "cloud_project_file_references",
        ["owner_user_id", "file_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cloud_project_file_refs_owner_file",
        table_name="cloud_project_file_references",
    )
    op.drop_index(
        "ix_cloud_project_file_refs_project_created",
        table_name="cloud_project_file_references",
    )
    op.drop_table("cloud_project_file_references")
    op.drop_index("ix_cloud_files_owner_state", table_name="cloud_files")
    op.drop_index("ix_cloud_files_owner_created", table_name="cloud_files")
    op.drop_table("cloud_files")
