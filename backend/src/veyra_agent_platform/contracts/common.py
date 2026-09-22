"""Strict primitives used by every V1 wire and portable-definition contract."""

from __future__ import annotations

import re
import secrets
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Any

SCHEMA_VERSION = "1.0"
_UUID7_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_ETAG_RE = re.compile(r'^"[0-9a-f]{64}"$')
NODE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


class ContractValidationError(ValueError):
    """Raised when untrusted portable or wire data violates a V1 contract."""


def new_uuid7() -> str:
    """Return a sortable RFC 9562 UUIDv7 string without a third-party dependency."""
    timestamp_ms = int(time.time_ns() // 1_000_000)
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (
        (timestamp_ms << 80) | (0x7 << 76) | (random_a << 64) | (0b10 << 62) | random_b
    )
    return str(uuid.UUID(int=value))


def require_uuid7(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _UUID7_RE.fullmatch(value):
        raise ContractValidationError(f"{field} must be a lowercase UUIDv7 text ID")
    return value


def require_node_id(value: Any, field: str) -> str:
    return require_string(value, field, pattern=NODE_ID_RE)


def freeze_json(value: Any) -> Any:
    """Defensively copy JSON-compatible data into immutable recursive values."""
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ContractValidationError("JSON numbers must be finite")
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ContractValidationError("JSON object keys must be strings")
        return MappingProxyType({key: freeze_json(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(freeze_json(item) for item in value)
    raise ContractValidationError("value must contain JSON data only")


def thaw_json(value: Any) -> Any:
    """Return a fresh mutable JSON-compatible copy for serialization."""
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


def require_schema_version(data: Mapping[str, Any]) -> None:
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ContractValidationError(
            f"schema_version must be exactly {SCHEMA_VERSION!r}"
        )


def require_keys(
    data: Mapping[str, Any],
    *,
    allowed: set[str],
    required: set[str],
    field: str = "",
) -> None:
    unknown = set(data) - allowed
    missing = required - set(data)
    prefix = f"{field}: " if field else ""
    if unknown:
        raise ContractValidationError(
            f"{prefix}unknown field(s): {', '.join(sorted(unknown))}"
        )
    if missing:
        raise ContractValidationError(
            f"{prefix}missing field(s): {', '.join(sorted(missing))}"
        )


def require_string(
    value: Any, field: str, *, pattern: re.Pattern[str] | None = None
) -> str:
    if not isinstance(value, str) or not value:
        raise ContractValidationError(f"{field} must be a non-empty string")
    if pattern is not None and not pattern.fullmatch(value):
        raise ContractValidationError(f"{field} has an invalid format")
    return value


def require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field} must be a list")
    return value


def require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{field} must be an object")
    return value


@dataclass(frozen=True)
class ErrorEnvelope:
    schema_version: str
    code: str
    message: str
    request_id: str
    details: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError("invalid error envelope schema_version")
        require_string(self.code, "code")
        require_string(self.message, "message")
        require_uuid7(self.request_id, "request_id")
        if self.details is not None and not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in self.details.items()
        ):
            raise ContractValidationError("details must map strings to strings")


@dataclass(frozen=True)
class Cursor:
    schema_version: str
    value: str

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError("invalid cursor schema_version")
        require_string(self.value, "cursor.value")


@dataclass(frozen=True)
class RevisionEtag:
    schema_version: str
    revision: int
    etag: str

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError("invalid revision schema_version")
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 0
        ):
            raise ContractValidationError("revision must be a non-negative integer")
        if not isinstance(self.etag, str) or not _ETAG_RE.fullmatch(self.etag):
            raise ContractValidationError("etag must be a quoted SHA-256 digest")


@dataclass(frozen=True)
class IdempotencyKey:
    schema_version: str
    value: str

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError("invalid idempotency schema_version")
        require_uuid7(self.value, "idempotency_key")
