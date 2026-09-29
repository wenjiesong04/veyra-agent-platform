"""Add the local/device scope to Runtime credentials."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0029_provider_credential_scope"
down_revision: str | None = "local_0028_provider_credentials_runtime_bindings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provider_credentials",
        sa.Column(
            "credential_scope",
            sa.Text(),
            nullable=False,
            server_default="device",
        ),
    )


def downgrade() -> None:
    op.drop_column("provider_credentials", "credential_scope")
