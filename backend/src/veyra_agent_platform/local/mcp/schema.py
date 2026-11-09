"""Bounded, offline JSON Schema contracts for discovered MCP tools."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from itertools import islice
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

    def __init__(
        self,
        code: str = "mcp_schema_unsupported",
        *,
        diagnostics: Sequence[dict[str, Any]] = (),
    ) -> None:
        super().__init__(code)
        self.code = code
        self.diagnostics = tuple(diagnostics)


def public_parameter_path(schema: Any, path: Sequence[Any]) -> str:
    """Only reviewed schema names and array positions may appear in evidence."""
    parts = []
    current = schema
    for segment in path:
        if type(segment) is int:
            parts.append(str(segment))
            current = current.get("items", {}) if isinstance(current, dict) else {}
            continue
        properties = current.get("properties", {}) if isinstance(current, dict) else {}
        declared = isinstance(properties, dict) and segment in properties
        safe = (
            isinstance(segment, str)
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", segment)
            and not segment.startswith(("sk-", "ghp_", "gho_", "AIza"))
        )
        parts.append(segment if declared and safe else "*")
        current = (
            properties[segment]
            if declared
            else current.get("additionalProperties", {})
            if isinstance(current, dict)
            else {}
        )
    return "/arguments" + ("/" + "/".join(parts) if parts else "")


def _validation_diagnostics(schema: dict[str, Any], value: Any) -> list[dict[str, Any]]:
    diagnostics = []
    for error in islice(Draft202012Validator(schema).iter_errors(value), 8):
        category = str(error.validator)
        if category not in _KEYWORDS:
            category = "schema"
        paths = [list(error.absolute_path)]
        if category == "required" and isinstance(error.instance, dict):
            missing = [
                name for name in error.validator_value if name not in error.instance
            ]
            if missing:
                paths = [list(error.absolute_path) + [name] for name in missing]
        item: dict[str, Any] = {"category": category}
        if category == "additionalProperties":
            properties = error.schema.get("properties", {})
            item["allowed_parameters"] = [
                public_parameter_path(schema, list(error.absolute_path) + [name])
                for name in properties
            ][:16]
        if category == "type":
            expected = error.validator_value
            allowed = {
                "null",
                "boolean",
                "object",
                "array",
                "number",
                "integer",
                "string",
            }
            if isinstance(expected, str) and expected in allowed:
                item["expected_type"] = expected
            elif isinstance(expected, list) and all(
                kind in allowed for kind in expected
            ):
                item["expected_type"] = " | ".join(expected)
        if category in {
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "minLength",
            "maxLength",
            "minItems",
            "maxItems",
            "minProperties",
            "maxProperties",
        } and type(error.validator_value) in {int, float}:
            item["limit"] = error.validator_value
        for path in paths:
            located = {**item, "location": public_parameter_path(schema, path)}
            if located not in diagnostics:
                diagnostics.append(located)
            if len(diagnostics) == 8:
                return diagnostics
    return diagnostics


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
        diagnostics = _validation_diagnostics(schema, value)
    except (ValueError, TypeError, RecursionError):
        diagnostics = [{"category": "json_serializable", "location": "/arguments"}]
    if diagnostics:
        raise McpSchemaError(code, diagnostics=diagnostics)
