"""Add encrypted server-owned Cloud Runtime credential metadata and bindings."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "community_0014_server_credentials"
down_revision: str | None = "community_0013_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cloud_credentials",
        sa.Column("credential_id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("provider_type", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("masked_hint", sa.String(length=32), nullable=False),
        sa.Column("capabilities_json", sa.Text(), nullable=False),
        sa.Column("default_model_id", sa.String(length=160), nullable=True),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["community_users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("credential_id"),
    )
    op.create_index(
        "ix_cloud_credentials_owner_updated",
        "cloud_credentials",
        ["owner_user_id", "updated_at"],
    )
    op.create_index(
        "ix_cloud_credentials_owner_default",
        "cloud_credentials",
        ["owner_user_id", "is_default"],
    )
    op.create_table(
        "cloud_runtime_bindings",
        sa.Column("binding_id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("binding_slot", sa.String(length=80), nullable=False),
        sa.Column("credential_id", sa.String(length=36), nullable=False),
        sa.Column("model_id", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["community_users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["cloud_projects.project_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["credential_id"], ["cloud_credentials.credential_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("binding_id"),
    )
    op.create_index(
        "ix_cloud_runtime_bindings_owner_project_agent_slot",
        "cloud_runtime_bindings",
        ["owner_user_id", "project_id", "agent_id", "binding_slot"],
    )
    op.create_index(
        "ix_cloud_runtime_bindings_credential",
        "cloud_runtime_bindings",
        ["credential_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cloud_runtime_bindings_credential", table_name="cloud_runtime_bindings"
    )
    op.drop_index(
        "ix_cloud_runtime_bindings_owner_project_agent_slot",
        table_name="cloud_runtime_bindings",
    )
    op.drop_table("cloud_runtime_bindings")
    op.drop_index("ix_cloud_credentials_owner_default", table_name="cloud_credentials")
    op.drop_index("ix_cloud_credentials_owner_updated", table_name="cloud_credentials")
    op.drop_table("cloud_credentials")
