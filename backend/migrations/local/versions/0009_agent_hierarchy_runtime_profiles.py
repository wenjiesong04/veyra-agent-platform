"""Track Project Agent hierarchy and non-secret Runtime API profiles."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0009_agent_hierarchy_runtime_profiles"
down_revision: str | None = "local_0008_factory_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("parent_agent_id", sa.Text(), nullable=True),
    )
    op.create_index("ix_agents_parent_agent", "agents", ["parent_agent_id"])
    op.create_table(
        "runtime_api_profiles",
        sa.Column("scope_id", sa.Text(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("projects.project_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.Text(),
            sa.ForeignKey("agents.agent_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("profile_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "project_id", "agent_id", name="uq_runtime_api_profiles_scope"
        ),
    )
    op.create_index(
        "ix_runtime_api_profiles_project",
        "runtime_api_profiles",
        ["project_id", "agent_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_api_profiles_project", table_name="runtime_api_profiles")
    op.drop_table("runtime_api_profiles")
    op.drop_index("ix_agents_parent_agent", table_name="agents")
    op.drop_column("agents", "parent_agent_id")
