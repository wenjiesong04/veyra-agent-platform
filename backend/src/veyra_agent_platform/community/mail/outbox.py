"""Durable audit record plus transient dispatch for verification email."""

from __future__ import annotations

from dataclasses import dataclass

from ..storage.database import CommunityDatabase
from ..storage.identifiers import utc_now
from ..storage.mail_outbox_repository import CommunityMailOutboxRepository
from .provider import MailProvider, VerificationMailMessage


@dataclass(frozen=True)
class PendingVerificationMail:
    """A post-commit transient dispatch request containing a plaintext code."""

    outbox_id: str
    message: VerificationMailMessage


class MailOutboxDispatcher:
    """Record provider effects without persisting reversible verification codes."""

    def __init__(self, database: CommunityDatabase, provider: MailProvider) -> None:
        self._database = database
        self._provider = provider
        self._outbox = CommunityMailOutboxRepository()

    def dispatch(self, pending: PendingVerificationMail) -> None:
        """Attempt post-commit delivery and persist only a safe receipt/outcome."""

        with self._database.transaction() as session:
            outbox = self._outbox.find_by_id(session, pending.outbox_id)
            if outbox is None:
                return
            self._outbox.mark_attempted(session, outbox, utc_now())
        try:
            receipt = self._provider.send(pending.message)
        except (
            Exception
        ) as error:  # Provider errors must not expose sensitive payloads.
            with self._database.transaction() as session:
                outbox = self._outbox.find_by_id(session, pending.outbox_id)
                if outbox is not None:
                    self._outbox.mark_failed(
                        session,
                        outbox,
                        failure_class=type(error).__name__[:64],
                        now=utc_now(),
                    )
            return
        with self._database.transaction() as session:
            outbox = self._outbox.find_by_id(session, pending.outbox_id)
            if outbox is not None:
                self._outbox.mark_delivered(
                    session,
                    outbox,
                    provider_receipt=receipt.provider_message_id[:255],
                    now=utc_now(),
                )
