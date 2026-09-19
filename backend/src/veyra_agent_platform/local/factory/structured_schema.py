"""Moonshot MFJS projection for Factory structured output.

This module only reshapes a JSON Schema so kimi-k3 accepts
`response_format.json_schema.schema`. The default Factory generate path now
asks for AgentSemanticPlanV1; the AgentBlueprint projection remains a
compatibility bridge, not the provider-facing contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

_STRIP_KEYWORDS = {
    "$comment",
    "$schema",
    "allOf",
    "else",
    "format",
    "if",
    "minProperties",
    "propertyNames",
    "then",
    "uniqueItems",
}


def project_moonshot_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Project a JSON Schema onto the Moonshot Flavored JSON Schema subset.

    Live 400 evidence against kimi-k3 with strict json_schema:

    - enum nodes must declare type
    - $ref to oneOf is rejected as unterminated recursion; anyOf is walked
    - const is not an MFJS keyword, so discriminators become typed enum
    """

    projected = _project_node(deepcopy(dict(schema)))
    if not isinstance(projected, dict):
        raise TypeError("Moonshot schema projection must return an object")
    return _inline_internal_refs(projected)


def _project_node(node: Any) -> Any:
    if isinstance(node, dict):
        const = node.get("const")
        projected: dict[str, Any] = {}
        for key, value in node.items():
            if key in _STRIP_KEYWORDS or key == "const":
                continue
            if key == "oneOf":
                projected["anyOf"] = _project_node(value)
            else:
                projected[key] = _project_node(value)
        if const is not None:
            inferred = _json_type(const)
            if inferred is not None and "type" not in projected:
                projected["type"] = inferred
            projected.setdefault("enum", [const])
        if "enum" in projected and "type" not in projected:
            inferred = _infer_enum_type(projected["enum"])
            if inferred is not None:
                projected["type"] = inferred
        return projected
    if isinstance(node, list):
        return [_project_node(item) for item in node]
    return node


def _inline_internal_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Expand #/$defs refs so MFJS constrained decoding sees required fields."""

    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        return schema

    def expand(node: Any, stack: frozenset[str]) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/") and len(node) == 1:
                name = ref[len("#/$defs/") :]
                target = defs.get(name)
                if name not in stack and isinstance(target, dict):
                    return expand(deepcopy(target), stack | {name})
            return {
                key: expand(value, stack)
                for key, value in node.items()
                if key != "$defs"
            }
        if isinstance(node, list):
            return [expand(item, stack) for item in node]
        return node

    inlined = expand(schema, frozenset())
    if not isinstance(inlined, dict):
        raise TypeError("Moonshot schema inlining must return an object")
    inlined.pop("$defs", None)
    return inlined


def _json_type(value: Any) -> str | None:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return None


def _infer_enum_type(values: Any) -> str | None:
    if not isinstance(values, list) or not values:
        return None
    types = {_json_type(item) for item in values}
    if len(types) != 1:
        return None
    return next(iter(types))
