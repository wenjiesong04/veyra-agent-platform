"""Typed, non-logging boundary for transactional mail providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..auth.codes import VerificationPurpose


class MailProviderFailure(RuntimeError):
    """A provider could not accept a transactional mail message."""


@dataclass(frozen=True)
class VerificationMailMessage:
    """Transient rendered mail input; verification code is never persisted here."""

    recipient_email: str
    purpose: VerificationPurpose
    verification_code: str


@dataclass(frozen=True)
class MailProviderReceipt:
    """Provider acceptance result safe to retain in a delivery record."""

    provider_message_id: str


class MailProvider(Protocol):
    """Send a message without logging its recipient, credentials, or code."""

    def send(self, message: VerificationMailMessage) -> MailProviderReceipt:
        """Submit a transactional email and return a non-secret receipt."""
