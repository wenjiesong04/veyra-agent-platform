"""One-time email-code lifecycle logic and HMAC comparison."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy.orm import Session

from ..storage.auth_repository import CommunityVerificationCodeRepository
from ..storage.schema import CommunityVerificationCode
from .tokens import AuthSecretDigester, new_six_digit_code


class VerificationPurpose(StrEnum):
    """Purposes must remain explicit so codes cannot cross auth workflows."""

    REGISTRATION = "registration"
    PASSWORD_RESET = "password_reset"


@dataclass(frozen=True)
class IssuedVerificationCode:
    """Transient code body that must be sent without being stored in plaintext."""

    code_id: str
    email_normalized: str
    purpose: VerificationPurpose
    code: str


class VerificationCodeService:
    """Issue and consume purpose-bound, finite-attempt email codes."""

    _ttl = timedelta(minutes=10)
    _resend_delay = timedelta(seconds=60)
    _max_attempts = 5

    def __init__(self, digester: AuthSecretDigester) -> None:
        self._digester = digester
        self._codes = CommunityVerificationCodeRepository()

    def issue_if_resend_allowed(
        self,
        session: Session,
        *,
        email_normalized: str,
        purpose: VerificationPurpose,
        client_ip_hash: str,
        device_hash: str,
        now: datetime,
    ) -> IssuedVerificationCode | None:
        active = self._codes.latest_active(
            session,
            email_normalized=email_normalized,
            purpose=purpose.value,
            now=now,
            lock=True,
        )
        if active is not None and active.resend_available_at > now:
            return None
        self._codes.supersede_active(
            session,
            email_normalized=email_normalized,
            purpose=purpose.value,
            now=now,
        )
        plaintext_code = new_six_digit_code()
        record = self._codes.create(
            session,
            email_normalized=email_normalized,
            purpose=purpose.value,
            code_hmac=self._digester.code_digest(
                purpose.value, email_normalized, plaintext_code
            ),
            issued_at=now,
            expires_at=now + self._ttl,
            resend_available_at=now + self._resend_delay,
            requested_ip_hash=client_ip_hash,
            requested_device_hash=device_hash,
            max_attempts=self._max_attempts,
        )
        return IssuedVerificationCode(
            code_id=record.id,
            email_normalized=email_normalized,
            purpose=purpose,
            code=plaintext_code,
        )

    def consume(
        self,
        session: Session,
        *,
        email_normalized: str,
        purpose: VerificationPurpose,
        supplied_code: str,
        now: datetime,
    ) -> CommunityVerificationCode | None:
        record = self._codes.latest_active(
            session,
            email_normalized=email_normalized,
            purpose=purpose.value,
            now=now,
            lock=True,
        )
        if record is None:
            return None
        supplied_digest = self._digester.code_digest(
            purpose.value, email_normalized, supplied_code
        )
        if not hmac.compare_digest(record.code_hmac, supplied_digest):
            self._codes.record_failed_attempt(session, record, now)
            return None
        self._codes.consume(session, record, now)
        return record
