"""Canonical portable-definition projections and SHA-256 digests."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

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
        "id": source["id"],
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


def file_hash(source: Mapping[str, Any]) -> str:
    """Design-document name for the whole-source digest."""
    return source_hash(source)


def behavior_hash(source: Mapping[str, Any]) -> str:
    return sha256_digest(behavior_projection(source))


def lock_hash(source: Mapping[str, Any]) -> str:
    return sha256_digest(lock_projection(source))
