"""Retain actual entity revision snapshots; old records get one honest baseline."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0037_entity_revision_history"
down_revision: str | None = "local_0036_model_capabilities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entity_revisions",
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.Text(), nullable=False),
        sa.Column("snapshot_kind", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("entity_id", "revision"),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["entity_records.entity_id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_entity_revisions_revision"),
        sa.CheckConstraint(
            "snapshot_kind IN ('write', 'baseline')",
            name="ck_entity_revisions_snapshot_kind",
        ),
    )
    # Digest-only events cannot reconstruct prior contents or their sources.
    op.execute(
        sa.text(
            "INSERT INTO entity_revisions("
            "entity_id, revision, payload_json, status, source, recorded_at, "
            "snapshot_kind) "
            "SELECT entity_id, revision, payload_json, status, 'legacy_baseline', "
            "updated_at, 'baseline' FROM entity_records"
        )
    )


def downgrade() -> None:
    op.drop_table("entity_revisions")
