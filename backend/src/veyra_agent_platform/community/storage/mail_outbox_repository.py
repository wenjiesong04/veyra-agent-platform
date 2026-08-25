"""Repository for non-secret transactional-mail delivery records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .identifiers import new_uuid7
from .schema import CommunityMailOutbox


class CommunityMailOutboxRepository:
    """Persist authorization, provider receipt, and verifier outcome for mail."""

    def create(
        self,
        session: Session,
        *,
        verification_code_id: str,
        recipient_email: str,
        purpose: str,
        template_name: str,
        now: datetime,
    ) -> CommunityMailOutbox:
        outbox = CommunityMailOutbox(
            id=new_uuid7(),
            verification_code_id=verification_code_id,
            recipient_email=recipient_email,
            purpose=purpose,
            template_name=template_name,
            status="authorized",
            authorized_at=now,
            authorization_reason="user_requested_authentication_email",
            created_at=now,
        )
        session.add(outbox)
        session.flush()
        return outbox

    def mark_attempted(
        self, session: Session, outbox: CommunityMailOutbox, now: datetime
    ) -> None:
        outbox.status = "attempted"
        outbox.attempted_at = now
        session.flush()

    def mark_delivered(
        self,
        session: Session,
        outbox: CommunityMailOutbox,
        *,
        provider_receipt: str,
        now: datetime,
    ) -> None:
        outbox.status = "delivered"
        outbox.delivered_at = now
        outbox.provider_receipt = provider_receipt
        outbox.verifier_outcome = "accepted"
        outbox.failure_class = None
        session.flush()

    def mark_failed(
        self,
        session: Session,
        outbox: CommunityMailOutbox,
        *,
        failure_class: str,
        now: datetime,
    ) -> None:
        outbox.status = "failed"
        outbox.attempted_at = now
        outbox.verifier_outcome = "not_accepted"
        outbox.failure_class = failure_class
        session.flush()

    def find_by_id(
        self, session: Session, outbox_id: str
    ) -> CommunityMailOutbox | None:
        return session.get(CommunityMailOutbox, outbox_id)
