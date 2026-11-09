"""Versioned local Runtime command and replayable event wire contracts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from math import isfinite
from typing import Any, cast

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
    RUN_STATE_CHANGED = "run.state_changed"
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_INTERRUPTED = "run.interrupted"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    NODE_QUEUED = "node.queued"
    NODE_STATE_CHANGED = "node.state_changed"
    NODE_STARTED = "node.started"
    NODE_OUTPUT = "node.output"
    NODE_WAITING = "node.waiting"
    NODE_COMPLETED = "node.completed"
    NODE_FAILED = "node.failed"
    NODE_SKIPPED = "node.skipped"
    NODE_CANCELLED = "node.cancelled"
    TOOL_REQUESTED = "tool.requested"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    TOOL_INPUT_REJECTED = "tool.input_rejected"
    MODEL_OUTPUT_REJECTED = "model.output_rejected"
    AGENT_PLAN_UPDATED = "agent.plan_updated"
    AGENT_BUDGET_UPDATED = "agent.budget_updated"
    AGENT_BUDGET_INSUFFICIENT = "agent.budget_insufficient"
    FINALIZATION_STARTED = "finalization.started"
    FINALIZATION_PROGRESS = "finalization.progress"
    FINALIZATION_COMPLETED = "finalization.completed"
    FINALIZATION_REJECTED = "finalization.rejected"
    FINALIZATION_ACCEPTED = "finalization.accepted"
    FINALIZATION_FAILED = "finalization.failed"
    IMAGE_RESPONSE_RECEIVED = "image.response_received"
    MODEL_DELTA = "model.delta"
    MODEL_PROGRESS = "model.progress"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"
    INPUT_REQUESTED = "input.requested"
    INPUT_RESOLVED = "input.resolved"
    ARTIFACT_CREATED = "artifact.created"
    CHECKPOINT_CREATED = "checkpoint.created"
    VERIFICATION_COMPLETED = "verification.completed"
    EVALUATION_COMPLETED = "evaluation.completed"
    EVALUATION_REVIEWED = "evaluation.reviewed"
    VERIFIER_RESULT = "verifier.result"
    SKILL_LOADED = "skill.loaded"
    KNOWLEDGE_RETRIEVED = "knowledge.retrieved"
    POLICY_PARTIAL = "policy.partial"
    INPUT_PROTECTED = "input.protected"
    INPUT_OUTPUT_CREATED = "input.output_created"


class RunCommandKind(StrEnum):
    START = "run.start"
    CANCEL = "run.cancel"
    STOP = "run.stop"
    APPROVE = "run.approve"
    REJECT = "run.reject"
    REPLY = "run.reply"
    STEER = "run.steer"
    RESUME = "run.resume"
    RESUME_CHECKPOINT = "run.resume_checkpoint"
    RETRY_SAFE_NODE = "run.retry_safe_node"
    EXTEND_BUDGET = "run.extend_budget"


class RunState(StrEnum):
    CREATED = "created"
    VALIDATING = "validating"
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_INPUT = "waiting_input"
    WAITING_EXTERNAL = "waiting_external"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class NodeState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_INPUT = "waiting_input"
    WAITING_EXTERNAL = "waiting_external"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"


EVENT_NODE_ID_REQUIRED: Mapping[RunEventKind, bool] = {
    RunEventKind.RUN_CREATED: False,
    RunEventKind.RUN_STATE_CHANGED: False,
    RunEventKind.RUN_STARTED: False,
    RunEventKind.RUN_COMPLETED: False,
    RunEventKind.RUN_INTERRUPTED: False,
    RunEventKind.RUN_FAILED: False,
    RunEventKind.RUN_CANCELLED: False,
    RunEventKind.NODE_QUEUED: True,
    RunEventKind.NODE_STATE_CHANGED: True,
    RunEventKind.NODE_STARTED: True,
    RunEventKind.NODE_OUTPUT: True,
    RunEventKind.NODE_WAITING: True,
    RunEventKind.NODE_COMPLETED: True,
    RunEventKind.NODE_FAILED: True,
    RunEventKind.NODE_SKIPPED: True,
    RunEventKind.NODE_CANCELLED: True,
    RunEventKind.TOOL_REQUESTED: True,
    RunEventKind.TOOL_STARTED: True,
    RunEventKind.TOOL_COMPLETED: True,
    RunEventKind.TOOL_FAILED: True,
    RunEventKind.TOOL_INPUT_REJECTED: True,
    RunEventKind.MODEL_OUTPUT_REJECTED: True,
    RunEventKind.AGENT_PLAN_UPDATED: True,
    RunEventKind.AGENT_BUDGET_UPDATED: True,
    RunEventKind.AGENT_BUDGET_INSUFFICIENT: True,
    RunEventKind.FINALIZATION_STARTED: True,
    RunEventKind.FINALIZATION_PROGRESS: True,
    RunEventKind.FINALIZATION_COMPLETED: True,
    RunEventKind.FINALIZATION_REJECTED: True,
    RunEventKind.FINALIZATION_ACCEPTED: True,
    RunEventKind.FINALIZATION_FAILED: True,
    RunEventKind.IMAGE_RESPONSE_RECEIVED: True,
    RunEventKind.MODEL_DELTA: True,
    RunEventKind.MODEL_PROGRESS: True,
    RunEventKind.APPROVAL_REQUESTED: True,
    RunEventKind.APPROVAL_RESOLVED: True,
    RunEventKind.INPUT_REQUESTED: True,
    RunEventKind.INPUT_RESOLVED: True,
    RunEventKind.ARTIFACT_CREATED: True,
    RunEventKind.CHECKPOINT_CREATED: True,
    RunEventKind.VERIFICATION_COMPLETED: True,
    RunEventKind.EVALUATION_COMPLETED: False,
    RunEventKind.EVALUATION_REVIEWED: False,
    RunEventKind.VERIFIER_RESULT: True,
    RunEventKind.SKILL_LOADED: True,
    RunEventKind.KNOWLEDGE_RETRIEVED: True,
    RunEventKind.POLICY_PARTIAL: True,
    RunEventKind.INPUT_PROTECTED: False,
    RunEventKind.INPUT_OUTPUT_CREATED: False,
}

COMMAND_NODE_ID_REQUIRED: Mapping[RunCommandKind, bool] = {
    RunCommandKind.START: False,
    RunCommandKind.CANCEL: False,
    RunCommandKind.STOP: False,
    RunCommandKind.APPROVE: True,
    RunCommandKind.REJECT: True,
    RunCommandKind.REPLY: True,
    RunCommandKind.STEER: True,
    RunCommandKind.RESUME: True,
    RunCommandKind.RESUME_CHECKPOINT: False,
    RunCommandKind.RETRY_SAFE_NODE: True,
    RunCommandKind.EXTEND_BUDGET: True,
}


def _payload(value: Any, field: str) -> Mapping[str, Any]:
    item = require_mapping(value, field)
    # Payloads are data-only; a nested callable is never a portable wire value.
    if not _json_data(item):
        raise ContractValidationError(f"{field} must contain JSON data only")
    return cast(Mapping[str, Any], freeze_json(item))


def _state_change_payload(
    value: Any, state_type: type[RunState] | type[NodeState]
) -> Mapping[str, Any]:
    item = require_mapping(value, "state-change payload")
    require_keys(
        item,
        allowed={"previous_state", "state", "reason"},
        required={"previous_state", "state"},
    )
    try:
        previous_state = state_type(item["previous_state"])
        state = state_type(item["state"])
    except (TypeError, ValueError) as exc:
        raise ContractValidationError(
            "state-change payload contains an unknown state"
        ) from exc
    result: dict[str, str] = {
        "previous_state": previous_state.value,
        "state": state.value,
    }
    if "reason" in item:
        result["reason"] = require_string(item["reason"], "reason")
    return cast(Mapping[str, Any], freeze_json(result))


def _json_data(value: Any) -> bool:
    if value is None or isinstance(value, str | int | bool):
        return True
    if isinstance(value, float):
        return isfinite(value)
    if isinstance(value, list):
        return all(_json_data(item) for item in value)
    if isinstance(value, Mapping):
        return all(
            isinstance(key, str) and _json_data(item) for key, item in value.items()
        )
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
    def from_dict(cls, data: Any) -> RunEvent:
        item = require_mapping(data, "run event")
        required = {
            "schema_version",
            "event_id",
            "run_id",
            "timestamp",
            "sequence",
            "kind",
            "node_id",
            "payload",
        }
        require_keys(item, allowed=required, required=required)
        require_schema_version(item)
        try:
            kind = RunEventKind(item["kind"])
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("run event kind is unknown") from exc
        sequence = item["sequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ContractValidationError(
                "run event sequence must be a positive integer"
            )
        node_id = item["node_id"]
        if EVENT_NODE_ID_REQUIRED[kind]:
            require_node_id(node_id, "node_id")
        elif node_id is not None:
            raise ContractValidationError("run-level events must have null node_id")
        if kind is RunEventKind.RUN_STATE_CHANGED:
            payload = _state_change_payload(item["payload"], RunState)
        elif kind is RunEventKind.NODE_STATE_CHANGED:
            payload = _state_change_payload(item["payload"], NodeState)
        else:
            payload = _payload(item["payload"], "payload")
        return cls(
            SCHEMA_VERSION,
            require_uuid7(item["event_id"], "event_id"),
            require_uuid7(item["run_id"], "run_id"),
            _utc_timestamp(item["timestamp"]),
            sequence,
            kind,
            node_id,
            payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "kind": self.kind.value,
            "node_id": self.node_id,
            "payload": thaw_json(self.payload),
        }


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
    def from_dict(cls, data: Any) -> RunCommand:
        item = require_mapping(data, "run command")
        required = {
            "schema_version",
            "command_id",
            "run_id",
            "idempotency_key",
            "kind",
            "node_id",
            "expected_revision",
            "payload",
        }
        require_keys(item, allowed=required, required=required)
        require_schema_version(item)
        try:
            kind = RunCommandKind(item["kind"])
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("run command kind is unknown") from exc
        node_id = item["node_id"]
        if COMMAND_NODE_ID_REQUIRED[kind]:
            require_node_id(node_id, "node_id")
        elif node_id is not None:
            raise ContractValidationError("run-level command must have null node_id")
        revision = item["expected_revision"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ContractValidationError(
                "expected_revision must be a non-negative integer"
            )
        return cls(
            SCHEMA_VERSION,
            require_uuid7(item["command_id"], "command_id"),
            require_uuid7(item["run_id"], "run_id"),
            require_uuid7(item["idempotency_key"], "idempotency_key"),
            kind,
            node_id,
            revision,
            _payload(item["payload"], "payload"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "command_id": self.command_id,
            "run_id": self.run_id,
            "idempotency_key": self.idempotency_key,
            "kind": self.kind.value,
            "node_id": self.node_id,
            "expected_revision": self.expected_revision,
            "payload": thaw_json(self.payload),
        }


_UTC_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")


def _utc_timestamp(value: Any) -> str:
    timestamp = require_string(value, "timestamp")
    if not _UTC_TIMESTAMP_RE.fullmatch(timestamp):
        raise ContractValidationError(
            "timestamp must be canonical RFC 3339 UTC text with T and Z"
        )
    try:
        parsed = datetime.fromisoformat(f"{timestamp[:-1]}+00:00")
    except ValueError as exc:
        raise ContractValidationError("timestamp must be RFC 3339") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ContractValidationError("timestamp must be timezone-aware UTC")
    base = parsed.strftime("%Y-%m-%dT%H:%M:%S")
    if parsed.microsecond == 0:
        return f"{base}Z"
    return f"{base}.{parsed.microsecond:06d}".rstrip("0") + "Z"
