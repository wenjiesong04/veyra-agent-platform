"""Safe per-invocation Builder Harness receipts.

A receipt records the controlled protocol context of one provider request.
It is not a prompt archive, chain of thought, ProviderCapabilityProfile row,
operation timeline, chat message, or Runtime run.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Literal

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.builder.conversation_store import (
    BuilderConversationStore,
)
from veyra_agent_platform.local.builder.harness import (
    EXCLUDED_CONTEXT_CATEGORIES,
    INCLUDED_CONTEXT_CATEGORIES,
    BuilderHarness,
    BuilderMode,
    canonical_json_hash,
)
from veyra_agent_platform.local.builder.prompt import (
    BUILDER_POLICY_VERSION,
    BUILDER_SYSTEM_PROMPT,
    builder_policy_hash,
)
from veyra_agent_platform.local.factory.capability_profile import (
    ProviderCapabilityProfile,
)
from veyra_agent_platform.local.factory.client import FactoryProviderError

InvocationKind = Literal[
    "resolve_intent",
    "interview",
    "semantic_plan",
    "semantic_plan_repair",
]
ReceiptStatus = Literal["prepared", "success", "failed"]
StructuredMode = Literal["strict_json_schema", "json_object", "none"]
FailureStage = Literal["provider_request"]

INVOCATION_KINDS = frozenset(
    {"resolve_intent", "interview", "semantic_plan", "semantic_plan_repair"}
)
STRUCTURED_MODES = frozenset({"strict_json_schema", "json_object", "none"})
_SECRET = re.compile(r"(?i)(bearer\s+\S+|sk-[A-Za-z0-9._-]+|moonshot-[A-Za-z0-9._-]+)")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_FORBIDDEN_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "secret",
        "password",
        "token",
        "prompt",
        "system",
        "raw",
        "body",
        "headers",
        "reasoning",
        "reasoning_content",
        "credential",
        "cookie",
    }
)
_FORBIDDEN_TOKENS = (
    "sk-",
    "bearer ",
    "authorization",
    "reasoning_content",
    "chain-of-thought",
    "you are veyra builder",
)


class ReceiptImmutableError(RuntimeError):
    """Completed receipts are historical evidence and cannot be rewritten."""


class HarnessReceiptRecorder:
    """Persist prepared receipts before a provider request, then finalize them."""

    def __init__(
        self,
        store: BuilderConversationStore,
        harness: BuilderHarness,
        *,
        project_id: str,
        conversation_id: str,
        operation_id: str,
        profile: ProviderCapabilityProfile,
    ) -> None:
        self.store = store
        self.harness = harness
        self.project_id = project_id
        self.conversation_id = conversation_id
        self.operation_id = operation_id
        self.profile = profile

    def begin(
        self,
        *,
        kind: InvocationKind,
        harness_mode: BuilderMode,
        structured_mode: StructuredMode,
        output_contract: str,
        schema: Mapping[str, Any] | None,
        messages: Sequence[Mapping[str, Any]],
        history_message_count: int,
        fallback_from: str | None = None,
        fallback_to: str | None = None,
        profile: ProviderCapabilityProfile | None = None,
    ) -> str:
        if kind not in INVOCATION_KINDS or structured_mode not in STRUCTURED_MODES:
            raise ValueError("unknown harness receipt kind")
        used = profile or self.profile
        snapshot = self.harness.snapshot_facts(self.project_id, harness_mode)
        included = list(INCLUDED_CONTEXT_CATEGORIES)
        if history_message_count <= 0:
            included = [
                item for item in included if item != "conversation_recent_messages"
            ]
        receipt_id = new_uuid7()
        started_at = _now()
        payload = {
            "receipt_id": receipt_id,
            "operation_id": self.operation_id,
            "conversation_id": self.conversation_id,
            "project_id": self.project_id,
            "invocation_kind": kind,
            "sequence": self.store.next_receipt_sequence(self.operation_id),
            "status": "prepared",
            "started_at": started_at,
            "completed_at": None,
            "harness_mode": harness_mode,
            "policy_version": BUILDER_POLICY_VERSION,
            "policy_hash": builder_policy_hash(),
            "output_contract": output_contract,
            "schema_version": "1.0",
            "schema_hash": canonical_json_hash(schema or {"contract": output_contract}),
            "structured_mode": structured_mode,
            "project_snapshot_hash": snapshot.project_hash,
            "catalog_snapshot_hash": snapshot.catalog_hash,
            "included_categories": included,
            "excluded_categories": list(EXCLUDED_CONTEXT_CATEGORIES),
            "history_message_count": max(0, history_message_count),
            "context_size_bytes": snapshot.context_size_bytes,
            "request_size_bytes": _bounded_size(messages),
            "provider_id": used.provider_id,
            "model": used.model,
            "endpoint_kind": used.endpoint_kind,
            "provider_profile_status": used.status,
            "provider_profile_source": used.source,
            "schema_profile": used.schema_profile,
            "failure_stage": None,
            "error_code": None,
            "safe_provider_error_type": None,
            "safe_provider_error_param": None,
            "provider_request_id": None,
            "fallback_from": fallback_from,
            "fallback_to": fallback_to,
            "created_at": started_at,
            "updated_at": started_at,
        }
        assert_safe_receipt_payload(payload)
        self.store.insert_receipt(payload)
        return receipt_id

    def succeed(
        self,
        receipt_id: str,
        *,
        provider_request_id: str | None = None,
    ) -> None:
        _finalize(
            self.store,
            receipt_id,
            status="success",
            completed_at=_now(),
            provider_request_id=_safe_request_id(provider_request_id),
        )

    def fail(
        self,
        receipt_id: str,
        error: FactoryProviderError,
        *,
        failure_stage: FailureStage = "provider_request",
    ) -> None:
        details = dict(error.details or {})
        _finalize(
            self.store,
            receipt_id,
            status="failed",
            completed_at=_now(),
            failure_stage=failure_stage,
            error_code=str(error.code)[:80],
            safe_provider_error_type=_safe_fact(details.get("provider_error_type")),
            safe_provider_error_param=_safe_fact(
                details.get("rejected_field") or details.get("provider_error_param")
            ),
        )


def _finalize(
    store: BuilderConversationStore,
    receipt_id: str,
    **fields: Any,
) -> None:
    try:
        store.finalize_receipt(receipt_id, **fields)
    except ValueError as exc:
        if "immutable" in str(exc):
            raise ReceiptImmutableError(str(exc)) from exc
        raise


def structured_mode_of(response_format: Mapping[str, Any] | None) -> StructuredMode:
    kind = response_format.get("type") if isinstance(response_format, dict) else None
    if kind == "json_schema":
        return "strict_json_schema"
    if kind == "json_object":
        return "json_object"
    return "none"


def public_receipt(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "receipt_id": row["receipt_id"],
        "operation_id": row["operation_id"],
        "conversation_id": row["conversation_id"],
        "project_id": row["project_id"],
        "invocation_kind": row["invocation_kind"],
        "sequence": int(row["sequence"]),
        "status": row["status"],
        "started_at": row["started_at"],
        "completed_at": row.get("completed_at"),
        "harness_mode": row["harness_mode"],
        "policy_version": row["policy_version"],
        "policy_hash": row["policy_hash"],
        "output_contract": row["output_contract"],
        "schema_version": row["schema_version"],
        "schema_hash": row["schema_hash"],
        "structured_mode": row["structured_mode"],
        "project_snapshot_hash": row["project_snapshot_hash"],
        "catalog_snapshot_hash": row["catalog_snapshot_hash"],
        "included_categories": _load_list(row.get("included_categories_json")),
        "excluded_categories": _load_list(row.get("excluded_categories_json")),
        "history_message_count": int(row["history_message_count"]),
        "context_size_bytes": int(row["context_size_bytes"]),
        "request_size_bytes": int(row["request_size_bytes"]),
        "provider_id": row["provider_id"],
        "model": row["model"],
        "endpoint_kind": row["endpoint_kind"],
        "provider_profile_status": row["provider_profile_status"],
        "provider_profile_source": row["provider_profile_source"],
        "schema_profile": row["schema_profile"],
        "failure_stage": row.get("failure_stage"),
        "error_code": row.get("error_code"),
        "safe_provider_error_type": row.get("safe_provider_error_type"),
        "safe_provider_error_param": row.get("safe_provider_error_param"),
        "provider_request_id": row.get("provider_request_id"),
        "fallback_from": row.get("fallback_from"),
        "fallback_to": row.get("fallback_to"),
    }
    assert_safe_receipt_payload(payload)
    return payload


def assert_safe_receipt_payload(payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False)
    folded = encoded.casefold()
    for key in _walk_keys(payload):
        if key.casefold() in _FORBIDDEN_KEYS:
            raise ValueError("harness receipt must not persist secrets or prompts")
    for token in _FORBIDDEN_TOKENS:
        if token in folded:
            raise ValueError("harness receipt must not persist secrets or prompts")
    if BUILDER_SYSTEM_PROMPT in encoded:
        raise ValueError("harness receipt must not persist the Builder policy prompt")
    if _SECRET.search(encoded):
        raise ValueError("harness receipt must not persist credentials")


def _bounded_size(messages: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for item in messages:
        total += _message_bytes(item)
    return min(total, 2_000_000)


def _message_bytes(item: Mapping[str, Any]) -> int:
    content = item.get("content")
    if isinstance(content, str):
        return len(content.encode("utf-8"))
    return len(json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _safe_request_id(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not _REQUEST_ID.fullmatch(cleaned):
        return None
    if cleaned.casefold().startswith("sk-") or "bearer" in cleaned.casefold():
        return None
    return cleaned


def _safe_fact(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = _SECRET.sub("", " ".join(value.split())).strip()[:80]
    if not cleaned or any(token in cleaned.casefold() for token in _FORBIDDEN_TOKENS):
        return None
    return cleaned


def _load_list(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if not isinstance(raw, str) or not raw:
        return []
    loaded = json.loads(raw)
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded]


def _walk_keys(payload: object) -> list[str]:
    keys: list[str] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            keys.append(str(key))
            keys.extend(_walk_keys(value))
    elif isinstance(payload, list):
        for item in payload:
            keys.extend(_walk_keys(item))
    return keys


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
