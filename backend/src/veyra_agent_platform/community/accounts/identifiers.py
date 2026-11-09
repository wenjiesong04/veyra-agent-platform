"""Normalization rules for private email and public Community handles."""

from __future__ import annotations

import re
import unicodedata

_HANDLE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$")
_LOCAL = re.compile(r"^[^@\s]{1,64}$")
_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class InvalidEmailAddress(ValueError):
    """Raised when input cannot represent a normalized account email."""


class InvalidPublicHandle(ValueError):
    """Raised when input cannot represent a public Community handle."""


def normalize_email(value: str) -> str:
    """Normalize a practical account email without preserving ambiguous Unicode."""

    normalized = unicodedata.normalize("NFKC", value).strip()
    if normalized.count("@") != 1 or any(
        character.isspace() for character in normalized
    ):
        raise InvalidEmailAddress("email must contain one address without whitespace")
    local_part, domain = normalized.rsplit("@", 1)
    if not _LOCAL.fullmatch(local_part):
        raise InvalidEmailAddress("email local part is invalid")
    try:
        ascii_domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise InvalidEmailAddress("email domain is invalid") from error
    if len(ascii_domain) > 253 or "." not in ascii_domain:
        raise InvalidEmailAddress("email domain is invalid")
    if any(not _DOMAIN_LABEL.fullmatch(label) for label in ascii_domain.split(".")):
        raise InvalidEmailAddress("email domain is invalid")
    return f"{local_part.casefold()}@{ascii_domain}"


def normalize_handle(value: str) -> str:
    """Return a canonical public handle that remains independent from email."""

    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    if not _HANDLE.fullmatch(normalized):
        raise InvalidPublicHandle(
            "handle must use 3-32 lowercase letters, digits, or interior hyphens"
        )
    return normalized


def normalize_display_name(value: str) -> str:
    """Normalize a human-visible profile label without accepting blank values."""

    normalized = unicodedata.normalize("NFKC", value).strip()
    if (
        not normalized
        or len(normalized) > 80
        or any(character in "\r\n\x00" for character in normalized)
    ):
        raise ValueError("display name is invalid")
    return normalized
