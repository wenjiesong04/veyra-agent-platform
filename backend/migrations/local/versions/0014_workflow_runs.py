"""Persist Workflow runs, checkpoints, and links to immutable Agent runs."""

import sqlalchemy as sa
from alembic import op

revision = "local_0014_workflow_runs"
down_revision = "local_0013_workflow_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("run_id", sa.Text(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("projects.project_id"),
            nullable=False,
        ),
        sa.Column(
            "workflow_id",
            sa.Text(),
            sa.ForeignKey("workflows.workflow_id"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            sa.Text(),
            sa.ForeignKey("workflow_versions.version_id"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("context_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text()),
        sa.Column("error_json", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("finished_at", sa.Text()),
    )
    op.create_table(
        "workflow_run_events",
        sa.Column(
            "run_id", sa.Text(), sa.ForeignKey("workflow_runs.run_id"), primary_key=True
        ),
        sa.Column("sequence", sa.Integer(), primary_key=True),
        sa.Column("node_id", sa.Text()),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.add_column(
        "workflow_run_events", sa.Column("event_id", sa.Text(), nullable=False)
    )
    op.create_table(
        "workflow_run_calls",
        sa.Column(
            "run_id", sa.Text(), sa.ForeignKey("workflow_runs.run_id"), primary_key=True
        ),
        sa.Column("node_id", sa.Text(), primary_key=True),
        sa.Column(
            "agent_id", sa.Text(), sa.ForeignKey("agents.agent_id"), nullable=False
        ),
        sa.Column(
            "version_id",
            sa.Text(),
            sa.ForeignKey("agent_versions.version_id"),
            nullable=False,
        ),
        sa.Column("dispatch_key", sa.Text(), nullable=False),
        sa.Column("child_run_id", sa.Text(), sa.ForeignKey("runtime_runs.run_id")),
    )


def downgrade() -> None:
    op.drop_table("workflow_run_calls")
    op.drop_table("workflow_run_events")
    op.drop_table("workflow_runs")
