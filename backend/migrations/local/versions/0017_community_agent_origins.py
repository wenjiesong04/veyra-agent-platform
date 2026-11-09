"""Retain Community provenance for locally imported Agent identities."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0017_community_agent_origins"
down_revision: str | None = "local_0016_orchestrator_leases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_agent_origins",
        sa.Column("local_agent_id", sa.Text(), nullable=False),
        sa.Column("owner_handle", sa.Text(), nullable=False),
        sa.Column("remote_slug", sa.Text(), nullable=False),
        sa.Column("remote_version", sa.Text(), nullable=False),
        sa.Column("remote_source_hash", sa.Text(), nullable=False),
        sa.Column("imported_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["local_agent_id"],
            ["agents.agent_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("local_agent_id"),
    )
    op.create_index(
        "ix_community_agent_origins_remote",
        "community_agent_origins",
        ["owner_handle", "remote_slug", "remote_version"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_community_agent_origins_remote",
        table_name="community_agent_origins",
    )
    op.drop_table("community_agent_origins")
