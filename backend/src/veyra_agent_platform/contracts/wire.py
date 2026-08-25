"""Versioned local Runtime command and replayable event wire contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from math import isfinite
from typing import Any, Mapping

from .common import (
    SCHEMA_VERSION,
    ContractValidationError,
    freeze_json,
    require_keys,
    require_mapping,
    require_node_id,
    require_schema_version,
    require_string,
    require_uuid7,
    thaw_json,
)


class RunEventKind(StrEnum):
    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    NODE_STARTED = "node.started"
    NODE_OUTPUT = "node.output"
    NODE_WAITING = "node.waiting"
    NODE_FAILED = "node.failed"
    NODE_COMPLETED = "node.completed"
    VERIFIER_RESULT = "verifier.result"


class RunCommandKind(StrEnum):
    START = "run.start"
    CANCEL = "run.cancel"
    APPROVE = "run.approve"
    REJECT = "run.reject"
    RESUME = "run.resume"


_RUN_LEVEL_EVENTS = frozenset({
    RunEventKind.RUN_CREATED,
    RunEventKind.RUN_STARTED,
    RunEventKind.RUN_COMPLETED,
    RunEventKind.RUN_FAILED,
    RunEventKind.RUN_CANCELLED,
})
_NODE_COMMANDS = frozenset({RunCommandKind.APPROVE, RunCommandKind.REJECT, RunCommandKind.RESUME})


def _payload(value: Any, field: str) -> Mapping[str, Any]:
    item = require_mapping(value, field)
    # Payloads are data-only; a nested callable is never a portable wire value.
    if not _json_data(item):
        raise ContractValidationError(f"{field} must contain JSON data only")
    return freeze_json(item)


def _json_data(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, bool)):
        return True
    if isinstance(value, float):
        return isfinite(value)
    if isinstance(value, list):
        return all(_json_data(item) for item in value)
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _json_data(item) for key, item in value.items())
    return False


@dataclass(frozen=True)
class RunEvent:
    schema_version: str
    event_id: str
    run_id: str
    timestamp: str
    sequence: int
    kind: RunEventKind
    node_id: str | None
    payload: Mapping[str, Any]

    @classmethod
    def from_dict(cls, data: Any) -> "RunEvent":
        item = require_mapping(data, "run event")
        required = {"schema_version", "event_id", "run_id", "timestamp", "sequence", "kind", "node_id", "payload"}
        require_keys(item, allowed=required, required=required)
        require_schema_version(item)
        try:
            kind = RunEventKind(item["kind"])
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("run event kind is unknown") from exc
        sequence = item["sequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ContractValidationError("run event sequence must be a positive integer")
        node_id = item["node_id"]
        if kind in _RUN_LEVEL_EVENTS:
            if node_id is not None:
                raise ContractValidationError("run-level events must have null node_id")
        else:
            require_node_id(node_id, "node_id")
        return cls(SCHEMA_VERSION, require_uuid7(item["event_id"], "event_id"), require_uuid7(item["run_id"], "run_id"), _utc_timestamp(item["timestamp"]), sequence, kind, node_id, _payload(item["payload"], "payload"))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "event_id": self.event_id, "run_id": self.run_id, "timestamp": self.timestamp, "sequence": self.sequence, "kind": self.kind.value, "node_id": self.node_id, "payload": thaw_json(self.payload)}


@dataclass(frozen=True)
class RunCommand:
    schema_version: str
    command_id: str
    run_id: str
    idempotency_key: str
    kind: RunCommandKind
    node_id: str | None
    expected_revision: int
    payload: Mapping[str, Any]

    @classmethod
    def from_dict(cls, data: Any) -> "RunCommand":
        item = require_mapping(data, "run command")
        required = {"schema_version", "command_id", "run_id", "idempotency_key", "kind", "node_id", "expected_revision", "payload"}
        require_keys(item, allowed=required, required=required)
        require_schema_version(item)
        try:
            kind = RunCommandKind(item["kind"])
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("run command kind is unknown") from exc
        node_id = item["node_id"]
        if kind in _NODE_COMMANDS:
            require_node_id(node_id, "node_id")
        elif node_id is not None:
            raise ContractValidationError("run-level command must have null node_id")
        revision = item["expected_revision"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ContractValidationError("expected_revision must be a non-negative integer")
        return cls(SCHEMA_VERSION, require_uuid7(item["command_id"], "command_id"), require_uuid7(item["run_id"], "run_id"), require_uuid7(item["idempotency_key"], "idempotency_key"), kind, node_id, revision, _payload(item["payload"], "payload"))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "command_id": self.command_id, "run_id": self.run_id, "idempotency_key": self.idempotency_key, "kind": self.kind.value, "node_id": self.node_id, "expected_revision": self.expected_revision, "payload": thaw_json(self.payload)}


def _utc_timestamp(value: Any) -> str:
    timestamp = require_string(value, "timestamp")
    if not timestamp.endswith("Z"):
        raise ContractValidationError("timestamp must be an RFC 3339 UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(f"{timestamp[:-1]}+00:00")
    except ValueError as exc:
        raise ContractValidationError("timestamp must be RFC 3339") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ContractValidationError("timestamp must be timezone-aware UTC")
    return timestamp
