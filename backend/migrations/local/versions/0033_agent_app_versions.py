"""Pin Agent App conversations to committed versions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0033_agent_app_versions"
down_revision: str | None = "local_0032_factory_specification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_versions",
        sa.Column("committed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_conversations",
        sa.Column("agent_version_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_conversations",
        sa.Column("metadata_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_conversations", "metadata_json")
    op.drop_column("agent_conversations", "agent_version_id")
    op.drop_column("agent_versions", "committed")
