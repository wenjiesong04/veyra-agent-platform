"""Link canonical Builder creation proposals to their operation and Factory session."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0027_builder_creation_proposals"
down_revision: str | None = "local_0026_builder_semantic_plan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "edit_proposals",
        sa.Column("builder_creation_operation_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "edit_proposals",
        sa.Column("factory_session_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "edit_proposals",
        sa.Column("applied_agent_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "edit_proposals",
        sa.Column("applied_json", sa.Text(), nullable=True),
    )
    op.create_index(
        "uq_edit_proposals_builder_operation",
        "edit_proposals",
        ["project_id", "builder_creation_operation_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_edit_proposals_builder_operation", table_name="edit_proposals")
    op.drop_column("edit_proposals", "applied_json")
    op.drop_column("edit_proposals", "applied_agent_id")
    op.drop_column("edit_proposals", "factory_session_id")
    op.drop_column("edit_proposals", "builder_creation_operation_id")
