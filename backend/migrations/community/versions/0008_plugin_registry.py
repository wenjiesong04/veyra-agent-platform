"""Add the Community Plugin Pack registry."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "community_0008_plugin_registry"
down_revision: str | None = "community_0007_agent_moderation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_plugins",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["community_users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "slug", name="uq_community_plugins_owner_slug"),
    )
    op.create_index("ix_community_plugins_owner_id", "community_plugins", ["owner_id"])
    op.create_table(
        "community_plugin_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("plugin_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("package_storage_id", sa.String(length=64), nullable=False),
        sa.Column("package_hash", sa.String(length=64), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("skill_count", sa.Integer(), nullable=False),
        sa.Column("mcp_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["plugin_id"], ["community_plugins.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plugin_id", "version", name="uq_community_plugin_versions_plugin_version"
        ),
        sa.UniqueConstraint(
            "package_storage_id", name="uq_community_plugin_versions_storage"
        ),
    )
    op.create_index(
        "ix_community_plugin_versions_plugin_id",
        "community_plugin_versions",
        ["plugin_id"],
    )
    op.create_table(
        "community_plugin_moderations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("moderator_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"], ["community_plugin_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["moderator_id"], ["community_users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_community_plugin_moderations_version_id",
        "community_plugin_moderations",
        ["version_id"],
    )
    op.create_index(
        "ix_community_plugin_moderations_moderator_id",
        "community_plugin_moderations",
        ["moderator_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_community_plugin_moderations_moderator_id",
        table_name="community_plugin_moderations",
    )
    op.drop_index(
        "ix_community_plugin_moderations_version_id",
        table_name="community_plugin_moderations",
    )
    op.drop_table("community_plugin_moderations")
    op.drop_index(
        "ix_community_plugin_versions_plugin_id", table_name="community_plugin_versions"
    )
    op.drop_table("community_plugin_versions")
    op.drop_index("ix_community_plugins_owner_id", table_name="community_plugins")
    op.drop_table("community_plugins")
