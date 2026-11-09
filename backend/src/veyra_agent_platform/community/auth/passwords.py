"""Argon2id password hashing with fixed, reviewable V1 parameters."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

_MIN_PASSWORD_LENGTH = 8
_MAX_PASSWORD_LENGTH = 64
_COMMON_PASSWORDS = frozenset(
    {
        "00000000",
        "11111111",
        "12345678",
        "123456789",
        "1234567890",
        "abc12345",
        "admin123",
        "iloveyou",
        "letmein1",
        "password",
        "password1",
        "password123",
        "passw0rd",
        "qwerty123",
        "veyra123",
        "veyra1234",
        "veyra12345",
        "veyra2024",
        "veyra2025",
        "veyra2026",
        "veyra-password",
        "veyra-password1",
        "veyrapassword",
        "passwordveyra",
        "veyraagent",
        "veyraagent1",
        "welcome1",
    }
)


class PasswordPolicyError(ValueError):
    """A requested password falls outside the bounded V1 policy."""


class PasswordManager:
    """Hash and verify passwords using explicit Argon2id cost parameters."""

    def __init__(self) -> None:
        self._hasher = PasswordHasher(
            time_cost=3,
            memory_cost=65_536,
            parallelism=1,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )
        self._dummy_hash = self._hasher.hash("veyra-invalid-password-check")

    @staticmethod
    def validate_new_password(password: str) -> None:
        if not _MIN_PASSWORD_LENGTH <= len(password) <= _MAX_PASSWORD_LENGTH:
            raise PasswordPolicyError(
                "password must contain "
                f"{_MIN_PASSWORD_LENGTH}–{_MAX_PASSWORD_LENGTH} characters"
            )
        if "\x00" in password:
            raise PasswordPolicyError("password cannot contain a null byte")
        if password.casefold() in _COMMON_PASSWORDS:
            raise PasswordPolicyError("password is too common")

    def hash_new_password(self, password: str) -> str:
        self.validate_new_password(password)
        return self._hasher.hash(password)

    def verify(self, stored_hash: str | None, password: str) -> bool:
        """Verify an account hash and equalize unknown-account timing."""

        target = stored_hash or self._dummy_hash
        try:
            verified = self._hasher.verify(target, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False
        return bool(verified and stored_hash is not None)
