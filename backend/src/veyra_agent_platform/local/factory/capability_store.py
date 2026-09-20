"""Persist safe ProviderCapabilityProfile rows outside Project directories."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .capability_profile import (
    ProviderCapabilityProfile,
    assert_safe_profile_payload,
)


class ProviderCapabilityStore:
    """Cache probe facts keyed by provider + model + endpoint + probe version."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = str(database_path)

    def get(self, identity_key: str) -> ProviderCapabilityProfile | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT profile_json FROM provider_capability_profiles
                   WHERE identity_key = ?""",
                (identity_key,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["profile_json"])
        if not isinstance(payload, dict):
            return None
        return profile_from_payload(payload)

    def put(self, profile: ProviderCapabilityProfile) -> None:
        payload = profile.to_storage_dict()
        assert_safe_profile_payload(payload)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if any(
            token in encoded.casefold()
            for token in ("sk-", "bearer ", "authorization", "moonshot-")
        ):
            raise ValueError("capability profile must not persist credentials")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO provider_capability_profiles(
                    identity_key, provider_id, model, endpoint_kind,
                    base_url_fingerprint, probe_version, status, source,
                    profile_json, checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(identity_key) DO UPDATE SET
                    status = excluded.status,
                    source = excluded.source,
                    profile_json = excluded.profile_json,
                    checked_at = excluded.checked_at""",
                (
                    profile.identity_key,
                    profile.provider_id,
                    profile.model,
                    profile.endpoint_kind,
                    profile.base_url_fingerprint,
                    profile.probe_version,
                    profile.status,
                    profile.source,
                    encoded,
                    profile.checked_at or "",
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection


def profile_from_payload(payload: Mapping[str, Any]) -> ProviderCapabilityProfile:
    assert_safe_profile_payload(payload)
    checked = payload.get("checked_at")
    error_class = payload.get("error_class")
    return ProviderCapabilityProfile(
        provider_id=_text(payload, "provider_id"),
        provider_family=_choice(
            payload, "provider_family", ("moonshot", "openai_compatible")
        ),
        model=_text(payload, "model"),
        endpoint_kind=_choice(
            payload,
            "endpoint_kind",
            ("chat_completions", "responses", "compatible_chat"),
        ),
        base_url_fingerprint=_text(payload, "base_url_fingerprint"),
        structured_output=_choice(
            payload, "structured_output", ("json_schema", "json_object")
        ),
        schema_flavor=_choice(payload, "schema_flavor", ("moonshot_mfjs", "none")),
        schema_profile=_choice(
            payload, "schema_profile", ("mfjs", "openai_json_schema", "unknown")
        ),
        strict_json_schema=_bool(payload, "strict_json_schema"),
        json_object_fallback=_bool(payload, "json_object_fallback"),
        reasoning_effort=_bool(payload, "reasoning_effort"),
        supports_reasoning_effort=_bool(payload, "supports_reasoning_effort"),
        strict_json_schema_support=_choice(
            payload,
            "strict_json_schema_support",
            ("supported", "unsupported", "unknown"),
        ),
        json_object_support=_choice(
            payload, "json_object_support", ("supported", "unsupported", "unknown")
        ),
        source=_choice(payload, "source", ("static_known", "probe", "fallback")),
        status=_choice(
            payload, "status", ("known", "unknown", "stale", "failed", "inconclusive")
        ),
        checked_at=checked if isinstance(checked, str) and checked else None,
        probe_version=_text(payload, "probe_version"),
        probed=_bool(payload, "probed"),
        error_class=error_class if isinstance(error_class, str) else None,
    )


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"capability profile missing {key}")
    return value


def _bool(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"capability profile missing {key}")
    return value


def _choice(payload: Mapping[str, Any], key: str, allowed: tuple[str, ...]) -> Any:
    value = _text(payload, key)
    if value not in allowed:
        raise ValueError(f"capability profile invalid {key}")
    return value
