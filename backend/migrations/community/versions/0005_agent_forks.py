"""Record immutable Community fork edges between Agent versions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "community_0005_agent_forks"
down_revision: str | None = "community_0004_agent_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_agent_forks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_version_id", sa.String(length=36), nullable=False),
        sa.Column("target_version_id", sa.String(length=36), nullable=False),
        sa.Column("forked_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_version_id"],
            ["community_agent_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_version_id"],
            ["community_agent_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["forked_by"], ["community_users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "target_version_id", name="uq_community_agent_forks_target"
        ),
    )
    op.create_index(
        "ix_community_agent_forks_source_version",
        "community_agent_forks",
        ["source_version_id"],
    )
    op.create_index(
        "ix_community_agent_forks_target_version",
        "community_agent_forks",
        ["target_version_id"],
    )
    op.create_index(
        "ix_community_agent_forks_forked_by",
        "community_agent_forks",
        ["forked_by"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_community_agent_forks_forked_by", table_name="community_agent_forks"
    )
    op.drop_index(
        "ix_community_agent_forks_target_version", table_name="community_agent_forks"
    )
    op.drop_index(
        "ix_community_agent_forks_source_version", table_name="community_agent_forks"
    )
    op.drop_table("community_agent_forks")
