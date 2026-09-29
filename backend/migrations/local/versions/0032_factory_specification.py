"""Persist Factory AgentSpecification beside the SemanticPlan."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0032_factory_specification"
down_revision: str | None = "local_0031_project_artifact_sync_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "factory_sessions",
        sa.Column("specification_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("factory_sessions", "specification_json")
