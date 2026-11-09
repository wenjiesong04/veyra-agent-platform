"""Small, deterministic license declaration scan for public packages."""

from __future__ import annotations

import re
from typing import Any

_LICENSE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,119}$")

# This is intentionally a conservative review list, not a license lawyer. A
# custom or newer identifier remains publishable but is surfaced for review.
_KNOWN_IDS = frozenset(
    {
        "AGPL-3.0-only",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "CC0-1.0",
        "GPL-2.0-only",
        "GPL-3.0-only",
        "ISC",
        "LGPL-2.1-only",
        "MIT",
        "MPL-2.0",
        "OFL-1.1",
        "Unlicense",
    }
)


def scan_license(value: str | None) -> dict[str, Any]:
    """Classify a declared license without blocking custom declarations."""
    if value is None or not value.strip():
        return {
            "status": "warning",
            "code": "license_missing",
            "value": None,
        }
    normalized = value.strip()
    if _LICENSE_ID.fullmatch(normalized) is None:
        return {
            "status": "warning",
            "code": "license_format_review",
            "value": None,
        }
    if normalized not in _KNOWN_IDS:
        return {
            "status": "warning",
            "code": "license_review",
            "value": normalized,
        }
    return {
        "status": "passed",
        "code": "spdx_identifier",
        "value": normalized,
    }
