"""Persist per-invocation Builder Harness receipts outside Project files."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0023_builder_harness_receipts"
down_revision: str | None = "local_0022_provider_capability_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "builder_harness_receipts",
        sa.Column("receipt_id", sa.Text(), primary_key=True),
        sa.Column(
            "operation_id",
            sa.Text(),
            sa.ForeignKey("builder_operations.operation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.Text(),
            sa.ForeignKey("builder_conversations.conversation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("projects.project_id"),
            nullable=False,
        ),
        sa.Column("invocation_kind", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.Column("harness_mode", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("policy_hash", sa.Text(), nullable=False),
        sa.Column("output_contract", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("schema_hash", sa.Text(), nullable=False),
        sa.Column("structured_mode", sa.Text(), nullable=False),
        sa.Column("project_snapshot_hash", sa.Text(), nullable=False),
        sa.Column("catalog_snapshot_hash", sa.Text(), nullable=False),
        sa.Column("included_categories_json", sa.Text(), nullable=False),
        sa.Column("excluded_categories_json", sa.Text(), nullable=False),
        sa.Column("history_message_count", sa.Integer(), nullable=False),
        sa.Column("context_size_bytes", sa.Integer(), nullable=False),
        sa.Column("request_size_bytes", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("endpoint_kind", sa.Text(), nullable=False),
        sa.Column("provider_profile_status", sa.Text(), nullable=False),
        sa.Column("provider_profile_source", sa.Text(), nullable=False),
        sa.Column("schema_profile", sa.Text(), nullable=False),
        sa.Column("failure_stage", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("safe_provider_error_type", sa.Text(), nullable=True),
        sa.Column("safe_provider_error_param", sa.Text(), nullable=True),
        sa.Column("provider_request_id", sa.Text(), nullable=True),
        sa.Column("fallback_from", sa.Text(), nullable=True),
        sa.Column("fallback_to", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "operation_id",
            "sequence",
            name="uq_builder_harness_receipts_sequence",
        ),
    )
    op.create_index(
        "ix_builder_harness_receipts_scope",
        "builder_harness_receipts",
        ["project_id", "conversation_id", "operation_id", "sequence"],
    )
