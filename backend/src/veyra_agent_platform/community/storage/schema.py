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


class CommunityAgent(CommunityBase):
    """Public author-owned Agent identity in the Community registry."""

    __tablename__ = "community_agents"
    __table_args__ = (UniqueConstraint("owner_id", "slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_users.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(63))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime())


class CommunityAgentVersion(CommunityBase):
    """Immutable validated Agent package metadata and object-store pointer."""

    __tablename__ = "community_agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_agents.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[str] = mapped_column(String(32))
    source_storage_id: Mapped[str] = mapped_column(String(64), unique=True)
    source_hash: Mapped[str] = mapped_column(String(64))
    behavior_hash: Mapped[str] = mapped_column(String(64))
    lock_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="published")
    scan_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    published_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class CommunityPlugin(CommunityBase):
    """Public author-owned declarative Plugin Pack identity."""

    __tablename__ = "community_plugins"
    __table_args__ = (UniqueConstraint("owner_id", "slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_users.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(63))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime())


class CommunityPluginVersion(CommunityBase):
    """Immutable Plugin Pack bytes and public manifest summary."""

    __tablename__ = "community_plugin_versions"
    __table_args__ = (UniqueConstraint("plugin_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    plugin_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_plugins.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[str] = mapped_column(String(32))
    package_storage_id: Mapped[str] = mapped_column(String(64), unique=True)
    package_hash: Mapped[str] = mapped_column(String(64))
    manifest_json: Mapped[str] = mapped_column(Text)
    skill_count: Mapped[int] = mapped_column(Integer)
    mcp_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="published")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    published_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class CommunityPluginModeration(CommunityBase):
    """Append-only receipt for a moderator's Plugin Pack decision."""

    __tablename__ = "community_plugin_moderations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_plugin_versions.id", ondelete="CASCADE"),
        index=True,
    )
    moderator_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_users.id", ondelete="RESTRICT"),
        index=True,
    )
    action: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())


class CommunityAgentModeration(CommunityBase):
    """Append-only receipt for a moderator's package decision."""

    __tablename__ = "community_agent_moderations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_agent_versions.id", ondelete="CASCADE"),
        index=True,
    )
    moderator_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_users.id", ondelete="RESTRICT"),
        index=True,
    )
    action: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())


class CommunityAgentFork(CommunityBase):
    """Immutable edge from a published source version to a forked version."""

    __tablename__ = "community_agent_forks"
    __table_args__ = (UniqueConstraint("target_version_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_agent_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    target_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_agent_versions.id", ondelete="CASCADE"),
        index=True,
    )
    forked_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())


class CommunityAgentStar(CommunityBase):
    """One user's version-bound Community star."""

    __tablename__ = "community_agent_stars"
    __table_args__ = (UniqueConstraint("version_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_agent_versions.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())


class CommunityAgentReview(CommunityBase):
    """A version-bound rating and review authored by a Community user."""

    __tablename__ = "community_agent_reviews"
    __table_args__ = (UniqueConstraint("version_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_agent_versions.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_users.id", ondelete="CASCADE"), index=True
    )
    rating: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime())


class CommunityAgentReport(CommunityBase):
    """A durable user report awaiting a future moderation queue."""

    __tablename__ = "community_agent_reports"
    __table_args__ = (UniqueConstraint("version_id", "reporter_id", "reason"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_agent_versions.id", ondelete="CASCADE"),
        index=True,
    )
    reporter_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("community_users.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[str] = mapped_column(String(64))
    details: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())


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
