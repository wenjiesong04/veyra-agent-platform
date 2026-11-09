"""Builder-first task understanding. Shape is decided after this, not before."""

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
from .filesystem_scope import normalize_project_scope

BoundaryKind = Literal[
    "reasoning",
    "tool",
    "condition",
    "human_approval",
    "human_input",
    "state",
    "artifact",
    "verification",
    "multimodal",
]
IOCardinality = Literal["single", "multiple", "collection"]
StateScope = Literal["run", "conversation", "project", "entity"]
InteractionModeHint = Literal["single_run", "multi_turn", "persistent_task"]
OrchestrationComplexity = Literal["single", "branched", "multi_actor", "unsupported"]

_BOUNDARY_KINDS = {
    "reasoning",
    "tool",
    "condition",
    "human_approval",
    "human_input",
    "state",
    "artifact",
    "verification",
    "multimodal",
}
_CARDINALITY = {"single", "multiple", "collection"}
_SCOPES = {"run", "conversation", "project", "entity"}
_COMPLEXITY = {"single", "branched", "multi_actor", "unsupported"}
_INTERACTION = {"single_run", "multi_turn", "persistent_task"}
_IO_TYPES = {
    "string",
    "number",
    "integer",
    "boolean",
    "object",
    "array",
    "table",
    "image",
    "pdf",
    "document",
    "file",
    "audio",
    "video",
    "collection",
}
_MAX_ITEMS = 24
_MAX_TEXT = 400


def _clip(value: str, limit: int = _MAX_TEXT) -> str:
    text = value.strip()
    return text[:limit]


def _string_list(value: Any, field: str, *, limit: int = _MAX_ITEMS) -> tuple[str, ...]:
    items = require_list(value, field)
    if len(items) > limit:
        raise ContractValidationError(f"{field} exceeds {limit} items")
    result: list[str] = []
    for index, item in enumerate(items):
        text = _clip(require_string(item, f"{field}[{index}]"))
        if text and text not in result:
            result.append(text)
    return tuple(result)


@dataclass(frozen=True)
class TaskIOField:
    name: str
    type: str
    multiple: bool = False
    required: bool = True
    cardinality: IOCardinality = "single"
    description: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "multiple": self.multiple,
            "required": self.required,
            "cardinality": self.cardinality,
        }
        if self.description:
            payload["description"] = self.description
        if self.source:
            payload["source"] = self.source
        return payload

    @classmethod
    def from_dict(cls, data: Any, field: str) -> TaskIOField:
        item = require_mapping(data, field)
        require_keys(
            item,
            allowed={
                "name",
                "type",
                "multiple",
                "required",
                "cardinality",
                "description",
                "source",
            },
            required={"name", "type"},
        )
        kind = require_string(item["type"], f"{field}.type")
        if kind not in _IO_TYPES:
            raise ContractValidationError(f"{field}.type is not supported")
        multiple = item.get("multiple", False)
        if not isinstance(multiple, bool):
            raise ContractValidationError(f"{field}.multiple must be boolean")
        required = item.get("required", True)
        if not isinstance(required, bool):
            raise ContractValidationError(f"{field}.required must be boolean")
        cardinality = str(
            item.get("cardinality") or ("multiple" if multiple else "single")
        )
        if cardinality not in _CARDINALITY:
            raise ContractValidationError(f"{field}.cardinality is invalid")
        if cardinality == "multiple":
            multiple = True
        if cardinality == "collection" and kind not in {"collection", "file", "image"}:
            kind = "collection"
        return cls(
            name=_clip(require_string(item["name"], f"{field}.name"), 63),
            type=kind,
            multiple=multiple,
            required=required,
            cardinality=cardinality,  # type: ignore[arg-type]
            description=_clip(str(item.get("description") or "")),
            source=_clip(str(item.get("source") or "")),
        )


@dataclass(frozen=True)
class ExecutionBoundary:
    kind: BoundaryKind
    stage: str
    reason: str
    required: bool = True
    question: str = ""
    expression: str = ""
    branches: tuple[str, ...] = ()
    checks: tuple[str, ...] = ()
    capability: str = ""
    entity: str = ""
    scope: StateScope | None = None
    source: str = ""
    approval_class: Literal["business", "tool"] | None = None
    expected_schema: Mapping[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "stage": self.stage,
            "reason": self.reason,
            "required": self.required,
        }
        if self.question:
            payload["question"] = self.question
        if self.expression:
            payload["expression"] = self.expression
        if self.branches:
            payload["branches"] = list(self.branches)
        if self.checks:
            payload["checks"] = list(self.checks)
        if self.capability:
            payload["capability"] = self.capability
        if self.entity:
            payload["entity"] = self.entity
        if self.scope:
            payload["scope"] = self.scope
        if self.source:
            payload["source"] = self.source
        if self.approval_class:
            payload["approval_class"] = self.approval_class
        if self.expected_schema:
            payload["expected_schema"] = dict(self.expected_schema)
        return payload

    @classmethod
    def from_dict(cls, data: Any, field: str) -> ExecutionBoundary:
        item = require_mapping(data, field)
        require_keys(
            item,
            allowed={
                "kind",
                "stage",
                "reason",
                "required",
                "question",
                "expression",
                "branches",
                "checks",
                "capability",
                "entity",
                "scope",
                "source",
                "approval_class",
                "expected_schema",
                "lifetime",
            },
            required={"kind", "stage", "reason"},
        )
        kind = require_string(item["kind"], f"{field}.kind")
        if kind not in _BOUNDARY_KINDS:
            raise ContractValidationError(f"{field}.kind is unknown")
        required = item.get("required", True)
        if not isinstance(required, bool):
            raise ContractValidationError(f"{field}.required must be boolean")
        scope_raw = item.get("scope")
        scope: StateScope | None = None
        if scope_raw is not None:
            scope_text = require_string(scope_raw, f"{field}.scope")
            if scope_text not in _SCOPES:
                raise ContractValidationError(f"{field}.scope is invalid")
            scope = scope_text  # type: ignore[assignment]
        approval_class = item.get("approval_class")
        if approval_class not in {None, "business", "tool"}:
            raise ContractValidationError(f"{field}.approval_class is invalid")
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
        return cls(
            kind=kind,  # type: ignore[arg-type]
            stage=_clip(require_string(item["stage"], f"{field}.stage"), 80),
            reason=_clip(require_string(item["reason"], f"{field}.reason")),
            required=required,
            question=_clip(str(item.get("question") or "")),
            expression=_clip(str(item.get("expression") or ""), 240),
            branches=_string_list(
                item.get("branches") or [], f"{field}.branches", limit=8
            ),
            checks=_string_list(item.get("checks") or [], f"{field}.checks", limit=12),
            capability=_clip(str(item.get("capability") or ""), 80),
            entity=_clip(str(item.get("entity") or ""), 80),
            scope=scope,
            source=_clip(str(item.get("source") or "")),
            approval_class=approval_class,
            expected_schema=freeze_json(expected) if expected else None,
        )


@dataclass(frozen=True)
class StateRequirement:
    entity: str
    identity: str
    scope: StateScope
    fields: Mapping[str, str]
    statuses: tuple[str, ...]
    revision: bool = True
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "entity": self.entity,
            "identity": self.identity,
            "scope": self.scope,
            "fields": dict(self.fields),
            "statuses": list(self.statuses),
            "revision": self.revision,
        }
        if self.source:
            payload["source"] = self.source
        return payload

    @classmethod
    def from_dict(cls, data: Any, field: str) -> StateRequirement:
        item = require_mapping(data, field)
        require_keys(
            item,
            allowed={
                "entity",
                "identity",
                "scope",
                "fields",
                "statuses",
                "status",
                "revision",
                "source",
            },
            required={"entity", "identity", "scope"},
        )
        scope = require_string(item["scope"], f"{field}.scope")
        if scope not in _SCOPES:
            raise ContractValidationError(f"{field}.scope is invalid")
        fields_raw = item.get("fields") or {}
        mapping = require_mapping(fields_raw, f"{field}.fields")
        fields = {
            require_string(key, f"{field}.fields.key"): require_string(
                value, f"{field}.fields.{key}"
            )
            for key, value in mapping.items()
        }
        statuses = item.get("statuses") or item.get("status") or []
        revision = item.get("revision", True)
        if not isinstance(revision, bool):
            raise ContractValidationError(f"{field}.revision must be boolean")
        return cls(
            entity=_clip(require_string(item["entity"], f"{field}.entity"), 80),
            identity=_clip(require_string(item["identity"], f"{field}.identity"), 80),
            scope=scope,  # type: ignore[arg-type]
            fields=freeze_json(fields),
            statuses=_string_list(statuses, f"{field}.statuses", limit=16),
            revision=revision,
            source=_clip(str(item.get("source") or "")),
        )


@dataclass(frozen=True)
class TaskActor:
    id: str
    role: str
    capabilities: tuple[str, ...]
    reason: str = ""
    inputs: tuple[TaskIOField, ...] = ()
    outputs: tuple[TaskIOField, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "role": self.role,
            "capabilities": list(self.capabilities),
        }
        if self.reason:
            payload["reason"] = self.reason
        if self.inputs:
            payload["inputs"] = [item.to_dict() for item in self.inputs]
        if self.outputs:
            payload["outputs"] = [item.to_dict() for item in self.outputs]
        return payload

    @classmethod
    def from_dict(cls, data: Any, field: str) -> TaskActor:
        item = require_mapping(data, field)
        require_keys(
            item,
            allowed={"id", "role", "capabilities", "reason", "inputs", "outputs"},
            required={"id", "role"},
        )
        return cls(
            id=_clip(require_string(item["id"], f"{field}.id"), 80),
            role=_clip(require_string(item["role"], f"{field}.role"), 80),
            capabilities=_string_list(
                item.get("capabilities") or [], f"{field}.capabilities", limit=16
            ),
            reason=_clip(str(item.get("reason") or "")),
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


def _field_sources(value: Any, field: str) -> dict[str, str]:
    if value is None:
        return {}
    fields = require_mapping(value, field)
    if len(fields) > _MAX_ITEMS:
        raise ContractValidationError(f"{field} exceeds {_MAX_ITEMS} entries")
    return {
        require_string(name, field): require_string(source, f"{field}.{name}")
        for name, source in fields.items()
    }


@dataclass(frozen=True)
class TaskStage:
    id: str
    summary: str
    actor: str = ""
    source: str = ""
    input_sources: Mapping[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.id, "summary": self.summary}
        if self.actor:
            payload["actor"] = self.actor
        if self.source:
            payload["source"] = self.source
        if self.input_sources:
            payload["input_sources"] = dict(self.input_sources)
        return payload

    @classmethod
    def from_dict(cls, data: Any, field: str) -> TaskStage:
        item = require_mapping(data, field)
        require_keys(
            item,
            allowed={"id", "summary", "actor", "source", "input_sources"},
            required={"id", "summary"},
        )
        return cls(
            id=_clip(require_string(item["id"], f"{field}.id"), 80),
            summary=_clip(require_string(item["summary"], f"{field}.summary")),
            actor=_clip(str(item.get("actor") or ""), 80),
            source=_clip(str(item.get("source") or "")),
            input_sources=freeze_json(
                _field_sources(item.get("input_sources"), f"{field}.input_sources")
            ),
        )


@dataclass(frozen=True)
class TaskLifecycle:
    persistent: bool
    interaction: InteractionModeHint
    entity: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "persistent": self.persistent,
            "interaction": self.interaction,
        }
        if self.entity:
            payload["entity"] = self.entity
        return payload

    @classmethod
    def from_dict(cls, data: Any, field: str) -> TaskLifecycle:
        item = require_mapping(data, field)
        require_keys(
            item,
            allowed={"persistent", "interaction", "entity"},
            required={"persistent"},
        )
        persistent = item["persistent"]
        if not isinstance(persistent, bool):
            raise ContractValidationError(f"{field}.persistent must be boolean")
        interaction = str(item.get("interaction") or "single_run")
        if interaction not in _INTERACTION:
            raise ContractValidationError(f"{field}.interaction is invalid")
        return cls(
            persistent=persistent,
            interaction=interaction,  # type: ignore[arg-type]
            entity=_clip(str(item.get("entity") or ""), 80),
        )


@dataclass(frozen=True)
class SkillChoice:
    """A proposed method; the server still resolves its pin and permissions."""

    actor: str
    capability: str
    reference: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "actor": self.actor,
            "capability": self.capability,
            "reference": self.reference,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Any, field: str) -> SkillChoice:
        item = require_mapping(data, field)
        require_keys(
            item,
            allowed={"actor", "capability", "reference", "reason"},
            required={"actor", "capability", "reference", "reason"},
        )
        values = {
            key: require_string(item[key], f"{field}.{key}")
            for key in ("actor", "capability", "reference", "reason")
        }
        for key, value in values.items():
            limit = 512 if key == "reference" else _MAX_TEXT if key == "reason" else 80
            if not value.strip() or value != value.strip() or len(value) > limit:
                raise ContractValidationError(f"{field}.{key} is invalid")
        if values["reference"].count("@") != 1:
            raise ContractValidationError(f"{field}.reference needs an exact version")
        return cls(**values)


@dataclass(frozen=True)
class TaskStructure:
    schema_version: str
    goal: str
    summary: str
    actors: tuple[TaskActor, ...]
    stages: tuple[TaskStage, ...]
    entities: tuple[str, ...]
    inputs: tuple[TaskIOField, ...]
    outputs: tuple[TaskIOField, ...]
    execution_boundaries: tuple[ExecutionBoundary, ...]
    lifecycle: TaskLifecycle
    orchestration_complexity: OrchestrationComplexity
    uncertainty: tuple[str, ...]
    state: StateRequirement | None = None
    user_requested_surface: str = ""
    user_shape_override: str = ""
    constraints: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    skill_choices: tuple[SkillChoice, ...] = ()
    filesystem_write_roots: tuple[str, ...] = ()
    protect_input_files: bool = False
    protected_input_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "goal": self.goal,
            "summary": self.summary,
            "actors": [item.to_dict() for item in self.actors],
            "stages": [item.to_dict() for item in self.stages],
            "entities": list(self.entities),
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "execution_boundaries": [
                item.to_dict() for item in self.execution_boundaries
            ],
            "lifecycle": self.lifecycle.to_dict(),
            "orchestration_complexity": self.orchestration_complexity,
            "uncertainty": list(self.uncertainty),
        }
        if self.constraints:
            payload["constraints"] = list(self.constraints)
        if self.success_criteria:
            payload["success_criteria"] = list(self.success_criteria)
        if self.skill_choices:
            payload["skill_choices"] = [item.to_dict() for item in self.skill_choices]
        if self.filesystem_write_roots:
            payload["filesystem_write_roots"] = list(self.filesystem_write_roots)
        if self.protect_input_files:
            payload["protect_input_files"] = True
        if self.protected_input_fields:
            payload["protected_input_fields"] = list(self.protected_input_fields)
        if self.state is not None:
            payload["state"] = self.state.to_dict()
        if self.user_requested_surface:
            payload["user_requested_surface"] = self.user_requested_surface
        if self.user_shape_override:
            payload["user_shape_override"] = self.user_shape_override
        return cast(dict[str, Any], thaw_json(freeze_json(payload)))

    @classmethod
    def from_dict(cls, data: Any) -> TaskStructure:
        item = require_mapping(data, "task structure")
        require_keys(
            item,
            allowed={
                "schema_version",
                "goal",
                "summary",
                "actors",
                "stages",
                "entities",
                "inputs",
                "outputs",
                "execution_boundaries",
                "lifecycle",
                "orchestration_complexity",
                "uncertainty",
                "state",
                "user_requested_surface",
                "user_shape_override",
                "constraints",
                "success_criteria",
                "skill_choices",
                "filesystem_write_roots",
                "protect_input_files",
                "protected_input_fields",
            },
            required={"schema_version", "goal", "summary", "lifecycle"},
        )
        require_schema_version(item)
        complexity = str(item.get("orchestration_complexity") or "single")
        if complexity not in _COMPLEXITY:
            raise ContractValidationError("orchestration_complexity is invalid")
        state_raw = item.get("state")
        choices = require_list(item.get("skill_choices") or [], "skill_choices")
        if len(choices) > 8:
            raise ContractValidationError("skill_choices exceeds 8 items")
        write_roots = require_list(
            item.get("filesystem_write_roots") or [], "filesystem_write_roots"
        )
        if len(write_roots) > 8:
            raise ContractValidationError("filesystem_write_roots exceeds 8 items")
        roots = tuple(
            dict.fromkeys(
                normalize_project_scope(require_string(value, "filesystem_write_roots"))
                for value in write_roots
            )
        )
        protect_input_files = item.get("protect_input_files", False)
        if not isinstance(protect_input_files, bool):
            raise ContractValidationError("protect_input_files must be boolean")
        protected_input_fields = _string_list(
            item.get("protected_input_fields") or [], "protected_input_fields"
        )
        if protected_input_fields and not protect_input_files:
            raise ContractValidationError(
                "protected_input_fields requires protect_input_files"
            )
        input_names = {
            value.get("name")
            for value in item.get("inputs", [])
            if isinstance(value, Mapping)
        }
        if set(protected_input_fields) - input_names:
            raise ContractValidationError(
                "protected_input_fields must name task inputs"
            )
        return cls(
            schema_version=SCHEMA_VERSION,
            goal=_clip(require_string(item["goal"], "goal")),
            summary=_clip(require_string(item["summary"], "summary")),
            actors=tuple(
                TaskActor.from_dict(value, f"actors[{index}]")
                for index, value in enumerate(
                    require_list(item.get("actors") or [], "actors")
                )
            ),
            stages=tuple(
                TaskStage.from_dict(value, f"stages[{index}]")
                for index, value in enumerate(
                    require_list(item.get("stages") or [], "stages")
                )
            ),
            entities=_string_list(item.get("entities") or [], "entities"),
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
            execution_boundaries=tuple(
                ExecutionBoundary.from_dict(value, f"execution_boundaries[{index}]")
                for index, value in enumerate(
                    require_list(
                        item.get("execution_boundaries") or [], "execution_boundaries"
                    )
                )
            ),
            lifecycle=TaskLifecycle.from_dict(item["lifecycle"], "lifecycle"),
            orchestration_complexity=complexity,  # type: ignore[arg-type]
            uncertainty=_string_list(item.get("uncertainty") or [], "uncertainty"),
            state=(
                StateRequirement.from_dict(state_raw, "state")
                if state_raw is not None
                else None
            ),
            user_requested_surface=_clip(
                str(item.get("user_requested_surface") or ""), 40
            ),
            user_shape_override=_clip(str(item.get("user_shape_override") or ""), 40),
            constraints=_string_list(item.get("constraints") or [], "constraints"),
            success_criteria=_string_list(
                item.get("success_criteria") or [], "success_criteria"
            ),
            skill_choices=tuple(
                SkillChoice.from_dict(value, f"skill_choices[{index}]")
                for index, value in enumerate(choices)
            ),
            filesystem_write_roots=roots,
            protect_input_files=protect_input_files,
            protected_input_fields=protected_input_fields,
        )

    def boundaries_of(self, kind: BoundaryKind) -> tuple[ExecutionBoundary, ...]:
        return tuple(item for item in self.execution_boundaries if item.kind == kind)
