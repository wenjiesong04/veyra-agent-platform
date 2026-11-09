"""Project entity store for Builder-generated persistent objects."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0034_project_entities"
down_revision: str | None = "local_0033_agent_app_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_entities",
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("schema_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "entity_type"),
    )
    op.create_table(
        "entity_records",
        sa.Column("entity_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_entity_records_revision"),
    )
    op.create_index(
        "ix_entity_records_project_type",
        "entity_records",
        ["project_id", "entity_type"],
    )
    op.create_table(
        "entity_events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("old_digest", sa.Text(), nullable=True),
        sa.Column("new_digest", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entity_records.entity_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_entity_events_entity", "entity_events", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_entity_events_entity", table_name="entity_events")
    op.drop_table("entity_events")
    op.drop_index("ix_entity_records_project_type", table_name="entity_records")
    op.drop_table("entity_records")
    op.drop_table("project_entities")
