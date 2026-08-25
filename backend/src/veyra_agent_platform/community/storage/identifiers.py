"""Stable identifiers and UTC timestamps for Community persistence."""

from __future__ import annotations

import secrets
import time
import uuid
from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(UTC)


def new_uuid7() -> str:
    """Generate a UUIDv7-compatible, randomly suffixed text identifier."""

    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    rand_a = random_bits >> 62
    rand_b = random_bits & ((1 << 62) - 1)
    value = timestamp_ms << 80
    value |= 0x7 << 76
    value |= rand_a << 64
    value |= 0b10 << 62
    value |= rand_b
    return str(uuid.UUID(int=value))
