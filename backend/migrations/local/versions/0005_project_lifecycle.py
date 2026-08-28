"""Track reversible local Project removal without changing recovery identity."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0005_project_lifecycle"
down_revision: str | None = "local_0004_project_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("removed_at", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "removed_at")
