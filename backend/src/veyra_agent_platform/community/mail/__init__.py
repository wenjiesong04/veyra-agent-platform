"""Transactional email provider boundary for the Community service."""

from .outbox import MailOutboxDispatcher
from .provider import MailProvider, MailProviderReceipt
from .smtp import QQSmtpMailProvider

__all__ = [
    "MailOutboxDispatcher",
    "MailProvider",
    "MailProviderReceipt",
    "QQSmtpMailProvider",
]
