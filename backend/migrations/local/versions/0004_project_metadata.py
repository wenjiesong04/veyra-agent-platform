"""Add portable Project descriptions and local-only pin metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0004_project_metadata"
down_revision: str | None = "local_0003_project_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column("projects", sa.Column("pinned_at", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "pinned_at")
    op.drop_column("projects", "description")
