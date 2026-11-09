"""Index Project Workflows and their mutable Studio drafts.

Revision ID: local_0012_workflow_library
Revises: local_0011_mcp_orchestrator
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0012_workflow_library"
down_revision: str | None = "local_0011_mcp_orchestrator"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("workflow_id", sa.Text(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("projects.project_id"),
            nullable=False,
        ),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_file_hash", sa.Text(), nullable=False),
        sa.Column("indexed_at", sa.Text(), nullable=False),
        sa.Column("removed_at", sa.Text(), nullable=True),
        sa.UniqueConstraint("project_id", "slug"),
    )
    op.create_table(
        "workflow_drafts",
        sa.Column(
            "workflow_id",
            sa.Text(),
            sa.ForeignKey("workflows.workflow_id"),
            primary_key=True,
        ),
        sa.Column("draft_id", sa.Text(), nullable=False, unique=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("source_json", sa.Text(), nullable=False),
        sa.Column("source_file_hash", sa.Text(), nullable=False),
        sa.Column("etag", sa.Text(), nullable=False),
    )
    op.create_table(
        "workflow_draft_write_intents",
        sa.Column("intent_id", sa.Text(), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.Text(),
            sa.ForeignKey("workflows.workflow_id"),
            nullable=False,
        ),
        sa.Column("previous_source_text", sa.Text(), nullable=False),
        sa.Column("intended_source_text", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("workflow_draft_write_intents")
    op.drop_table("workflow_drafts")
    op.drop_table("workflows")
