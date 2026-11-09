"""Persist the bounded Factory semantic plan for explicit Builder continuation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0026_builder_semantic_plan"
down_revision: str | None = "local_0025_project_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "factory_sessions",
        sa.Column("semantic_plan_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("factory_sessions", "semantic_plan_json")
