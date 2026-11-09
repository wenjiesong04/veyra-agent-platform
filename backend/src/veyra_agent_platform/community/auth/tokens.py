"""CSPRNG secrets and HMAC-only persistence digests for auth material."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass


class AuthSecretDigester:
    """Domain-separate HMAC digests so databases never retain raw auth secrets."""

    def __init__(self, secret: str) -> None:
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("auth HMAC secret must contain at least 32 bytes")
        self._key = secret.encode("utf-8")

    def digest(self, purpose: str, value: str) -> str:
        message = f"{purpose}\x00{value}".encode()
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    def code_digest(self, purpose: str, email_normalized: str, code: str) -> str:
        return self.digest(f"code:{purpose}:{email_normalized}", code)

    def subject_digest(self, scope: str, value: str) -> str:
        return self.digest(f"rate:{scope}", value)

    def opaque_token_digest(self, kind: str, token: str) -> str:
        return self.digest(f"token:{kind}", token)


def new_six_digit_code() -> str:
    """Generate a CSPRNG-backed, zero-padded six-digit verification code."""

    return f"{secrets.randbelow(1_000_000):06d}"


def new_opaque_token() -> str:
    """Generate an opaque token with at least 256 bits of CSPRNG entropy."""

    return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class SessionSecrets:
    """Transient raw browser secrets; only their digests enter persistence."""

    session_token: str
    refresh_token: str
    csrf_token: str

    @classmethod
    def create(cls) -> SessionSecrets:
        return cls(
            session_token=new_opaque_token(),
            refresh_token=new_opaque_token(),
            csrf_token=new_opaque_token(),
        )
