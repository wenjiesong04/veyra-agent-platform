"""Persist Community package scans and moderation decisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "community_0007_agent_moderation"
down_revision: str | None = "community_0006_agent_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "community_agent_versions",
        sa.Column(
            "scan_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
        ),
    )
    op.create_table(
        "community_agent_moderations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("moderator_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"], ["community_agent_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["moderator_id"], ["community_users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_community_agent_moderations_version_id",
        "community_agent_moderations",
        ["version_id"],
    )
    op.create_index(
        "ix_community_agent_moderations_moderator_id",
        "community_agent_moderations",
        ["moderator_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_community_agent_moderations_moderator_id",
        table_name="community_agent_moderations",
    )
    op.drop_index(
        "ix_community_agent_moderations_version_id",
        table_name="community_agent_moderations",
    )
    op.drop_table("community_agent_moderations")
    op.drop_column("community_agent_versions", "scan_json")
