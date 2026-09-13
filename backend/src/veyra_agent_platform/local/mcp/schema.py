"""Bounded, offline JSON Schema contracts for discovered MCP tools."""

from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped]

from veyra_agent_platform.contracts.canonical import sha256_digest

_MAX_SCHEMA_BYTES = 65_536
_MAX_SCHEMA_DEPTH = 16
_MAX_SCHEMA_NODES = 256
_KEYWORDS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "enum",
    "title",
    "description",
    "default",
    "examples",
    "$schema",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minProperties",
    "maxProperties",
}


class McpSchemaError(ValueError):
    """A schema failure with a fixed code; never expose validator messages."""

    def __init__(self, code: str = "mcp_schema_unsupported") -> None:
        super().__init__(code)
        self.code = code


def _check_schema(schema: Any, *, root: bool = True) -> None:
    if root and not isinstance(schema, dict):
        raise McpSchemaError()
    pending = [(schema, 0)]
    visited = 0
    while pending:
        current, depth = pending.pop()
        visited += 1
        if depth > _MAX_SCHEMA_DEPTH or visited > _MAX_SCHEMA_NODES:
            raise McpSchemaError()
        if isinstance(current, bool):
            continue
        if not isinstance(current, dict) or set(current) - _KEYWORDS:
            raise McpSchemaError()
        if "$schema" in current and current["$schema"] != (
            "https://json-schema.org/draft/2020-12/schema"
        ):
            raise McpSchemaError()
        properties = current.get("properties", {})
        if not isinstance(properties, dict):
            raise McpSchemaError()
        pending.extend((child, depth + 1) for child in properties.values())
        for keyword in ("items", "additionalProperties"):
            if keyword in current:
                pending.append((current[keyword], depth + 1))
    try:
        Draft202012Validator.check_schema(schema)
    except (SchemaError, RecursionError, TypeError, ValueError) as exc:
        raise McpSchemaError() from exc


def prepare_contract(input_schema: Any, output_schema: Any = None) -> dict[str, Any]:
    """Retain JSON constraints in the catalog hash, including unsupported ones.

    Unsupported contracts remain inspectable but cannot be approved or executed.
    No reference resolver, custom format, or external schema is ever enabled.
    """
    material = {"input": input_schema, "output": output_schema}
    try:
        encoded = json.dumps(material, allow_nan=False, sort_keys=True)
        if len(encoded.encode("utf-8")) > _MAX_SCHEMA_BYTES:
            raise McpSchemaError()
        normalized = json.loads(encoded)
    except (ValueError, TypeError, RecursionError):
        return {
            "schema_status": "unsupported",
            "schema_code": "mcp_schema_unsupported",
        }
    supported = True
    try:
        _check_schema(normalized["input"])
        if normalized["output"] is not None:
            _check_schema(normalized["output"])
    except McpSchemaError:
        supported = False
    return {
        "input_json_schema": normalized["input"],
        "output_json_schema": normalized["output"],
        "schema_contract_hash": sha256_digest(normalized),
        "schema_status": "supported" if supported else "unsupported",
        "schema_code": "ready" if supported else "mcp_schema_unsupported",
    }


def require_contract(spec: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    """Fail closed for legacy, unsupported, or tampered descriptors."""
    prepared = prepare_contract(
        spec.get("input_json_schema"), spec.get("output_json_schema")
    )
    if prepared["schema_status"] != "supported" or any(
        spec.get(key) != value for key, value in prepared.items()
    ):
        raise McpSchemaError()
    return prepared["input_json_schema"], prepared["output_json_schema"]


def validate_value(schema: dict[str, Any], value: Any, *, code: str) -> None:
    """Validate only a checked offline contract and return no sensitive details."""
    _check_schema(schema)
    try:
        json.dumps(value, allow_nan=False)
        valid = Draft202012Validator(schema).is_valid(value)
    except (ValueError, TypeError, RecursionError):
        valid = False
    if not valid:
        raise McpSchemaError(code)
