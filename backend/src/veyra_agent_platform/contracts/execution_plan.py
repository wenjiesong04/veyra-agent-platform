"""Builder IR: the product that Canvas visualizes, not the other way around."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from .common import (
    SCHEMA_VERSION,
    ContractValidationError,
    freeze_json,
    require_keys,
    require_list,
    require_mapping,
    require_schema_version,
    require_string,
    thaw_json,
)
from .task_structure import StateRequirement, TaskIOField, TaskStructure, _field_sources

ProductShape = Literal[
    "PURE_AGENT",
    "WORKFLOW",
    "AGENT_WORKFLOW",
    "MULTI_AGENT_WORKFLOW",
    "UNSUPPORTED",
]
PlanStepKind = Literal[
    "start",
    "agent_call",
    "condition",
    "human_input",
    "human_approval",
    "state_read",
    "state_write",
    "verifier",
    "transform",
    "output",
    "stop",
]
DecisionStatus = Literal["decided", "blocked", "needs_user_decision"]

_SHAPES = {
    "PURE_AGENT",
    "WORKFLOW",
    "AGENT_WORKFLOW",
    "MULTI_AGENT_WORKFLOW",
    "UNSUPPORTED",
}
_STEP_KINDS = {
    "start",
    "agent_call",
    "condition",
    "human_input",
    "human_approval",
    "state_read",
    "state_write",
    "verifier",
    "transform",
    "output",
    "stop",
}
_STATUSES = {"decided", "blocked", "needs_user_decision"}
_MAX_STEPS = 32


@dataclass(frozen=True)
class ProductShapeDecision:
    shape: ProductShape
    status: DecisionStatus
    reason: str
    warnings: tuple[str, ...] = ()
    blocked_reason: str = ""
    user_requested_surface: str = ""
    downgraded: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "shape": self.shape,
            "status": self.status,
            "reason": self.reason,
            "warnings": list(self.warnings),
            "downgraded": self.downgraded,
        }
        if self.blocked_reason:
            payload["blocked_reason"] = self.blocked_reason
        if self.user_requested_surface:
            payload["user_requested_surface"] = self.user_requested_surface
        return payload

    @classmethod
    def from_dict(cls, data: Any) -> ProductShapeDecision:
        item = require_mapping(data, "product shape decision")
        require_keys(
            item,
            allowed={
                "shape",
                "status",
                "reason",
                "warnings",
                "blocked_reason",
                "user_requested_surface",
                "downgraded",
            },
            required={"shape", "status", "reason"},
        )
        shape = require_string(item["shape"], "shape")
        if shape not in _SHAPES:
            raise ContractValidationError("product shape is unknown")
        status = require_string(item["status"], "status")
        if status not in _STATUSES:
            raise ContractValidationError("product shape status is unknown")
        warnings = tuple(
            require_string(value, f"warnings[{index}]")
            for index, value in enumerate(
                require_list(item.get("warnings") or [], "warnings")
            )
        )
        downgraded = item.get("downgraded", False)
        if not isinstance(downgraded, bool):
            raise ContractValidationError("downgraded must be boolean")
        return cls(
            shape=shape,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            reason=require_string(item["reason"], "reason")[:400],
            warnings=warnings,
            blocked_reason=str(item.get("blocked_reason") or "")[:400],
            user_requested_surface=str(item.get("user_requested_surface") or "")[:40],
            downgraded=downgraded,
        )


@dataclass(frozen=True)
class PlanActor:
    id: str
    kind: Literal["agent"]
    name: str
    capabilities: tuple[str, ...]
    brief: str
    reuse_of: str = ""
    inputs: tuple[TaskIOField, ...] = ()
    outputs: tuple[TaskIOField, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "capabilities": list(self.capabilities),
            "brief": self.brief,
        }
        if self.inputs:
            payload["inputs"] = [item.to_dict() for item in self.inputs]
        if self.outputs:
            payload["outputs"] = [item.to_dict() for item in self.outputs]
        if self.reuse_of:
            payload["reuse_of"] = self.reuse_of
        return payload

    @classmethod
    def from_dict(cls, data: Any, field: str) -> PlanActor:
        item = require_mapping(data, field)
        require_keys(
            item,
            allowed={
                "id",
                "kind",
                "name",
                "capabilities",
                "brief",
                "reuse_of",
                "inputs",
                "outputs",
            },
            required={"id", "kind", "name", "brief"},
        )
        kind = require_string(item["kind"], f"{field}.kind")
        if kind != "agent":
            raise ContractValidationError(f"{field}.kind must be agent")
        capabilities = tuple(
            require_string(value, f"{field}.capabilities[{index}]")
            for index, value in enumerate(
                require_list(item.get("capabilities") or [], f"{field}.capabilities")
            )
        )
        return cls(
            id=require_string(item["id"], f"{field}.id")[:80],
            kind="agent",
            name=require_string(item["name"], f"{field}.name")[:80],
            capabilities=capabilities,
            brief=require_string(item["brief"], f"{field}.brief")[:400],
            reuse_of=str(item.get("reuse_of") or "")[:80],
            inputs=tuple(
                TaskIOField.from_dict(value, f"{field}.inputs[{index}]")
                for index, value in enumerate(
                    require_list(item.get("inputs") or [], f"{field}.inputs")
                )
            ),
            outputs=tuple(
                TaskIOField.from_dict(value, f"{field}.outputs[{index}]")
                for index, value in enumerate(
                    require_list(item.get("outputs") or [], f"{field}.outputs")
                )
            ),
        )


@dataclass(frozen=True)
class PlanStep:
    id: str
    kind: PlanStepKind
    why: str
    agent: str = ""
    expression: str = ""
    question: str = ""
    prompt: str = ""
    checks: tuple[str, ...] = ()
    entity: str = ""
    capability: str = ""
    source: str = ""
    expected_schema: Mapping[str, str] | None = None
    on_true: str = ""
    on_false: str = ""
    on_approved: str = ""
    on_rejected: str = ""
    on_next: str = ""
    input_sources: Mapping[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "why": self.why,
        }
        for key in (
            "agent",
            "expression",
            "question",
            "prompt",
            "entity",
            "capability",
            "source",
            "on_true",
            "on_false",
            "on_approved",
            "on_rejected",
            "on_next",
        ):
            value = getattr(self, key)
            if value:
                payload[key] = value
        if self.checks:
            payload["checks"] = list(self.checks)
        if self.expected_schema:
            payload["expected_schema"] = dict(self.expected_schema)
        if self.input_sources:
            payload["input_sources"] = dict(self.input_sources)
        return payload

    @classmethod
    def from_dict(cls, data: Any, field: str) -> PlanStep:
        item = require_mapping(data, field)
        require_keys(
            item,
            allowed={
                "id",
                "kind",
                "why",
                "agent",
                "expression",
                "question",
                "prompt",
                "checks",
                "entity",
                "capability",
                "source",
                "expected_schema",
                "on_true",
                "on_false",
                "on_approved",
                "on_rejected",
                "on_next",
                "input_sources",
            },
            required={"id", "kind", "why"},
        )
        kind = require_string(item["kind"], f"{field}.kind")
        if kind not in _STEP_KINDS:
            raise ContractValidationError(f"{field}.kind is unknown")
        schema = item.get("expected_schema")
        expected: dict[str, str] | None = None
        if schema is not None:
            mapping = require_mapping(schema, f"{field}.expected_schema")
            expected = {
                require_string(key, f"{field}.expected_schema.key"): require_string(
                    value, f"{field}.expected_schema.{key}"
                )
                for key, value in mapping.items()
            }
        checks = tuple(
            require_string(value, f"{field}.checks[{index}]")
            for index, value in enumerate(
                require_list(item.get("checks") or [], f"{field}.checks")
            )
        )
        return cls(
            id=require_string(item["id"], f"{field}.id")[:80],
            kind=kind,  # type: ignore[arg-type]
            why=require_string(item["why"], f"{field}.why")[:400],
            agent=str(item.get("agent") or "")[:80],
            expression=str(item.get("expression") or "")[:240],
            question=str(item.get("question") or "")[:400],
            prompt=str(item.get("prompt") or "")[:400],
            checks=checks,
            entity=str(item.get("entity") or "")[:80],
            capability=str(item.get("capability") or "")[:80],
            source=str(item.get("source") or "")[:400],
            expected_schema=freeze_json(expected) if expected else None,
            on_true=str(item.get("on_true") or "")[:80],
            on_false=str(item.get("on_false") or "")[:80],
            on_approved=str(item.get("on_approved") or "")[:80],
            on_rejected=str(item.get("on_rejected") or "")[:80],
            on_next=str(item.get("on_next") or "")[:80],
            input_sources=freeze_json(
                _field_sources(item.get("input_sources"), f"{field}.input_sources")
            ),
        )


@dataclass(frozen=True)
class ExecutionPlan:
    schema_version: str
    shape: ProductShapeDecision
    task: Mapping[str, Any]
    actors: tuple[PlanActor, ...]
    steps: tuple[PlanStep, ...]
    inputs: tuple[TaskIOField, ...]
    outputs: tuple[TaskIOField, ...]
    state: StateRequirement | None
    capabilities: tuple[str, ...]
    tool_approvals: tuple[str, ...]
    business_approvals: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    interaction: str

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "shape": self.shape.to_dict(),
            "task": dict(self.task),
            "actors": [item.to_dict() for item in self.actors],
            "steps": [item.to_dict() for item in self.steps],
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "capabilities": list(self.capabilities),
            "tool_approvals": list(self.tool_approvals),
            "business_approvals": list(self.business_approvals),
            "missing_capabilities": list(self.missing_capabilities),
            "interaction": self.interaction,
        }
        if self.state is not None:
            payload["state"] = self.state.to_dict()
        return cast(dict[str, Any], thaw_json(freeze_json(payload)))

    @classmethod
    def from_dict(cls, data: Any) -> ExecutionPlan:
        item = require_mapping(data, "execution plan")
        require_keys(
            item,
            allowed={
                "schema_version",
                "shape",
                "task",
                "actors",
                "steps",
                "inputs",
                "outputs",
                "state",
                "capabilities",
                "tool_approvals",
                "business_approvals",
                "missing_capabilities",
                "interaction",
            },
            required={"schema_version", "shape", "steps"},
        )
        require_schema_version(item)
        steps = tuple(
            PlanStep.from_dict(value, f"steps[{index}]")
            for index, value in enumerate(require_list(item["steps"], "steps"))
        )
        if len(steps) > _MAX_STEPS:
            raise ContractValidationError("execution plan exceeds step bound")
        state_raw = item.get("state")
        return cls(
            schema_version=SCHEMA_VERSION,
            shape=ProductShapeDecision.from_dict(item["shape"]),
            task=freeze_json(require_mapping(item.get("task") or {}, "task")),
            actors=tuple(
                PlanActor.from_dict(value, f"actors[{index}]")
                for index, value in enumerate(
                    require_list(item.get("actors") or [], "actors")
                )
            ),
            steps=steps,
            inputs=tuple(
                TaskIOField.from_dict(value, f"inputs[{index}]")
                for index, value in enumerate(
                    require_list(item.get("inputs") or [], "inputs")
                )
            ),
            outputs=tuple(
                TaskIOField.from_dict(value, f"outputs[{index}]")
                for index, value in enumerate(
                    require_list(item.get("outputs") or [], "outputs")
                )
            ),
            state=(
                StateRequirement.from_dict(state_raw, "state")
                if state_raw is not None
                else None
            ),
            capabilities=tuple(
                require_string(value, f"capabilities[{index}]")
                for index, value in enumerate(
                    require_list(item.get("capabilities") or [], "capabilities")
                )
            ),
            tool_approvals=tuple(
                require_string(value, f"tool_approvals[{index}]")
                for index, value in enumerate(
                    require_list(item.get("tool_approvals") or [], "tool_approvals")
                )
            ),
            business_approvals=tuple(
                require_string(value, f"business_approvals[{index}]")
                for index, value in enumerate(
                    require_list(
                        item.get("business_approvals") or [], "business_approvals"
                    )
                )
            ),
            missing_capabilities=tuple(
                require_string(value, f"missing_capabilities[{index}]")
                for index, value in enumerate(
                    require_list(
                        item.get("missing_capabilities") or [], "missing_capabilities"
                    )
                )
            ),
            interaction=str(item.get("interaction") or "single_run")[:40],
        )

    @property
    def product_shape(self) -> ProductShape:
        return self.shape.shape


def task_payload(structure: TaskStructure) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], freeze_json(structure.to_dict()))
