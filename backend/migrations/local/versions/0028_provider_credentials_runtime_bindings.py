"""Persist local Runtime credential metadata and Project bindings."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0028_provider_credentials_runtime_bindings"
down_revision: str | None = "local_0027_builder_creation_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_credentials",
        sa.Column("credential_id", sa.Text(), primary_key=True),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("provider_type", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("masked_hint", sa.Text(), nullable=False),
        sa.Column("capabilities_json", sa.Text(), nullable=False),
        sa.Column("default_model_id", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("secret_ref", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("validated_at", sa.Text(), nullable=True),
        sa.Column("last_used_at", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_provider_credentials_owner",
        "provider_credentials",
        ["owner_id", "status"],
    )
    op.create_table(
        "runtime_bindings",
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
        sa.Column("binding_slot", sa.Text(), nullable=False),
        sa.Column(
            "credential_id",
            sa.Text(),
            sa.ForeignKey("provider_credentials.credential_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "project_id", "agent_id", "binding_slot", name="uq_runtime_binding_scope"
        ),
    )
    op.create_index(
        "ix_runtime_bindings_project",
        "runtime_bindings",
        ["project_id", "agent_id", "binding_slot"],
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_bindings_project", table_name="runtime_bindings")
    op.drop_table("runtime_bindings")
    op.drop_index("ix_provider_credentials_owner", table_name="provider_credentials")
    op.drop_table("provider_credentials")
