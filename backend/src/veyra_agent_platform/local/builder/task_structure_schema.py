"""Closed provider projection of the server-owned TaskStructure contract."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from veyra_agent_platform.contracts.condition import (
    ConditionValidationError,
    condition_expression_schema,
    parse_condition_expression,
    parse_condition_predicate,
)
from veyra_agent_platform.contracts.task_structure import TaskIOField, TaskStructure


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }


def _array(item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item, "maxItems": 24}


_TEXT = {"type": "string", "maxLength": 400}
_NAME = {"type": "string", "maxLength": 63}
_TYPE = {
    "type": "string",
    "enum": [
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
    ],
}
_NAMED_TYPE = _object({"name": _NAME, "type": _TYPE})
_IO = _object(
    {
        "name": _NAME,
        "type": _TYPE,
        "multiple": {"type": "boolean"},
        "required": {"type": "boolean"},
        "cardinality": {"type": "string", "enum": ["single", "multiple", "collection"]},
        "description": _TEXT,
        "source": _TEXT,
    }
)
_BINDING = _object({"input": _NAME, "source": _TEXT})
_BOUNDARY = _object(
    {
        "kind": {
            "type": "string",
            "enum": [
                "reasoning",
                "tool",
                "condition",
                "human_approval",
                "human_input",
                "state",
                "artifact",
                "verification",
                "multimodal",
            ],
        },
        "stage": _NAME,
        "reason": _TEXT,
        "required": {"type": "boolean"},
        "question": _TEXT,
        "expression": condition_expression_schema(),
        "branches": _array(_TEXT),
        "checks": _array(_TEXT),
        "capability": _NAME,
        "entity": _NAME,
        "scope": {
            "type": ["string", "null"],
            "enum": ["run", "conversation", "project", "entity", None],
        },
        "source": _TEXT,
        "approval_class": {
            "type": ["string", "null"],
            "enum": ["business", "tool", None],
        },
        "expected_schema": _array(_NAMED_TYPE),
    }
)
_STATE = _object(
    {
        "entity": _NAME,
        "identity": _NAME,
        "scope": {
            "type": "string",
            "enum": ["run", "conversation", "project", "entity"],
        },
        "fields": _array(
            _object(
                {
                    "name": _NAME,
                    "type": {
                        "type": "string",
                        "enum": [*_TYPE["enum"], "artifact"],
                    },
                }
            )
        ),
        "statuses": _array(_TEXT),
        "revision": {"type": "boolean"},
        "source": _TEXT,
    }
)
_SCHEMA = _object(
    {
        "schema_version": {"type": "string", "enum": ["1.0"]},
        "goal": _TEXT,
        "summary": _TEXT,
        "actors": _array(
            _object(
                {
                    "id": _NAME,
                    "role": _NAME,
                    "capabilities": _array(_NAME),
                    "reason": _TEXT,
                    "inputs": _array(_IO),
                    "outputs": _array(_IO),
                }
            )
        ),
        "stages": _array(
            _object(
                {
                    "id": _NAME,
                    "summary": _TEXT,
                    "actor": _NAME,
                    "source": _TEXT,
                    "input_sources": _array(_BINDING),
                }
            )
        ),
        "entities": _array(_NAME),
        "inputs": _array(_IO),
        "outputs": {**_array(_IO), "minItems": 1},
        "execution_boundaries": _array(_BOUNDARY),
        "lifecycle": _object(
            {
                "persistent": {"type": "boolean"},
                "interaction": {
                    "type": "string",
                    "enum": ["single_run", "multi_turn", "persistent_task"],
                },
                "entity": _NAME,
            }
        ),
        "orchestration_complexity": {
            "type": "string",
            "enum": ["single", "branched", "multi_actor", "unsupported"],
        },
        "uncertainty": _array(_TEXT),
        "constraints": _array(_TEXT),
        "success_criteria": _array(_TEXT),
        "skill_choices": {
            "type": "array",
            "maxItems": 8,
            "items": _object(
                {
                    "actor": _NAME,
                    "capability": _NAME,
                    "reference": {"type": "string", "maxLength": 512},
                    "reason": _TEXT,
                }
            ),
        },
        "filesystem_write_roots": {
            "type": "array",
            "maxItems": 8,
            "items": {"type": "string", "maxLength": 512},
        },
        "protect_input_files": {
            "type": "boolean",
            "description": (
                "Protect original input files when they must not be modified. "
                "Keep false for file editing tasks."
            ),
        },
        "protected_input_fields": {
            "type": "array",
            "items": _NAME,
            "description": (
                "Task input names containing Project file paths or immutable "
                "file references; never arbitrary prose strings."
            ),
        },
        "state": {"anyOf": [_STATE, {"type": "null"}]},
        "user_requested_surface": {"type": "string", "enum": ["", "agent", "workflow"]},
        "user_shape_override": {
            "type": "string",
            "enum": ["", "PURE_AGENT", "WORKFLOW"],
        },
    }
)


def task_structure_schema() -> dict[str, Any]:
    """Arrays of named fields avoid unbounded model-generated JSON properties."""
    return deepcopy(_SCHEMA)


def task_structure_projection(structure: TaskStructure) -> dict[str, Any]:
    """Serialize a server-owned contract into the complete Provider wire shape.

    This is not a repair or validator for Provider payloads. Identities, types,
    cardinalities and method choices remain unchanged; wire validation still
    decides whether the representation satisfies Provider limits.
    """
    if not isinstance(structure, TaskStructure):
        raise TypeError("Projection requires a server-owned TaskStructure")
    state = structure.state
    return {
        "schema_version": structure.schema_version,
        "goal": structure.goal,
        "summary": structure.summary,
        "actors": [
            {
                "id": actor.id,
                "role": actor.role,
                "capabilities": list(actor.capabilities),
                "reason": actor.reason,
                "inputs": [_io_projection(field) for field in actor.inputs],
                "outputs": [_io_projection(field) for field in actor.outputs],
            }
            for actor in structure.actors
        ],
        "stages": [
            {
                "id": stage.id,
                "summary": stage.summary,
                "actor": stage.actor,
                "source": stage.source,
                "input_sources": [
                    {"input": name, "source": source}
                    for name, source in (stage.input_sources or {}).items()
                ],
            }
            for stage in structure.stages
        ],
        "entities": list(structure.entities),
        "inputs": [_io_projection(field) for field in structure.inputs],
        "outputs": [_io_projection(field) for field in structure.outputs],
        "execution_boundaries": [
            {
                "kind": boundary.kind,
                "stage": boundary.stage,
                "reason": boundary.reason,
                "required": boundary.required,
                "question": boundary.question,
                "expression": boundary.expression,
                "branches": list(boundary.branches),
                "checks": list(boundary.checks),
                "capability": boundary.capability,
                "entity": boundary.entity,
                "scope": boundary.scope,
                "source": boundary.source,
                "approval_class": boundary.approval_class,
                "expected_schema": [
                    {"name": name, "type": kind}
                    for name, kind in (boundary.expected_schema or {}).items()
                ],
            }
            for boundary in structure.execution_boundaries
        ],
        "lifecycle": {
            "persistent": structure.lifecycle.persistent,
            "interaction": structure.lifecycle.interaction,
            "entity": structure.lifecycle.entity,
        },
        "orchestration_complexity": structure.orchestration_complexity,
        "uncertainty": list(structure.uncertainty),
        "constraints": list(structure.constraints),
        "success_criteria": list(structure.success_criteria),
        "skill_choices": [choice.to_dict() for choice in structure.skill_choices],
        "filesystem_write_roots": list(structure.filesystem_write_roots),
        "protect_input_files": structure.protect_input_files,
        "protected_input_fields": list(structure.protected_input_fields),
        "state": None
        if state is None
        else {
            "entity": state.entity,
            "identity": state.identity,
            "scope": state.scope,
            "fields": [
                {"name": name, "type": kind} for name, kind in state.fields.items()
            ],
            "statuses": list(state.statuses),
            "revision": state.revision,
            "source": state.source,
        },
        "user_requested_surface": structure.user_requested_surface,
        "user_shape_override": structure.user_shape_override,
    }


def _io_projection(field: TaskIOField) -> dict[str, Any]:
    return {
        "name": field.name,
        "type": field.type,
        "multiple": field.multiple,
        "required": field.required,
        "cardinality": field.cardinality,
        "description": field.description,
        "source": field.source,
    }


def task_structure_json_intake_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Validate supplied values before applying the contract's documented defaults.

    Constrained decoding may require every projection member, but missing optional
    metadata is not a semantic error. Intake is identical in either Provider mode.
    Both named arrays and canonical field mappings have the same typed values.
    """
    result = deepcopy(schema)
    result["required"] = ["schema_version", "goal", "summary", "lifecycle", "outputs"]
    properties = result["properties"]
    properties["actors"]["items"]["required"] = ["id", "role"]
    stage = properties["stages"]["items"]
    stage["required"] = ["id", "summary"]
    stage["properties"]["input_sources"] = _mapping_intake(
        stage["properties"]["input_sources"], _TEXT
    )
    boundary = properties["execution_boundaries"]["items"]
    boundary["required"] = ["kind", "stage", "reason"]
    boundary["properties"]["expected_schema"] = _mapping_intake(
        boundary["properties"]["expected_schema"], _TYPE
    )
    properties["lifecycle"]["required"] = ["persistent"]
    state = properties["state"]["anyOf"][0]
    state["required"] = ["entity", "identity", "scope"]
    state["properties"]["fields"] = _mapping_intake(
        state["properties"]["fields"],
        state["properties"]["fields"]["items"]["properties"]["type"],
    )

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("properties") == _IO["properties"]:
                value["required"] = ["name", "type"]
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(result)
    return result


def _mapping_intake(array: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    return {
        "anyOf": [
            array,
            {
                "type": "object",
                "maxProperties": 24,
                "propertyNames": {**_NAME, "minLength": 1},
                "additionalProperties": deepcopy(value),
            },
        ]
    }


def complete_task_io_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Fill only documented defaults after the JSON intake schema has passed."""
    result = deepcopy(payload)
    containers = [result, *result.get("actors", [])]
    for container in containers:
        for kind in ("inputs", "outputs"):
            for index, item in enumerate(container.get(kind, [])):
                defaults = _io_projection(
                    TaskIOField.from_dict(item, f"{kind}[{index}]")
                )
                # Explicit values remain authoritative; no port, type or source
                # reference is invented or overwritten by normalization.
                container[kind][index] = {**defaults, **item}
    return result


def task_structure_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert the provider projection; ordinary contract mappings remain valid."""
    value = deepcopy(payload)
    for stage in value.get("stages", []):
        if isinstance(stage, dict) and isinstance(stage.get("input_sources"), list):
            stage["input_sources"] = _named_mapping(
                stage["input_sources"], "input", "source"
            )
    for index, boundary in enumerate(value.get("execution_boundaries", [])):
        if isinstance(boundary, dict) and boundary.get("kind") == "condition":
            expression = boundary.get("expression")
            location = f"execution_boundaries[{index}].expression"
            if isinstance(expression, dict):
                expression = parse_condition_predicate(
                    expression, field_name=location
                ).to_text()
                boundary["expression"] = expression
            else:
                parse_condition_expression(expression, field_name=location)
            # ExecutionBoundary historically clips strings at 240 characters.
            # Reject overflow before that normalization can change a predicate.
            if isinstance(expression, str) and len(expression) > 240:
                raise ConditionValidationError("expression_too_long", location)
        if isinstance(boundary, dict) and isinstance(
            boundary.get("expected_schema"), list
        ):
            boundary["expected_schema"] = _named_mapping(
                boundary["expected_schema"], "name", "type"
            )
    state = value.get("state")
    if isinstance(state, dict) and isinstance(state.get("fields"), list):
        state["fields"] = _named_mapping(state["fields"], "name", "type")
    return value


def _named_mapping(items: list[Any], key: str, field: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != {key, field}:
            raise ValueError("Planner field mapping must use the declared projection")
        name, source = item[key], item[field]
        if (
            not isinstance(name, str)
            or not isinstance(source, str)
            or not name
            or name in mapping
        ):
            raise ValueError(
                "Planner field mapping contains an invalid or duplicate name"
            )
        mapping[name] = source
    return mapping
