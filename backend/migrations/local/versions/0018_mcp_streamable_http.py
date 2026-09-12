"""Add Streamable HTTP MCP connection metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0018_mcp_streamable_http"
down_revision: str | None = "local_0017_community_agent_origins"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mcp_servers",
        sa.Column("transport", sa.Text(), nullable=False, server_default="stdio"),
    )
    op.add_column("mcp_servers", sa.Column("url", sa.Text(), nullable=True))
    op.add_column(
        "mcp_servers",
        sa.Column(
            "header_templates_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("mcp_servers", "header_templates_json")
    op.drop_column("mcp_servers", "url")
    op.drop_column("mcp_servers", "transport")
