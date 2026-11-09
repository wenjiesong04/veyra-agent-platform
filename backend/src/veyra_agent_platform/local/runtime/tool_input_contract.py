"""Pre-effect Tool input checks with safe, schema-owned repair evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.typed_io import (
    parse_typed_field,
    value_matches_field,
)
from veyra_agent_platform.local.mcp.schema import (
    McpSchemaError,
    public_parameter_path,
    require_contract,
    validate_value,
)


@dataclass(frozen=True)
class ToolInputIssue:
    message: str
    violations: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": "tool_input",
            "summary": self.message,
            "violations": [dict(item) for item in self.violations],
        }


def native_input_constraints(spec: Mapping[str, Any]) -> dict[str, Any]:
    from .service import RuntimeError

    raw = spec.get("input_constraints") or {}
    if not isinstance(raw, Mapping):
        raise RuntimeError(
            "tool_schema_invalid", "Tool input constraints must be a named map"
        )
    constraints = dict(raw)
    if spec.get("adapter") == "veyra.runtime.entity.query":
        from veyra_agent_platform.local.state.entity_store import (
            _QUERY_MAX_FILTERS,
            _QUERY_MAX_RECORDS,
        )

        constraints.update(
            {
                "limit": {"minimum": 1, "maximum": _QUERY_MAX_RECORDS},
                "filters": {"maxProperties": _QUERY_MAX_FILTERS},
            }
        )
    return constraints


def _json_issue(
    schema: dict[str, Any], value: Any, *, code: str
) -> ToolInputIssue | None:
    from .service import RuntimeError

    try:
        validate_value(schema, value, code=code)
    except McpSchemaError as exc:
        if exc.code != code:
            raise RuntimeError(exc.code, "Tool schema contract is not ready") from exc
        return ToolInputIssue(
            "Arguments do not match the declared JSON input schema.", exc.diagnostics
        )
    return None


def tool_input_issue(
    resource: Mapping[str, Any] | None, raw_arguments: Any
) -> ToolInputIssue | None:
    from .service import RuntimeError

    if not isinstance(raw_arguments, dict):
        return ToolInputIssue(
            "Arguments must be a JSON object matching the input schema.",
            (
                {
                    "category": "type",
                    "location": "/arguments",
                    "expected_type": "object",
                },
            ),
        )
    spec = dict((resource or {}).get("spec") or {})
    if spec.get("adapter") == "veyra.runtime.mcp.call":
        try:
            schema, _ = require_contract(spec)
        except McpSchemaError as exc:
            raise RuntimeError(exc.code, "Tool schema contract is not ready") from exc
        return _json_issue(schema, raw_arguments, code="mcp_input_schema_invalid")
    if isinstance(spec.get("input_json_schema"), Mapping):
        return _json_issue(
            dict(spec["input_json_schema"]),
            raw_arguments,
            code="native_input_schema_invalid",
        )
    schema = spec.get("input_schema") or {}
    try:
        if not isinstance(schema, Mapping) or any(
            not isinstance(name, str) or not name or len(name) > 128 for name in schema
        ):
            raise ContractValidationError("Tool input schema must be a named map")
        fields = {
            name: parse_typed_field(value, f"tool.inputs.{name}")
            for name, value in schema.items()
        }
    except ContractValidationError as exc:
        raise RuntimeError(
            "tool_schema_invalid", "Tool schema contract is invalid"
        ) from exc
    public_schema: dict[str, Any] = {"properties": {name: {} for name in fields}}
    if set(raw_arguments) - set(fields):
        return ToolInputIssue(
            "Arguments include names not declared in the input schema.",
            (
                {
                    "category": "additionalProperties",
                    "location": "/arguments",
                    "allowed_parameters": [
                        public_parameter_path(public_schema, [name]) for name in fields
                    ],
                },
            ),
        )
    missing = [
        name
        for name, value in schema.items()
        if isinstance(value, Mapping)
        and value.get("required") is True
        and name not in raw_arguments
    ]
    if missing:
        return ToolInputIssue(
            "Arguments are missing a parameter explicitly declared required.",
            tuple(
                {
                    "category": "required",
                    "location": public_parameter_path(public_schema, [name]),
                }
                for name in missing[:8]
            ),
        )
    invalid = [
        name
        for name, value in raw_arguments.items()
        if not value_matches_field(fields[name], value)
    ]
    if invalid:
        return ToolInputIssue(
            "Argument types do not match the input schema.",
            tuple(
                {
                    "category": "type",
                    "location": public_parameter_path(public_schema, [name]),
                    "expected_type": fields[name].compact_type,
                }
                for name in invalid[:8]
            ),
        )
    constraints = native_input_constraints(spec)
    if constraints:
        try:
            issue = _json_issue(
                {"type": "object", "properties": constraints},
                raw_arguments,
                code="native_input_schema_invalid",
            )
        except RuntimeError as exc:
            if exc.code == "mcp_schema_unsupported":
                raise RuntimeError(
                    "tool_schema_invalid", "Tool input constraints are invalid"
                ) from exc
            raise
        if issue:
            return ToolInputIssue(
                "Arguments exceed the permitted input constraints.", issue.violations
            )
    return None
