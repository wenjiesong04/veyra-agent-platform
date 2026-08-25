"""Bounded Community registration, login, recovery, and session workflows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..accounts.identifiers import (
    normalize_display_name,
    normalize_email,
    normalize_handle,
)
from ..accounts.profiles import AccountProfile
from ..mail.outbox import MailOutboxDispatcher, PendingVerificationMail
from ..mail.provider import VerificationMailMessage
from ..storage.database import CommunityDatabase
from ..storage.identifiers import utc_now
from ..storage.mail_outbox_repository import CommunityMailOutboxRepository
from ..storage.schema import CommunityUser
from ..storage.user_repository import CommunityUserRepository
from .codes import IssuedVerificationCode, VerificationCodeService, VerificationPurpose
from .errors import (
    AuthenticationFailure,
    RegistrationUnavailable,
    VerificationCodeFailure,
)
from .passwords import PasswordManager
from .rate_limits import (
    DurableRateLimiter,
    code_attempt_targets,
    login_targets,
    request_code_targets,
)
from .sessions import ClientContext, SessionIssue, SessionManager
from .tokens import AuthSecretDigester


@dataclass(frozen=True)
class AuthenticatedAccount:
    """Profile plus transient issued cookies after login or registration."""

    profile: AccountProfile
    session: SessionIssue


class CommunityAuthWorkflows:
    """Coordinate repositories without ever exposing raw codes, passwords, or tokens."""

    def __init__(
        self,
        database: CommunityDatabase,
        *,
        auth_hmac_secret: str,
        mail_dispatcher: MailOutboxDispatcher,
        session_ttl: timedelta,
        refresh_ttl: timedelta,
    ) -> None:
        self._database = database
        self._digester = AuthSecretDigester(auth_hmac_secret)
        self._users = CommunityUserRepository()
        self._codes = VerificationCodeService(self._digester)
        self._rates = DurableRateLimiter(self._digester)
        self._passwords = PasswordManager()
        self._outbox = CommunityMailOutboxRepository()
        self._dispatcher = mail_dispatcher
        self.sessions = SessionManager(
            database,
            self._digester,
            session_ttl=session_ttl,
            refresh_ttl=refresh_ttl,
        )

    def request_registration_code(self, email: str, context: ClientContext) -> None:
        """Accept a registration request without revealing email-account existence."""

        normalized_email = normalize_email(email)
        self._request_code(
            normalized_email,
            VerificationPurpose.REGISTRATION,
            context,
            should_send=lambda user_exists: not user_exists,
        )

    def request_password_reset_code(self, email: str, context: ClientContext) -> None:
        """Accept a reset request without revealing whether an account exists."""

        normalized_email = normalize_email(email)
        self._request_code(
            normalized_email,
            VerificationPurpose.PASSWORD_RESET,
            context,
            should_send=lambda user_exists: user_exists,
        )

    def register(
        self,
        *,
        email: str,
        handle: str,
        password: str,
        verification_code: str,
        display_name: str | None,
        context: ClientContext,
    ) -> AuthenticatedAccount:
        """Consume a registration code, create an account, and issue a session."""

        normalized_email = normalize_email(email)
        normalized_handle = normalize_handle(handle)
        normalized_display_name = (
            normalize_display_name(display_name) if display_name is not None else None
        )
        password_hash = self._passwords.hash_new_password(password)
        user_id: str | None = None
        try:
            with self._database.transaction() as session:
                now = utc_now()
                allowed = self._rates.record_attempt(
                    session,
                    code_attempt_targets(
                        email_normalized=normalized_email,
                        client_ip=context.client_ip,
                        device_fingerprint=context.device_fingerprint,
                    ),
                    now,
                )
                code_record = (
                    self._codes.consume(
                        session,
                        email_normalized=normalized_email,
                        purpose=VerificationPurpose.REGISTRATION,
                        supplied_code=verification_code,
                        now=now,
                    )
                    if allowed
                    else None
                )
                if code_record is None:
                    continue_registration = False
                else:
                    existing_email = self._users.find_by_email(
                        session, normalized_email
                    )
                    existing_handle = self._users.find_by_handle(
                        session, normalized_handle
                    )
                    continue_registration = (
                        existing_email is None and existing_handle is None
                    )
                if continue_registration:
                    user = self._users.create(
                        session,
                        email_normalized=normalized_email,
                        handle=normalized_handle,
                        password_hash=password_hash,
                        display_name=normalized_display_name,
                        now=now,
                    )
                    user_id = user.id
        except IntegrityError as error:
            raise RegistrationUnavailable() from error
        if user_id is None:
            raise RegistrationUnavailable()
        session_issue = self.sessions.issue(user_id, context)
        return AuthenticatedAccount(
            profile=AccountProfile(
                id=user_id,
                email=normalized_email,
                handle=normalized_handle,
                display_name=normalized_display_name,
            ),
            session=session_issue,
        )

    def login(
        self, *, email: str, password: str, context: ClientContext
    ) -> AuthenticatedAccount:
        """Authenticate with a generic failure shape for missing or wrong accounts."""

        normalized_email = normalize_email(email)
        user_id: str | None = None
        profile: AccountProfile | None = None
        with self._database.transaction() as session:
            now = utc_now()
            allowed = self._rates.record_attempt(
                session,
                login_targets(
                    email_normalized=normalized_email,
                    client_ip=context.client_ip,
                    device_fingerprint=context.device_fingerprint,
                ),
                now,
            )
            user = self._users.find_by_email(session, normalized_email)
            stored_hash = (
                user.password_hash
                if user is not None
                and user.email_verified_at is not None
                and user.disabled_at is None
                else None
            )
            password_matches = self._passwords.verify(stored_hash, password)
            if allowed and user is not None and password_matches:
                user_id = user.id
                profile = _profile_from_user(user)
        if user_id is None or profile is None:
            raise AuthenticationFailure()
        return AuthenticatedAccount(
            profile=profile,
            session=self.sessions.issue(user_id, context),
        )

    def confirm_password_reset(
        self,
        *,
        email: str,
        verification_code: str,
        new_password: str,
        context: ClientContext,
    ) -> None:
        """Consume a reset code, replace the Argon2id hash, and revoke all sessions."""

        normalized_email = normalize_email(email)
        password_hash = self._passwords.hash_new_password(new_password)
        reset_user_id: str | None = None
        with self._database.transaction() as session:
            now = utc_now()
            allowed = self._rates.record_attempt(
                session,
                code_attempt_targets(
                    email_normalized=normalized_email,
                    client_ip=context.client_ip,
                    device_fingerprint=context.device_fingerprint,
                ),
                now,
            )
            code_record = (
                self._codes.consume(
                    session,
                    email_normalized=normalized_email,
                    purpose=VerificationPurpose.PASSWORD_RESET,
                    supplied_code=verification_code,
                    now=now,
                )
                if allowed
                else None
            )
            user = self._users.find_by_email(session, normalized_email)
            if (
                code_record is not None
                and user is not None
                and user.disabled_at is None
            ):
                self._users.update_password(
                    session,
                    user,
                    password_hash=password_hash,
                    now=now,
                )
                reset_user_id = user.id
        if reset_user_id is None:
            raise VerificationCodeFailure()
        self.sessions.revoke_user_sessions(reset_user_id, "password_reset")

    def _request_code(
        self,
        email_normalized: str,
        purpose: VerificationPurpose,
        context: ClientContext,
        *,
        should_send: Callable[[bool], bool],
    ) -> None:
        pending: PendingVerificationMail | None = None
        with self._database.transaction() as session:
            now = utc_now()
            allowed = self._rates.record_attempt(
                session,
                request_code_targets(
                    email_normalized=email_normalized,
                    client_ip=context.client_ip,
                    device_fingerprint=context.device_fingerprint,
                ),
                now,
            )
            user_exists = (
                self._users.find_by_email(session, email_normalized) is not None
            )
            issued = (
                self._codes.issue_if_resend_allowed(
                    session,
                    email_normalized=email_normalized,
                    purpose=purpose,
                    client_ip_hash=self._digester.digest(
                        "verification_ip", context.client_ip
                    ),
                    device_hash=self._digester.digest(
                        "verification_device", context.device_fingerprint
                    ),
                    now=now,
                )
                if allowed and should_send(user_exists)
                else None
            )
            if issued is not None:
                pending = self._prepare_pending_mail(session, issued, now)
        if pending is not None:
            self._dispatcher.dispatch(pending)

    def _prepare_pending_mail(
        self,
        session: Session,
        issued: IssuedVerificationCode,
        now: datetime,
    ) -> PendingVerificationMail:
        outbox = self._outbox.create(
            session,
            verification_code_id=issued.code_id,
            recipient_email=issued.email_normalized,
            purpose=issued.purpose.value,
            template_name=f"{issued.purpose.value}_code_v1",
            now=now,
        )
        return PendingVerificationMail(
            outbox_id=outbox.id,
            message=VerificationMailMessage(
                recipient_email=issued.email_normalized,
                purpose=issued.purpose,
                verification_code=issued.code,
            ),
        )


def _profile_from_user(user: CommunityUser) -> AccountProfile:
    return AccountProfile(
        id=user.id,
        email=user.email_normalized,
        handle=user.handle,
        display_name=user.display_name,
    )
