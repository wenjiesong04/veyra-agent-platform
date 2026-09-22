"""Provider-facing AgentSemanticPlan. Canonical storage remains AgentBlueprint.

V1 plans describe intent with ``steps: string[]``. Graph intent adds
``step_intents`` so the model can name duties, dependencies, semantic branches,
and typed output mappings without emitting node IDs, edges, locks, permissions,
or canvas coordinates. The server owns canonical IDs, ports, and transitions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, cast

from .common import (
    SCHEMA_VERSION,
    ContractValidationError,
    require_keys,
    require_list,
    require_mapping,
    require_schema_version,
    require_string,
)
from .typed_io import COMPACT_TYPES, CompactFieldType

FieldType = CompactFieldType
OperationKind = Literal[
    "model",
    "capability",
    "transform",
    "condition",
    "approval",
    "verification",
]
_FIELD_TYPES = set(COMPACT_TYPES)
_OPERATION_KINDS = {
    "model",
    "capability",
    "transform",
    "condition",
    "approval",
    "verification",
}
_STEP_INTENT_FIELDS = {
    "semantic_key",
    "name",
    "purpose",
    "operation_kind",
    "depends_on",
    "capability_requirement",
    "dependency_requirement",
    "reusable_capability",
    "inputs",
    "outputs",
    "branches",
    "branch_condition",
    "branch_key",
    "output_mapping",
}
_BRANCH_FIELDS = {"key", "label"}
_HASH = re.compile(r"^[0-9a-f]{64}$")
_UUID7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_FORBIDDEN = (
    "source.lock",
    "knowledge_refs",
    "resource hash",
    "canvas",
    "etag",
    "revision",
)


@dataclass(frozen=True)
class SemanticField:
    name: str
    type: FieldType
    description: str
    multiple: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "type": self.type}
        if self.description:
            payload["description"] = self.description
        if self.multiple:
            payload["multiple"] = True
        return payload


@dataclass(frozen=True)
class SemanticBranch:
    """A provider-named branch of one semantic Condition intent."""

    key: str
    label: str

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "label": self.label}


@dataclass(frozen=True)
class SemanticStepIntent:
    semantic_key: str
    name: str
    purpose: str
    operation_kind: OperationKind
    depends_on: tuple[str, ...]
    capability_requirement: str = ""
    dependency_requirement: str = ""
    reusable_capability: bool = False
    inputs: tuple[SemanticField, ...] = ()
    outputs: tuple[SemanticField, ...] = ()
    branches: tuple[SemanticBranch, ...] = ()
    branch_condition: str = ""
    branch_key: str = ""
    output_mapping: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "semantic_key": self.semantic_key,
            "name": self.name,
            "purpose": self.purpose,
            "operation_kind": self.operation_kind,
        }
        if self.depends_on:
            payload["depends_on"] = list(self.depends_on)
        if self.capability_requirement:
            payload["capability_requirement"] = self.capability_requirement
        if self.dependency_requirement:
            payload["dependency_requirement"] = self.dependency_requirement
        if self.reusable_capability:
            payload["reusable_capability"] = True
        if self.inputs:
            payload["inputs"] = [item.to_dict() for item in self.inputs]
        if self.outputs:
            payload["outputs"] = [item.to_dict() for item in self.outputs]
        if self.branches:
            payload["branches"] = [item.to_dict() for item in self.branches]
        if self.branch_condition:
            payload["branch_condition"] = self.branch_condition
        if self.branch_key:
            payload["branch_key"] = self.branch_key
        if self.output_mapping:
            payload["output_mapping"] = dict(self.output_mapping)
        return payload


@dataclass(frozen=True)
class AgentSemanticPlanV1:
    schema_version: str
    goal: str
    suggested_name: str
    description: str
    inputs: tuple[SemanticField, ...]
    outputs: tuple[SemanticField, ...]
    steps: tuple[str, ...]
    capability_intents: tuple[str, ...]
    knowledge_intents: tuple[str, ...]
    approval_points: tuple[str, ...]
    success_criteria: tuple[str, ...]
    user_constraints: tuple[str, ...]
    step_intents: tuple[SemanticStepIntent, ...] = ()

    @classmethod
    def from_dict(cls, data: Any) -> AgentSemanticPlanV1:
        item = require_mapping(data, "semantic plan")
        required = {
            "schema_version",
            "goal",
            "suggested_name",
            "description",
            "inputs",
            "outputs",
            "steps",
            "capability_intents",
            "knowledge_intents",
            "approval_points",
            "success_criteria",
            "user_constraints",
        }
        require_keys(item, allowed=required | {"step_intents"}, required=required)
        require_schema_version(item)
        plan = cls(
            schema_version=SCHEMA_VERSION,
            goal=_text(item["goal"], "goal", 2000),
            suggested_name=_text(item["suggested_name"], "suggested_name", 80),
            description=_text(item["description"], "description", 2000),
            inputs=_fields(item["inputs"], "inputs", 16),
            outputs=_fields(item["outputs"], "outputs", 8),
            steps=_phrases(item["steps"], "steps", 12, required=True),
            capability_intents=_phrases(
                item["capability_intents"], "capability_intents", 8
            ),
            knowledge_intents=_phrases(
                item["knowledge_intents"], "knowledge_intents", 8
            ),
            approval_points=_phrases(item["approval_points"], "approval_points", 4),
            success_criteria=_phrases(item["success_criteria"], "success_criteria", 8),
            user_constraints=_phrases(item["user_constraints"], "user_constraints", 8),
            step_intents=_step_intents(item.get("step_intents")),
        )
        if not plan.inputs or not plan.outputs:
            raise ContractValidationError("semantic plan needs inputs and outputs")
        return plan

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "goal": self.goal,
            "suggested_name": self.suggested_name,
            "description": self.description,
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "steps": list(self.steps),
            "capability_intents": list(self.capability_intents),
            "knowledge_intents": list(self.knowledge_intents),
            "approval_points": list(self.approval_points),
            "success_criteria": list(self.success_criteria),
            "user_constraints": list(self.user_constraints),
        }
        if self.step_intents:
            payload["step_intents"] = [item.to_dict() for item in self.step_intents]
        return payload


def _step_intents(value: Any) -> tuple[SemanticStepIntent, ...]:
    if value is None:
        return ()
    items = require_list(value, "step_intents")
    if len(items) > 12:
        raise ContractValidationError("step_intents exceeds 12 items")
    parsed: list[SemanticStepIntent] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        record = require_mapping(item, f"step_intents[{index}]")
        require_keys(
            record,
            allowed=_STEP_INTENT_FIELDS,
            required={"semantic_key", "name", "purpose", "operation_kind"},
            field=f"step_intents[{index}]",
        )
        key = _text(record["semantic_key"], f"step_intents[{index}].semantic_key", 64)
        folded = key.casefold()
        if folded in seen:
            raise ContractValidationError(
                f"step_intents[{index}].semantic_key must be unique"
            )
        seen.add(folded)
        kind = record["operation_kind"]
        if kind not in _OPERATION_KINDS:
            raise ContractValidationError(
                f"step_intents[{index}].operation_kind is not supported"
            )
        depends_on = _phrases(
            record.get("depends_on") or [],
            f"step_intents[{index}].depends_on",
            8,
        )
        requirement = _optional_text(
            record.get("capability_requirement"),
            f"step_intents[{index}].capability_requirement",
            240,
        )
        reusable = record.get("reusable_capability", False)
        if not isinstance(reusable, bool):
            raise ContractValidationError(
                f"step_intents[{index}].reusable_capability must be a boolean"
            )
        dependency_requirement = _optional_text(
            record.get("dependency_requirement"),
            f"step_intents[{index}].dependency_requirement",
            240,
        )
        inputs = _fields(record.get("inputs", []), f"step_intents[{index}].inputs", 16)
        outputs = _fields(
            record.get("outputs", []), f"step_intents[{index}].outputs", 8
        )
        branches = _branches(record.get("branches"), f"step_intents[{index}].branches")
        if branches and kind != "condition":
            raise ContractValidationError(
                f"step_intents[{index}].branches is only valid for condition steps"
            )
        branch_condition = _optional_text(
            record.get("branch_condition"),
            f"step_intents[{index}].branch_condition",
            64,
        )
        branch_key = _optional_text(
            record.get("branch_key"), f"step_intents[{index}].branch_key", 64
        )
        if bool(branch_condition) != bool(branch_key):
            raise ContractValidationError(
                f"step_intents[{index}] must provide both branch_condition "
                "and branch_key"
            )
        output_mapping = _output_mapping(
            record.get("output_mapping"), f"step_intents[{index}].output_mapping"
        )
        if output_mapping and kind != "transform":
            raise ContractValidationError(
                f"step_intents[{index}].output_mapping is only valid for "
                "transform steps"
            )
        if requirement and kind != "capability" and not reusable:
            raise ContractValidationError(
                f"step_intents[{index}].capability_requirement is only valid "
                "for operation_kind=capability or reusable capabilities"
            )
        if dependency_requirement and (not reusable or kind != "capability"):
            raise ContractValidationError(
                f"step_intents[{index}].dependency_requirement is only valid "
                "for reusable capability steps"
            )
        if reusable and (not requirement or not inputs or not outputs):
            raise ContractValidationError(
                f"step_intents[{index}] reusable capability needs a semantic "
                "requirement, inputs, and outputs"
            )
        parsed.append(
            SemanticStepIntent(
                semantic_key=key,
                name=_text(record["name"], f"step_intents[{index}].name", 80),
                purpose=_text(record["purpose"], f"step_intents[{index}].purpose", 240),
                operation_kind=cast(OperationKind, kind),
                depends_on=depends_on,
                capability_requirement=requirement,
                dependency_requirement=dependency_requirement,
                reusable_capability=reusable,
                inputs=inputs,
                outputs=outputs,
                branches=branches,
                branch_condition=branch_condition,
                branch_key=branch_key,
                output_mapping=output_mapping,
            )
        )
    keys = {item.semantic_key.casefold(): item.semantic_key for item in parsed}
    for item in parsed:
        if item.operation_kind == "condition" and not item.branches:
            raise ContractValidationError(
                f"step_intents[{item.semantic_key}] condition must declare "
                "exactly two branches"
            )
        if item.branches and len(item.branches) != 2:
            raise ContractValidationError(
                f"step_intents[{item.semantic_key}] must declare exactly two branches"
            )
        for dependency in item.depends_on:
            if dependency.casefold() not in keys:
                raise ContractValidationError(
                    f"step_intents[{item.semantic_key}].depends_on references "
                    f"unknown key {dependency}"
                )
            if dependency.casefold() == item.semantic_key.casefold():
                raise ContractValidationError(
                    f"step_intents[{item.semantic_key}] cannot depend on itself"
                )
        if item.branch_condition:
            condition = keys.get(item.branch_condition.casefold())
            if condition is None:
                raise ContractValidationError(
                    f"step_intents[{item.semantic_key}].branch_condition references "
                    f"unknown key {item.branch_condition}"
                )
            parent = next(step for step in parsed if step.semantic_key == condition)
            if parent.operation_kind != "condition":
                raise ContractValidationError(
                    f"step_intents[{item.semantic_key}].branch_condition must "
                    "reference a condition"
                )
            branch_keys = {branch.key.casefold() for branch in parent.branches}
            if item.branch_key.casefold() not in branch_keys:
                raise ContractValidationError(
                    f"step_intents[{item.semantic_key}].branch_key is not declared by "
                    f"{parent.semantic_key}"
                )
            same_branch = {
                step.semantic_key.casefold()
                for step in parsed
                if step.branch_condition.casefold() == parent.semantic_key.casefold()
                and step.branch_key.casefold() == item.branch_key.casefold()
            }
            for dependency in item.depends_on:
                if dependency.casefold() == parent.semantic_key.casefold():
                    continue
                if dependency.casefold() not in same_branch:
                    raise ContractValidationError(
                        f"step_intents[{item.semantic_key}] cannot depend on a "
                        "sibling branch"
                    )
    _reject_cycles(parsed)
    return tuple(parsed)


def _branches(value: Any, field: str) -> tuple[SemanticBranch, ...]:
    if value is None:
        return ()
    items = require_list(value, field)
    if len(items) != 2:
        raise ContractValidationError(f"{field} must contain exactly two branches")
    parsed: list[SemanticBranch] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        record = require_mapping(item, f"{field}[{index}]")
        require_keys(
            record,
            allowed=_BRANCH_FIELDS,
            required=_BRANCH_FIELDS,
            field=f"{field}[{index}]",
        )
        key = _text(record["key"], f"{field}[{index}].key", 64)
        folded = key.casefold()
        if folded in seen:
            raise ContractValidationError(f"{field} branch keys must be unique")
        seen.add(folded)
        parsed.append(
            SemanticBranch(
                key=key,
                label=_text(record["label"], f"{field}[{index}].label", 80),
            )
        )
    return tuple(parsed)


def _output_mapping(value: Any, field: str) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    record = require_mapping(value, field)
    if not record or len(record) > 8:
        raise ContractValidationError(f"{field} must contain 1 to 8 mappings")
    parsed: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, template in record.items():
        name = _text(key, f"{field} key", 80)
        folded = name.casefold()
        if folded in seen:
            raise ContractValidationError(f"{field} keys must be unique")
        seen.add(folded)
        parsed.append((name, _text(template, f"{field}.{name}", 240)))
    return tuple(parsed)


def _reject_cycles(steps: list[SemanticStepIntent]) -> None:
    dependents: dict[str, list[str]] = {
        item.semantic_key.casefold(): [] for item in steps
    }
    for item in steps:
        for dependency in item.depends_on:
            dependents[dependency.casefold()].append(item.semantic_key.casefold())
    visiting: set[str] = set()
    seen: set[str] = set()

    def walk(node: str) -> None:
        if node in seen:
            return
        if node in visiting:
            raise ContractValidationError("step_intents contains a cycle")
        visiting.add(node)
        for child in dependents[node]:
            walk(child)
        visiting.remove(node)
        seen.add(node)

    for key in dependents:
        walk(key)


def _fields(value: Any, field: str, limit: int) -> tuple[SemanticField, ...]:
    items = require_list(value, field)
    if len(items) > limit:
        raise ContractValidationError(f"{field} exceeds {limit} items")
    parsed: list[SemanticField] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        record = require_mapping(item, f"{field}[{index}]")
        require_keys(
            record,
            allowed={"name", "type", "description", "multiple"},
            required={"name", "type"},
        )
        name = _text(record["name"], f"{field}[{index}].name", 80)
        kind = record["type"]
        if kind not in _FIELD_TYPES:
            raise ContractValidationError(f"{field}[{index}].type is not supported")
        multiple = record.get("multiple")
        if multiple is None:
            many = False
        elif isinstance(multiple, bool):
            many = multiple
        else:
            raise ContractValidationError(
                f"{field}[{index}].multiple must be a boolean"
            )
        key = name.casefold()
        if key in seen:
            raise ContractValidationError(f"{field} names must be unique")
        seen.add(key)
        parsed.append(
            SemanticField(
                name=name,
                type=cast(FieldType, kind),
                description=_optional_text(
                    record.get("description"), f"{field}[{index}].description", 240
                ),
                multiple=many,
            )
        )
    return tuple(parsed)


def _phrases(
    value: Any, field: str, limit: int, *, required: bool = False
) -> tuple[str, ...]:
    items = require_list(value, field)
    if required and not items:
        raise ContractValidationError(f"{field} must not be empty")
    if len(items) > limit:
        raise ContractValidationError(f"{field} exceeds {limit} items")
    return tuple(
        _text(item, f"{field}[{index}]", 240) for index, item in enumerate(items)
    )


def _optional_text(value: Any, field: str, limit: int) -> str:
    if value is None:
        return ""
    return _text(value, field, limit)


def _text(value: Any, field: str, limit: int) -> str:
    text = require_string(value, field).strip()
    if not text:
        raise ContractValidationError(f"{field} must be a non-empty string")
    if len(text) > limit:
        raise ContractValidationError(f"{field} exceeds {limit} characters")
    lowered = text.casefold()
    if _HASH.fullmatch(text) or _UUID7.fullmatch(text):
        raise ContractValidationError(f"{field} must not include Veyra internals")
    if any(token in lowered for token in _FORBIDDEN):
        raise ContractValidationError(f"{field} must not include Veyra internals")
    if text.startswith("/") or ":\\" in text:
        raise ContractValidationError(f"{field} must not include filesystem roots")
    return text
