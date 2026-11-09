"""Add Community accounts, secure auth state, and transactional mail outbox.

Revision ID: community_0002_accounts_auth_mail
Revises: community_0001_scaffold_baseline
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "community_0002_accounts_auth_mail"
down_revision: str | None = "community_0001_scaffold_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create PostgreSQL-ready tables for the V1-1 account foundation."""

    op.create_table(
        "community_users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email_normalized", sa.String(length=320), nullable=False),
        sa.Column("handle", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email_normalized", name="uq_community_users_email"),
        sa.UniqueConstraint("handle", name="uq_community_users_handle"),
    )
    op.create_index(
        "ix_community_users_email_normalized",
        "community_users",
        ["email_normalized"],
    )
    op.create_index("ix_community_users_handle", "community_users", ["handle"])

    op.create_table(
        "community_verification_codes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email_normalized", sa.String(length=320), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("code_hmac", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resend_available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_ip_hash", sa.String(length=64), nullable=False),
        sa.Column("requested_device_hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_community_verification_codes_email_normalized",
        "community_verification_codes",
        ["email_normalized"],
    )
    op.create_index(
        "ix_community_verification_codes_purpose",
        "community_verification_codes",
        ["purpose"],
    )

    op.create_table(
        "community_auth_rate_limits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("subject_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scope", "subject_hash", name="uq_community_auth_rate_limit_subject"
        ),
    )

    op.create_table(
        "community_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("session_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_to_session_id", sa.String(length=36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=64), nullable=True),
        sa.Column("device_name", sa.String(length=120), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["rotated_to_session_id"], ["community_sessions.id"]),
        sa.ForeignKeyConstraint(
            ["user_id"], ["community_users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_token_hash", name="uq_community_sessions_session_token_hash"
        ),
        sa.UniqueConstraint(
            "refresh_token_hash", name="uq_community_sessions_refresh_token_hash"
        ),
    )
    op.create_index("ix_community_sessions_user_id", "community_sessions", ["user_id"])
    op.create_index(
        "ix_community_sessions_family_id", "community_sessions", ["family_id"]
    )

    op.create_table(
        "community_mail_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("verification_code_id", sa.String(length=36), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("template_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("authorization_reason", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_receipt", sa.String(length=255), nullable=True),
        sa.Column("verifier_outcome", sa.String(length=32), nullable=True),
        sa.Column("failure_class", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["verification_code_id"],
            ["community_verification_codes.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_community_mail_outbox_verification_code_id",
        "community_mail_outbox",
        ["verification_code_id"],
    )


def downgrade() -> None:
    """Remove the V1-1 Community account foundation in reverse dependency order."""

    op.drop_index(
        "ix_community_mail_outbox_verification_code_id",
        table_name="community_mail_outbox",
    )
    op.drop_table("community_mail_outbox")
    op.drop_index("ix_community_sessions_family_id", table_name="community_sessions")
    op.drop_index("ix_community_sessions_user_id", table_name="community_sessions")
    op.drop_table("community_sessions")
    op.drop_table("community_auth_rate_limits")
    op.drop_index(
        "ix_community_verification_codes_purpose",
        table_name="community_verification_codes",
    )
    op.drop_index(
        "ix_community_verification_codes_email_normalized",
        table_name="community_verification_codes",
    )
    op.drop_table("community_verification_codes")
    op.drop_index("ix_community_users_handle", table_name="community_users")
    op.drop_index("ix_community_users_email_normalized", table_name="community_users")
    op.drop_table("community_users")
