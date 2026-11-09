"""Add immutable Agent identities and published version metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "community_0004_agent_registry"
down_revision: str | None = "community_0003_account_avatars"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_agents",
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
        sa.UniqueConstraint("owner_id", "slug", name="uq_community_agents_owner_slug"),
    )
    op.create_index("ix_community_agents_owner_id", "community_agents", ["owner_id"])
    op.create_table(
        "community_agent_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("source_storage_id", sa.String(length=64), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("behavior_hash", sa.String(length=64), nullable=False),
        sa.Column("lock_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["community_agents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_id", "version", name="uq_community_agent_versions_agent_version"
        ),
        sa.UniqueConstraint(
            "source_storage_id", name="uq_community_agent_versions_storage"
        ),
    )
    op.create_index(
        "ix_community_agent_versions_agent_id", "community_agent_versions", ["agent_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_community_agent_versions_agent_id", table_name="community_agent_versions"
    )
    op.drop_table("community_agent_versions")
    op.drop_index("ix_community_agents_owner_id", table_name="community_agents")
    op.drop_table("community_agents")
