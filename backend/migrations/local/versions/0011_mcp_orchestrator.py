"""Persist host-side MCP servers and local WorkItems outside Project directories."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0011_mcp_orchestrator"
down_revision: str | None = "local_0010_runtime_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column("server_id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("args_json", sa.Text(), nullable=False),
        sa.Column("env_names_json", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_mcp_servers_created", "mcp_servers", ["created_at"])
    op.create_table(
        "work_items",
        sa.Column("work_item_id", sa.Text(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("projects.project_id"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("depends_on_json", sa.Text(), nullable=False),
        sa.Column("inputs_json", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_work_items_project", "work_items", ["project_id", "created_at"])
    op.create_index("ix_work_items_status", "work_items", ["status"])
