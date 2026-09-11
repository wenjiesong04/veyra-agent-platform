"""Add version-bound Community stars, reviews, and reports."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "community_0006_agent_feedback"
down_revision: str | None = "community_0005_agent_forks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_agent_stars",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"], ["community_agent_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["community_users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "version_id", "user_id", name="uq_community_agent_stars_version_user"
        ),
    )
    op.create_index(
        "ix_community_agent_stars_version_id",
        "community_agent_stars",
        ["version_id"],
    )
    op.create_index(
        "ix_community_agent_stars_user_id", "community_agent_stars", ["user_id"]
    )

    op.create_table(
        "community_agent_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"], ["community_agent_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["community_users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "version_id", "user_id", name="uq_community_agent_reviews_version_user"
        ),
    )
    op.create_index(
        "ix_community_agent_reviews_version_id",
        "community_agent_reviews",
        ["version_id"],
    )
    op.create_index(
        "ix_community_agent_reviews_user_id",
        "community_agent_reviews",
        ["user_id"],
    )

    op.create_table(
        "community_agent_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("reporter_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"], ["community_agent_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reporter_id"], ["community_users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "version_id",
            "reporter_id",
            "reason",
            name="uq_community_agent_reports_version_reporter_reason",
        ),
    )
    op.create_index(
        "ix_community_agent_reports_version_id",
        "community_agent_reports",
        ["version_id"],
    )
    op.create_index(
        "ix_community_agent_reports_reporter_id",
        "community_agent_reports",
        ["reporter_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_community_agent_reports_reporter_id",
        table_name="community_agent_reports",
    )
    op.drop_index(
        "ix_community_agent_reports_version_id",
        table_name="community_agent_reports",
    )
    op.drop_table("community_agent_reports")
    op.drop_index(
        "ix_community_agent_reviews_user_id",
        table_name="community_agent_reviews",
    )
    op.drop_index(
        "ix_community_agent_reviews_version_id",
        table_name="community_agent_reviews",
    )
    op.drop_table("community_agent_reviews")
    op.drop_index(
        "ix_community_agent_stars_user_id",
        table_name="community_agent_stars",
    )
    op.drop_index(
        "ix_community_agent_stars_version_id",
        table_name="community_agent_stars",
    )
    op.drop_table("community_agent_stars")
