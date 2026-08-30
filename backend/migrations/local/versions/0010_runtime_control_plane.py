"""Persist Tool authorization, approvals, checkpoints, and run commands."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0010_runtime_control_plane"
down_revision: str | None = "local_0009_agent_hierarchy_runtime_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runtime_runs", sa.Column("inputs_json", sa.Text(), nullable=True))
    op.create_table(
        "runtime_tool_calls",
        sa.Column("tool_call_id", sa.Text(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Text(),
            sa.ForeignKey("runtime_runs.run_id"),
            nullable=False,
        ),
        sa.Column("node_id", sa.Text(), nullable=False),
        sa.Column("tool_reference", sa.Text(), nullable=False),
        sa.Column("authorization", sa.Text(), nullable=False),
        sa.Column("decision_code", sa.Text(), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=False),
        sa.Column("input_digest", sa.Text(), nullable=False),
        sa.Column("receipt_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_runtime_tool_calls_run", "runtime_tool_calls", ["run_id", "created_at"]
    )
    op.create_table(
        "runtime_approval_requests",
        sa.Column("approval_id", sa.Text(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Text(),
            sa.ForeignKey("runtime_runs.run_id"),
            nullable=False,
        ),
        sa.Column("node_id", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("resolved_at", sa.Text(), nullable=True),
        sa.Column("resolved_by_command_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_runtime_approvals_run",
        "runtime_approval_requests",
        ["run_id", "status"],
    )
    op.create_table(
        "runtime_checkpoints",
        sa.Column("checkpoint_id", sa.Text(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Text(),
            sa.ForeignKey("runtime_runs.run_id"),
            nullable=False,
        ),
        sa.Column("node_id", sa.Text(), nullable=False),
        sa.Column("waiting_kind", sa.Text(), nullable=False),
        sa.Column("values_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_runtime_checkpoints_run", "runtime_checkpoints", ["run_id", "created_at"]
    )
    op.create_table(
        "runtime_run_commands",
        sa.Column("command_id", sa.Text(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Text(),
            sa.ForeignKey("runtime_runs.run_id"),
            nullable=False,
        ),
        sa.Column("command_type", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("applied_at", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_runtime_run_commands_run", "runtime_run_commands", ["run_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_run_commands_run", table_name="runtime_run_commands")
    op.drop_table("runtime_run_commands")
    op.drop_index("ix_runtime_checkpoints_run", table_name="runtime_checkpoints")
    op.drop_table("runtime_checkpoints")
    op.drop_index("ix_runtime_approvals_run", table_name="runtime_approval_requests")
    op.drop_table("runtime_approval_requests")
    op.drop_index("ix_runtime_tool_calls_run", table_name="runtime_tool_calls")
    op.drop_table("runtime_tool_calls")
    op.drop_column("runtime_runs", "inputs_json")
