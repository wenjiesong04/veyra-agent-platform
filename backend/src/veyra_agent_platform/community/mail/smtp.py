"""QQ SMTP transactional-mail adapter with TLS and no secret logging."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid

from .config import MailSettings
from .provider import (
    MailProviderFailure,
    MailProviderReceipt,
    VerificationMailMessage,
)


class QQSmtpMailProvider:
    """Deliver V1 verification messages through configured QQ-compatible SMTP."""

    def __init__(self, settings: MailSettings | None = None) -> None:
        self._settings = settings or MailSettings()

    def send(self, message: VerificationMailMessage) -> MailProviderReceipt:
        server = self._settings.server
        if not self._settings.is_configured or server is None:
            raise MailProviderFailure("SMTP delivery is not configured")
        email = self._render_message(message)
        context = ssl.create_default_context()
        try:
            if self._settings.use_ssl:
                with smtplib.SMTP_SSL(
                    server,
                    self._settings.port,
                    context=context,
                    timeout=self._settings.timeout_seconds,
                ) as client:
                    self._authenticate_and_send(client, email)
            else:
                with smtplib.SMTP(
                    server,
                    self._settings.port,
                    timeout=self._settings.timeout_seconds,
                ) as client:
                    client.starttls(context=context)
                    self._authenticate_and_send(client, email)
        except (OSError, smtplib.SMTPException) as error:
            raise MailProviderFailure("SMTP delivery was not accepted") from error
        return MailProviderReceipt(provider_message_id=email["Message-ID"])

    def _authenticate_and_send(self, client: smtplib.SMTP, email: EmailMessage) -> None:
        username = self._settings.username
        password = self._settings.password
        if username is None or password is None:
            raise MailProviderFailure("SMTP delivery is not configured")
        client.login(username.get_secret_value(), password.get_secret_value())
        client.send_message(email)

    def _render_message(self, message: VerificationMailMessage) -> EmailMessage:
        sender = self._settings.default_sender
        if sender is None:
            raise MailProviderFailure("SMTP delivery is not configured")
        email = EmailMessage()
        email["From"] = sender
        email["To"] = message.recipient_email
        email["Message-ID"] = make_msgid(domain="mail.veyra.local")
        if message.purpose.value == "registration":
            email["Subject"] = "Your Veyra Community verification code"
            action = "complete registration"
        else:
            email["Subject"] = "Your Veyra Community password reset code"
            action = "reset your password"
        email.set_content(
            f"Use this code to {action}: {message.verification_code}\n\n"
            "This code expires in 10 minutes. If you did not request it, "
            "ignore this email."
        )
        return email
