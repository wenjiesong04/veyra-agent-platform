"""Closed provider projection of the server-owned TaskStructure contract."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


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
        "expression": _TEXT,
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
        "outputs": _array(_IO),
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


def task_structure_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert the provider projection; ordinary contract mappings remain valid."""
    value = deepcopy(payload)
    for stage in value.get("stages", []):
        if isinstance(stage, dict) and isinstance(stage.get("input_sources"), list):
            stage["input_sources"] = _named_mapping(
                stage["input_sources"], "input", "source"
            )
    for boundary in value.get("execution_boundaries", []):
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
