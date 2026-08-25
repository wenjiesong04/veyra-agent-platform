"""Canonical portable-definition projections and SHA-256 digests."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from typing import Any

from .common import ContractValidationError


def canonical_json(value: Any) -> bytes:
    """Serialize JSON deterministically and reject non-portable values."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractValidationError("value is not canonical JSON") from exc


def sha256_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def source_projection(source: Mapping[str, Any]) -> dict[str, Any]:
    """Whole portable source: documentation and layout deliberately remain material."""
    return dict(source)


def behavior_projection(source: Mapping[str, Any]) -> dict[str, Any]:
    """Execution semantics, excluding presentational/editor-only metadata."""
    veyra = source.get("extensions", {}).get("veyra", {})
    return {
        "agentspec_version": source["agentspec_version"],
        "component_type": source["component_type"],
        "inputs": source["inputs"],
        "outputs": source["outputs"],
        "nodes": source["nodes"],
        "transitions": source["transitions"],
        "runtime_profile": veyra["runtime_profile"],
        "secret_refs": veyra["secret_refs"],
        "permissions": veyra["permissions"],
        "verification": veyra["verification"],
    }


def lock_projection(source: Mapping[str, Any]) -> dict[str, Any]:
    lock = source.get("lock")
    if not isinstance(lock, Mapping):
        raise ContractValidationError("agent source requires a lock object")
    return dict(lock)


def source_hash(source: Mapping[str, Any]) -> str:
    return sha256_digest(source_projection(source))


def normalized_source_bytes(source_text: str) -> bytes:
    """Normalize portable source text before its whole-file digest is computed."""
    if not isinstance(source_text, str):
        raise ContractValidationError("raw source must be text")
    normalized = unicodedata.normalize(
        "NFC", source_text.replace("\r\n", "\n").replace("\r", "\n")
    )
    return normalized.encode("utf-8")


def file_hash(source_text: str) -> str:
    """Digest normalized raw source bytes; distinct from canonical semantic hashes."""
    return hashlib.sha256(normalized_source_bytes(source_text)).hexdigest()


def behavior_hash(source: Mapping[str, Any]) -> str:
    return sha256_digest(behavior_projection(source))


def lock_hash(source: Mapping[str, Any]) -> str:
    return sha256_digest(lock_projection(source))
