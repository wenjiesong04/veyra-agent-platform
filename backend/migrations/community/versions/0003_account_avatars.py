"""Add Community account avatar metadata.

Revision ID: community_0003_account_avatars
Revises: community_0002_accounts_auth_mail
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "community_0003_account_avatars"
down_revision: str | None = "community_0002_accounts_auth_mail"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_avatars",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("storage_id", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("etag", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["community_users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("storage_id", name="uq_community_avatars_storage_id"),
    )


def downgrade() -> None:
    op.drop_table("community_avatars")
