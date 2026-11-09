"""Persist Factory provider capability facts without secrets or user data."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0022_provider_capability_profiles"
down_revision: str | None = "local_0021_builder_operation_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_capability_profiles",
        sa.Column("identity_key", sa.Text(), primary_key=True),
        sa.Column("provider_id", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("endpoint_kind", sa.Text(), nullable=False),
        sa.Column("base_url_fingerprint", sa.Text(), nullable=False),
        sa.Column("probe_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("profile_json", sa.Text(), nullable=False),
        sa.Column("checked_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_provider_capability_profiles_identity",
        "provider_capability_profiles",
        ["provider_id", "model", "endpoint_kind", "probe_version"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_capability_profiles_identity",
        table_name="provider_capability_profiles",
    )
    op.drop_table("provider_capability_profiles")
