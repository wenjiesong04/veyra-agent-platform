"""Durable multi-subject rate limits for public authentication endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..storage.auth_repository import CommunityRateLimitRepository
from ..storage.schema import CommunityAuthRateLimit
from .tokens import AuthSecretDigester


@dataclass(frozen=True)
class RateLimitPolicy:
    """Window and temporary block policy for one durable counter."""

    maximum: int
    window: timedelta
    block_for: timedelta


@dataclass(frozen=True)
class RateLimitTarget:
    """An independently hashed email, IP, or device counter target."""

    scope: str
    raw_subject: str
    policy: RateLimitPolicy


CODE_REQUEST_POLICY = RateLimitPolicy(3, timedelta(hours=1), timedelta(hours=1))
LOGIN_POLICY = RateLimitPolicy(8, timedelta(minutes=15), timedelta(minutes=15))
CODE_ATTEMPT_POLICY = RateLimitPolicy(8, timedelta(minutes=15), timedelta(minutes=15))


class DurableRateLimiter:
    """Apply all relevant rate targets inside the caller's DB transaction."""

    def __init__(self, digester: AuthSecretDigester) -> None:
        self._digester = digester
        self._records = CommunityRateLimitRepository()

    def record_attempt(
        self, session: Session, targets: tuple[RateLimitTarget, ...], now: datetime
    ) -> bool:
        blocked = False
        for target in targets:
            subject_hash = self._digester.subject_digest(
                target.scope, target.raw_subject
            )
            record = self._records.get_or_create(
                session,
                scope=target.scope,
                subject_hash=subject_hash,
                now=now,
            )
            if not self._consume(record, target.policy, now):
                blocked = True
        session.flush()
        return not blocked

    @staticmethod
    def _consume(
        record: CommunityAuthRateLimit,
        policy: RateLimitPolicy,
        now: datetime,
    ) -> bool:
        if record.blocked_until is not None and record.blocked_until > now:
            record.request_count += 1
            record.updated_at = now
            return False
        if now - record.window_started_at >= policy.window:
            record.window_started_at = now
            record.request_count = 0
            record.blocked_until = None
        record.request_count += 1
        record.updated_at = now
        if record.request_count > policy.maximum:
            record.blocked_until = now + policy.block_for
            return False
        return True


def request_code_targets(
    *, email_normalized: str, client_ip: str, device_fingerprint: str
) -> tuple[RateLimitTarget, ...]:
    return (
        RateLimitTarget("code_request:email", email_normalized, CODE_REQUEST_POLICY),
        RateLimitTarget("code_request:ip", client_ip, CODE_REQUEST_POLICY),
        RateLimitTarget("code_request:device", device_fingerprint, CODE_REQUEST_POLICY),
    )


def login_targets(
    *, email_normalized: str, client_ip: str, device_fingerprint: str
) -> tuple[RateLimitTarget, ...]:
    return (
        RateLimitTarget("login:email", email_normalized, LOGIN_POLICY),
        RateLimitTarget("login:ip", client_ip, LOGIN_POLICY),
        RateLimitTarget("login:device", device_fingerprint, LOGIN_POLICY),
    )


def code_attempt_targets(
    *, email_normalized: str, client_ip: str, device_fingerprint: str
) -> tuple[RateLimitTarget, ...]:
    return (
        RateLimitTarget("code_attempt:email", email_normalized, CODE_ATTEMPT_POLICY),
        RateLimitTarget("code_attempt:ip", client_ip, CODE_ATTEMPT_POLICY),
        RateLimitTarget("code_attempt:device", device_fingerprint, CODE_ATTEMPT_POLICY),
    )
