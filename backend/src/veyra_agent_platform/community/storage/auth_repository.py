"""Repositories for verification codes, rate limits, and opaque sessions."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .identifiers import new_uuid7
from .schema import CommunityAuthRateLimit, CommunitySession, CommunityVerificationCode


class CommunityVerificationCodeRepository:
    """Persist one-time code lifecycle state without retaining plaintext codes."""

    def latest_active(
        self,
        session: Session,
        *,
        email_normalized: str,
        purpose: str,
        now: datetime,
        lock: bool = False,
    ) -> CommunityVerificationCode | None:
        statement: Select[tuple[CommunityVerificationCode]] = (
            select(CommunityVerificationCode)
            .where(
                CommunityVerificationCode.email_normalized == email_normalized,
                CommunityVerificationCode.purpose == purpose,
                CommunityVerificationCode.consumed_at.is_(None),
                CommunityVerificationCode.superseded_at.is_(None),
                CommunityVerificationCode.expires_at > now,
            )
            .order_by(CommunityVerificationCode.issued_at.desc())
            .limit(1)
        )
        if lock:
            statement = statement.with_for_update()
        return session.scalar(statement)

    def supersede_active(
        self,
        session: Session,
        *,
        email_normalized: str,
        purpose: str,
        now: datetime,
    ) -> None:
        active_codes = session.scalars(
            select(CommunityVerificationCode)
            .where(
                CommunityVerificationCode.email_normalized == email_normalized,
                CommunityVerificationCode.purpose == purpose,
                CommunityVerificationCode.consumed_at.is_(None),
                CommunityVerificationCode.superseded_at.is_(None),
            )
            .with_for_update()
        ).all()
        for code in active_codes:
            code.superseded_at = now

    def create(
        self,
        session: Session,
        *,
        email_normalized: str,
        purpose: str,
        code_hmac: str,
        issued_at: datetime,
        expires_at: datetime,
        resend_available_at: datetime,
        requested_ip_hash: str,
        requested_device_hash: str,
        max_attempts: int,
    ) -> CommunityVerificationCode:
        code = CommunityVerificationCode(
            id=new_uuid7(),
            email_normalized=email_normalized,
            purpose=purpose,
            code_hmac=code_hmac,
            issued_at=issued_at,
            expires_at=expires_at,
            resend_available_at=resend_available_at,
            attempts=0,
            max_attempts=max_attempts,
            requested_ip_hash=requested_ip_hash,
            requested_device_hash=requested_device_hash,
        )
        session.add(code)
        session.flush()
        return code

    def consume(
        self, session: Session, code: CommunityVerificationCode, now: datetime
    ) -> None:
        code.consumed_at = now
        session.flush()

    def record_failed_attempt(
        self,
        session: Session,
        code: CommunityVerificationCode,
        now: datetime,
    ) -> None:
        code.attempts += 1
        if code.attempts >= code.max_attempts:
            code.consumed_at = now
        session.flush()


class CommunityRateLimitRepository:
    """Store rate-limit counters with a unique subject key per policy scope."""

    def get_or_create(
        self,
        session: Session,
        *,
        scope: str,
        subject_hash: str,
        now: datetime,
    ) -> CommunityAuthRateLimit:
        record = session.scalar(
            select(CommunityAuthRateLimit)
            .where(
                CommunityAuthRateLimit.scope == scope,
                CommunityAuthRateLimit.subject_hash == subject_hash,
            )
            .with_for_update()
        )
        if record is not None:
            return record

        created = CommunityAuthRateLimit(
            id=new_uuid7(),
            scope=scope,
            subject_hash=subject_hash,
            window_started_at=now,
            request_count=0,
            updated_at=now,
        )
        try:
            with session.begin_nested():
                session.add(created)
                session.flush()
            return created
        except IntegrityError as error:
            record = session.scalar(
                select(CommunityAuthRateLimit)
                .where(
                    CommunityAuthRateLimit.scope == scope,
                    CommunityAuthRateLimit.subject_hash == subject_hash,
                )
                .with_for_update()
            )
            if record is None:
                raise RuntimeError(
                    "rate-limit record lost after unique-key race"
                ) from error
            return record


class CommunitySessionRepository:
    """Persist and revoke opaque session-token lineages."""

    def create(
        self,
        session: Session,
        *,
        user_id: str,
        family_id: str,
        session_token_hash: str,
        refresh_token_hash: str,
        csrf_token_hash: str,
        session_expires_at: datetime,
        refresh_expires_at: datetime,
        device_name: str | None,
        user_agent: str,
        ip_hash: str,
        now: datetime,
    ) -> CommunitySession:
        record = CommunitySession(
            id=new_uuid7(),
            user_id=user_id,
            family_id=family_id,
            session_token_hash=session_token_hash,
            refresh_token_hash=refresh_token_hash,
            csrf_token_hash=csrf_token_hash,
            session_expires_at=session_expires_at,
            refresh_expires_at=refresh_expires_at,
            created_at=now,
            last_seen_at=now,
            device_name=device_name,
            user_agent=user_agent,
            ip_hash=ip_hash,
        )
        session.add(record)
        session.flush()
        return record

    def find_by_session_hash(
        self, session: Session, session_token_hash: str, *, lock: bool = False
    ) -> CommunitySession | None:
        statement: Select[tuple[CommunitySession]] = select(CommunitySession).where(
            CommunitySession.session_token_hash == session_token_hash
        )
        if lock:
            statement = statement.with_for_update()
        return session.scalar(statement)

    def find_by_refresh_hash(
        self, session: Session, refresh_token_hash: str, *, lock: bool = False
    ) -> CommunitySession | None:
        statement: Select[tuple[CommunitySession]] = select(CommunitySession).where(
            CommunitySession.refresh_token_hash == refresh_token_hash
        )
        if lock:
            statement = statement.with_for_update()
        return session.scalar(statement)

    def rotate(
        self,
        session: Session,
        *,
        previous: CommunitySession,
        replacement: CommunitySession,
        now: datetime,
    ) -> None:
        previous.rotated_at = now
        previous.rotated_to_session_id = replacement.id
        previous.revoke_reason = "rotated"
        session.flush()

    def revoke(
        self,
        session: Session,
        record: CommunitySession,
        *,
        now: datetime,
        reason: str,
    ) -> None:
        if record.revoked_at is None:
            record.revoked_at = now
            record.revoke_reason = reason
            session.flush()

    def revoke_family(
        self,
        session: Session,
        *,
        family_id: str,
        now: datetime,
        reason: str,
    ) -> int:
        records: Sequence[CommunitySession] = session.scalars(
            select(CommunitySession)
            .where(CommunitySession.family_id == family_id)
            .with_for_update()
        ).all()
        revoked_count = 0
        for record in records:
            if record.revoked_at is None:
                record.revoked_at = now
                record.revoke_reason = reason
                revoked_count += 1
        session.flush()
        return revoked_count

    def revoke_all_for_user(
        self,
        session: Session,
        *,
        user_id: str,
        now: datetime,
        reason: str,
    ) -> int:
        records: Sequence[CommunitySession] = session.scalars(
            select(CommunitySession)
            .where(CommunitySession.user_id == user_id)
            .with_for_update()
        ).all()
        revoked_count = 0
        for record in records:
            if record.revoked_at is None:
                record.revoked_at = now
                record.revoke_reason = reason
                revoked_count += 1
        session.flush()
        return revoked_count

    def list_for_user(
        self, session: Session, user_id: str
    ) -> Sequence[CommunitySession]:
        return session.scalars(
            select(CommunitySession)
            .where(CommunitySession.user_id == user_id)
            .order_by(CommunitySession.last_seen_at.desc())
        ).all()

    def touch(self, session: Session, record: CommunitySession, now: datetime) -> None:
        record.last_seen_at = now
        session.flush()
