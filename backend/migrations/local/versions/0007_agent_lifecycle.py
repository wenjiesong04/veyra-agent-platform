"""Track recoverable Agent removal while retaining immutable history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0007_agent_lifecycle"
down_revision: str | None = "local_0006_runtime_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("removed_at", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "removed_at")
