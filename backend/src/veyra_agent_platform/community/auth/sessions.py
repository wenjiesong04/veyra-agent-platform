"""Opaque session issuance, rotation, reuse detection, and revocation."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..storage.auth_repository import CommunitySessionRepository
from ..storage.database import CommunityDatabase
from ..storage.identifiers import new_uuid7, utc_now
from ..storage.schema import CommunitySession
from ..storage.user_repository import CommunityUserRepository
from .errors import AuthenticationFailure, CsrfFailure
from .tokens import AuthSecretDigester, SessionSecrets


@dataclass(frozen=True)
class ClientContext:
    """Non-authoritative request metadata used for risk controls and device display."""

    client_ip: str
    device_fingerprint: str
    device_name: str | None
    user_agent: str


@dataclass(frozen=True)
class AuthenticatedSession:
    """Server-validated identity produced only from an opaque session cookie."""

    user_id: str
    session_id: str
    csrf_token_hash: str


@dataclass(frozen=True)
class SessionIssue:
    """Transient cookies for an issued or rotated browser session."""

    user_id: str
    session_id: str
    secrets: SessionSecrets


@dataclass(frozen=True)
class DeviceSession:
    """Safe, device-visible projection of one server-side session."""

    id: str
    device_name: str | None
    user_agent: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    current: bool


class SessionManager:
    """Operate only on server-hashed opaque tokens and explicit lineage state."""

    def __init__(
        self,
        database: CommunityDatabase,
        digester: AuthSecretDigester,
        *,
        session_ttl: timedelta,
        refresh_ttl: timedelta,
    ) -> None:
        self._database = database
        self._digester = digester
        self._session_ttl = session_ttl
        self._refresh_ttl = refresh_ttl
        self._sessions = CommunitySessionRepository()
        self._users = CommunityUserRepository()

    def issue(self, user_id: str, context: ClientContext) -> SessionIssue:
        """Create a fresh session family after registration or successful login."""

        secrets = SessionSecrets.create()
        now = utc_now()
        with self._database.transaction() as session:
            record = self._create_record(
                session,
                user_id=user_id,
                family_id=new_uuid7(),
                secrets=secrets,
                context=context,
                now=now,
            )
            return SessionIssue(user_id=user_id, session_id=record.id, secrets=secrets)

    def authenticate(self, session_token: str) -> AuthenticatedSession:
        """Validate an access cookie without accepting headers or browser storage."""

        token_hash = self._digester.opaque_token_digest("session", session_token)
        now = utc_now()
        with self._database.transaction() as session:
            record = self._sessions.find_by_session_hash(session, token_hash, lock=True)
            if record is None or not self._is_current(record, now):
                raise AuthenticationFailure()
            user = self._users.find_by_id(session, record.user_id)
            if user is None or user.disabled_at is not None:
                raise AuthenticationFailure()
            self._sessions.touch(session, record, now)
            return AuthenticatedSession(
                user_id=record.user_id,
                session_id=record.id,
                csrf_token_hash=record.csrf_token_hash,
            )

    def require_csrf(
        self, authenticated: AuthenticatedSession, csrf_token: str
    ) -> None:
        """Require a session-bound double-submit CSRF token for unsafe requests."""

        supplied_hash = self._digester.opaque_token_digest("csrf", csrf_token)
        if not hmac.compare_digest(authenticated.csrf_token_hash, supplied_hash):
            raise CsrfFailure()

    def rotate(
        self,
        *,
        refresh_token: str,
        csrf_token: str,
        context: ClientContext,
    ) -> SessionIssue:
        """Rotate a refresh token; old-token reuse revokes the whole family."""

        refresh_hash = self._digester.opaque_token_digest("refresh", refresh_token)
        csrf_hash = self._digester.opaque_token_digest("csrf", csrf_token)
        now = utc_now()
        secrets = SessionSecrets.create()
        reuse_detected = False
        issued: SessionIssue | None = None
        with self._database.transaction() as session:
            previous = self._sessions.find_by_refresh_hash(
                session, refresh_hash, lock=True
            )
            if previous is None:
                raise AuthenticationFailure()
            if previous.rotated_at is not None:
                self._sessions.revoke_family(
                    session,
                    family_id=previous.family_id,
                    now=now,
                    reason="refresh_token_reuse",
                )
                reuse_detected = True
            elif not self._is_refreshable(previous, now):
                raise AuthenticationFailure()
            elif not hmac.compare_digest(previous.csrf_token_hash, csrf_hash):
                raise CsrfFailure()
            else:
                user = self._users.find_by_id(session, previous.user_id)
                if user is None or user.disabled_at is not None:
                    raise AuthenticationFailure()
                replacement = self._create_record(
                    session,
                    user_id=previous.user_id,
                    family_id=previous.family_id,
                    secrets=secrets,
                    context=context,
                    now=now,
                )
                self._sessions.rotate(
                    session,
                    previous=previous,
                    replacement=replacement,
                    now=now,
                )
                issued = SessionIssue(
                    user_id=previous.user_id,
                    session_id=replacement.id,
                    secrets=secrets,
                )
        if reuse_detected or issued is None:
            raise AuthenticationFailure()
        return issued

    def revoke_current(self, authenticated: AuthenticatedSession, reason: str) -> None:
        """Revoke exactly the active session used by the current request."""

        with self._database.transaction() as session:
            record = session.get(
                CommunitySession, authenticated.session_id, with_for_update=True
            )
            if record is not None and record.user_id == authenticated.user_id:
                self._sessions.revoke(session, record, now=utc_now(), reason=reason)

    def revoke_refresh_family(
        self, *, refresh_token: str, csrf_token: str, reason: str
    ) -> bool:
        """Revoke a refresh lineage even when its short-lived access has expired."""

        refresh_hash = self._digester.opaque_token_digest("refresh", refresh_token)
        csrf_hash = self._digester.opaque_token_digest("csrf", csrf_token)
        with self._database.transaction() as session:
            record = self._sessions.find_by_refresh_hash(
                session, refresh_hash, lock=True
            )
            if record is None:
                return False
            if not hmac.compare_digest(record.csrf_token_hash, csrf_hash):
                raise CsrfFailure()
            self._sessions.revoke_family(
                session,
                family_id=record.family_id,
                now=utc_now(),
                reason=reason,
            )
            return True

    def revoke_user_sessions(self, user_id: str, reason: str) -> None:
        """Revoke all sessions after a password reset or account safety event."""

        with self._database.transaction() as session:
            self._sessions.revoke_all_for_user(
                session,
                user_id=user_id,
                now=utc_now(),
                reason=reason,
            )

    def list_for_user(
        self, user_id: str, current_session_id: str
    ) -> tuple[DeviceSession, ...]:
        """List safe metadata; raw IPs and tokens never leave persistence."""

        with self._database.transaction() as session:
            records = self._sessions.list_for_user(session, user_id)
            now = utc_now()
            return tuple(
                DeviceSession(
                    id=record.id,
                    device_name=record.device_name,
                    user_agent=record.user_agent,
                    created_at=record.created_at,
                    last_seen_at=record.last_seen_at,
                    expires_at=record.refresh_expires_at,
                    current=record.id == current_session_id,
                )
                for record in records
                if (
                    record.revoked_at is None
                    and record.rotated_at is None
                    and record.refresh_expires_at > now
                )
            )

    def revoke_named_session(
        self, authenticated: AuthenticatedSession, target_session_id: str
    ) -> bool:
        """Revoke one owned session and report whether it existed for this account."""

        with self._database.transaction() as session:
            record = session.get(
                CommunitySession, target_session_id, with_for_update=True
            )
            if record is None or record.user_id != authenticated.user_id:
                return False
            self._sessions.revoke(session, record, now=utc_now(), reason="user_revoked")
            return True

    def _create_record(
        self,
        session: Session,
        *,
        user_id: str,
        family_id: str,
        secrets: SessionSecrets,
        context: ClientContext,
        now: datetime,
    ) -> CommunitySession:
        session_expires_at = now + self._session_ttl
        refresh_expires_at = now + self._refresh_ttl
        return self._sessions.create(
            session,
            user_id=user_id,
            family_id=family_id,
            session_token_hash=self._digester.opaque_token_digest(
                "session", secrets.session_token
            ),
            refresh_token_hash=self._digester.opaque_token_digest(
                "refresh", secrets.refresh_token
            ),
            csrf_token_hash=self._digester.opaque_token_digest(
                "csrf", secrets.csrf_token
            ),
            session_expires_at=session_expires_at,
            refresh_expires_at=refresh_expires_at,
            device_name=context.device_name,
            user_agent=context.user_agent,
            ip_hash=self._digester.digest("session_ip", context.client_ip),
            now=now,
        )

    @staticmethod
    def _is_current(record: CommunitySession | None, now: datetime) -> bool:
        return (
            record is not None
            and record.revoked_at is None
            and record.rotated_at is None
            and record.session_expires_at > now
        )

    @staticmethod
    def _is_refreshable(record: CommunitySession, now: datetime) -> bool:
        return record.revoked_at is None and record.refresh_expires_at > now
