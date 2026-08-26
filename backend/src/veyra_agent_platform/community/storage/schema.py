"""Community database mappings shared by repositories and test setup."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .utc_datetime import UtcDateTime


class CommunityBase(DeclarativeBase):
    """Base class for Community-owned relational tables."""


class CommunityUser(CommunityBase):
    """Private account identity and credential record."""

    __tablename__ = "community_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email_normalized: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    handle: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    password_hash: Mapped[str] = mapped_column(Text)
    email_verified_at: Mapped[datetime] = mapped_column(UtcDateTime())
    disabled_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime())


class CommunityVerificationCode(CommunityBase):
    """A one-time email verification or recovery code, HMAC-only at rest."""

    __tablename__ = "community_verification_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email_normalized: Mapped[str] = mapped_column(String(320), index=True)
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    code_hmac: Mapped[str] = mapped_column(String(64))
    issued_at: Mapped[datetime] = mapped_column(UtcDateTime())
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime())
    resend_available_at: Mapped[datetime] = mapped_column(UtcDateTime())
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    consumed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    superseded_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    requested_ip_hash: Mapped[str] = mapped_column(String(64))
    requested_device_hash: Mapped[str] = mapped_column(String(64))


class CommunityAuthRateLimit(CommunityBase):
    """Durable per-subject counters for public authentication operations."""

    __tablename__ = "community_auth_rate_limits"
    __table_args__ = (UniqueConstraint("scope", "subject_hash"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scope: Mapped[str] = mapped_column(String(64))
    subject_hash: Mapped[str] = mapped_column(String(64))
    window_started_at: Mapped[datetime] = mapped_column(UtcDateTime())
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_until: Mapped[datetime | None] = mapped_column(UtcDateTime())
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime())


class CommunitySession(CommunityBase):
    """Opaque browser session and refresh-token rotation lineage."""

    __tablename__ = "community_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    session_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    session_expires_at: Mapped[datetime] = mapped_column(UtcDateTime())
    refresh_expires_at: Mapped[datetime] = mapped_column(UtcDateTime())
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    last_seen_at: Mapped[datetime] = mapped_column(UtcDateTime())
    rotated_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    rotated_to_session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("community_sessions.id"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    revoke_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(512))
    ip_hash: Mapped[str] = mapped_column(String(64))


class CommunityAvatar(CommunityBase):
    """Private storage metadata for one user's public avatar."""

    __tablename__ = "community_avatars"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    storage_id: Mapped[str] = mapped_column(String(64), unique=True)
    media_type: Mapped[str] = mapped_column(String(32))
    byte_size: Mapped[int] = mapped_column(Integer)
    etag: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime())


class CommunityMailOutbox(CommunityBase):
    """Durable authorization and delivery record for transactional email."""

    __tablename__ = "community_mail_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    verification_code_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_verification_codes.id", ondelete="RESTRICT"),
        index=True,
    )
    recipient_email: Mapped[str] = mapped_column(String(320))
    purpose: Mapped[str] = mapped_column(String(32))
    template_name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    authorized_at: Mapped[datetime] = mapped_column(UtcDateTime())
    authorization_reason: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    attempted_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    delivered_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    provider_receipt: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verifier_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
