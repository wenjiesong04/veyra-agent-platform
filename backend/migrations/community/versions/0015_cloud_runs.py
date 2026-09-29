"""Add the durable Cloud Runtime execution plane."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "community_0015_cloud_runs"
down_revision: str | None = "community_0014_server_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cloud_runs",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("agent_version_id", sa.String(length=36), nullable=False),
        sa.Column("execution_target", sa.String(length=16), nullable=False),
        sa.Column("binding_slot", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("inputs_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("retry_of_run_id", sa.String(length=36), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column(
            "stop_requested", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("current_node_id", sa.String(length=80), nullable=True),
        sa.Column("provider_type", sa.String(length=40), nullable=True),
        sa.Column("model_id", sa.String(length=160), nullable=True),
        sa.Column("credential_alias", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["community_users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["cloud_projects.project_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["retry_of_run_id"], ["cloud_runs.run_id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_cloud_runs_owner_created", "cloud_runs", ["owner_user_id", "created_at"]
    )
    op.create_index(
        "ix_cloud_runs_owner_project_created",
        "cloud_runs",
        ["owner_user_id", "project_id", "created_at"],
    )
    op.create_index("ix_cloud_runs_status", "cloud_runs", ["status"])

    op.create_table(
        "cloud_run_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("node_id", sa.String(length=80), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["cloud_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "run_id", "sequence", name="uq_cloud_run_events_run_sequence"
        ),
    )
    op.create_index(
        "ix_cloud_run_events_run_sequence", "cloud_run_events", ["run_id", "sequence"]
    )

    op.create_table(
        "cloud_run_commands",
        sa.Column("command_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("command", sa.String(length=32), nullable=False),
        sa.Column("result_run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["cloud_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("command_id"),
        sa.UniqueConstraint(
            "run_id", "idempotency_key", name="uq_cloud_run_commands_run_key"
        ),
    )
    op.create_index(
        "ix_cloud_run_commands_run_created",
        "cloud_run_commands",
        ["run_id", "created_at"],
    )

    op.create_table(
        "cloud_run_checkpoints",
        sa.Column("checkpoint_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=80), nullable=False),
        sa.Column("waiting_kind", sa.String(length=32), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["cloud_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("checkpoint_id"),
    )
    op.create_index(
        "ix_cloud_run_checkpoints_run_created",
        "cloud_run_checkpoints",
        ["run_id", "created_at"],
    )

    op.create_table(
        "cloud_run_approvals",
        sa.Column("approval_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=80), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["cloud_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("approval_id"),
    )
    op.create_index(
        "ix_cloud_run_approvals_run_status", "cloud_run_approvals", ["run_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_cloud_run_approvals_run_status", table_name="cloud_run_approvals")
    op.drop_table("cloud_run_approvals")
    op.drop_index(
        "ix_cloud_run_checkpoints_run_created", table_name="cloud_run_checkpoints"
    )
    op.drop_table("cloud_run_checkpoints")
    op.drop_index("ix_cloud_run_commands_run_created", table_name="cloud_run_commands")
    op.drop_table("cloud_run_commands")
    op.drop_index("ix_cloud_run_events_run_sequence", table_name="cloud_run_events")
    op.drop_table("cloud_run_events")
    op.drop_index("ix_cloud_runs_status", table_name="cloud_runs")
    op.drop_index("ix_cloud_runs_owner_project_created", table_name="cloud_runs")
    op.drop_index("ix_cloud_runs_owner_created", table_name="cloud_runs")
    op.drop_table("cloud_runs")
