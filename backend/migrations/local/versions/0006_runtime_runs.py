"""Add durable local Runtime runs and ordered evidence events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0006_runtime_runs"
down_revision: str | None = "local_0005_project_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_runs",
        sa.Column("run_id", sa.Text(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("projects.project_id"),
            nullable=False,
        ),
        sa.Column(
            "agent_id", sa.Text(), sa.ForeignKey("agents.agent_id"), nullable=False
        ),
        sa.Column(
            "version_id",
            sa.Text(),
            sa.ForeignKey("agent_versions.version_id"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("finished_at", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_runtime_runs_agent_created", "runtime_runs", ["agent_id", "created_at"]
    )
    op.create_table(
        "runtime_run_events",
        sa.Column("event_id", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "run_id", sa.Text(), sa.ForeignKey("runtime_runs.run_id"), primary_key=True
        ),
        sa.Column("sequence", sa.Integer(), primary_key=True),
        sa.Column("node_id", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("runtime_run_events")
    op.drop_index("ix_runtime_runs_agent_created", table_name="runtime_runs")
    op.drop_table("runtime_runs")
