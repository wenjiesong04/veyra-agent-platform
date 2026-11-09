"""Establish the empty Community migration head."""

from collections.abc import Sequence

revision: str = "community_0001_scaffold_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Reserve the first revision without introducing product tables."""


def downgrade() -> None:
    """Remove the empty baseline revision."""
