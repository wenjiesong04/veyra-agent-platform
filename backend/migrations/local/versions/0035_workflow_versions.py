"""Track which immutable Workflow versions were explicitly committed."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0035_workflow_versions"
down_revision: str | None = "local_0034_project_entities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing snapshots may have been created by Studio Test Run, so leave
    # their commitment state unknown and require a fresh explicit commit.
    op.add_column(
        "workflow_versions",
        sa.Column("committed", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("workflow_versions", "committed")
