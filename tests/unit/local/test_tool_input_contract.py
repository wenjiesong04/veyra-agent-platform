from __future__ import annotations

import json

import pytest

from veyra_agent_platform.local.mcp.schema import McpSchemaError, validate_value
from veyra_agent_platform.local.runtime.tool_input_contract import tool_input_issue


@pytest.mark.parametrize(
    ("arguments", "category", "location"),
    [
        ({}, "required", "/arguments/count"),
        ({"count": "private-value"}, "type", "/arguments/count"),
        ({"count": 21}, "maximum", "/arguments/count"),
        (
            {"count": 1, "private-key": "private-value"},
            "additionalProperties",
            "/arguments",
        ),
    ],
)
def test_native_json_input_rejections_have_safe_specific_evidence(
    arguments: dict, category: str, location: str
) -> None:
    resource = {
        "spec": {
            "input_json_schema": {
                "type": "object",
                "properties": {"count": {"type": "integer", "maximum": 20}},
                "required": ["count"],
                "additionalProperties": False,
            }
        }
    }
    issue = tool_input_issue(resource, arguments)
    assert issue is not None
    evidence = issue.to_dict()
    assert evidence["stage"] == "tool_input"
    assert evidence["violations"][0]["category"] == category
    assert evidence["violations"][0]["location"] == location
    assert "private" not in json.dumps(evidence)


def test_paths_do_not_expose_dynamic_or_secret_like_property_names() -> None:
    schema = {
        "type": "object",
        "properties": {
            "filters": {"type": "object", "additionalProperties": {"type": "number"}},
            "sk-private-schema-key": {"type": "number"},
        },
    }
    with pytest.raises(McpSchemaError) as caught:
        validate_value(
            schema,
            {
                "filters": {"private-instance-key": "private-value"},
                "sk-private-schema-key": "private-value",
            },
            code="input_invalid",
        )
    evidence = caught.value.diagnostics
    assert {item["location"] for item in evidence} == {
        "/arguments/filters/*",
        "/arguments/*",
    }
    assert "private" not in str(evidence) and str(caught.value) == "input_invalid"


def test_compact_constraints_preserve_optional_defaults_and_public_limit() -> None:
    resource = {
        "spec": {
            "input_schema": {"limit": "number", "query": "string"},
            "input_constraints": {"limit": {"minimum": 1, "maximum": 50}},
        }
    }
    assert tool_input_issue(resource, {"query": "query"}) is None
    issue = tool_input_issue(resource, {"query": "query", "limit": 51})
    assert issue is not None
    assert issue.violations == (
        {"category": "maximum", "location": "/arguments/limit", "limit": 50},
    )


def test_diagnostics_are_bounded_without_serializing_invalid_values() -> None:
    schema = {
        "type": "object",
        "properties": {f"field{i}": {"type": "integer"} for i in range(20)},
    }
    with pytest.raises(McpSchemaError) as caught:
        validate_value(
            schema, {f"field{i}": "private-value" for i in range(20)}, code="invalid"
        )
    assert len(caught.value.diagnostics) == 8
    assert "private" not in str(caught.value.diagnostics)


def test_each_missing_reviewed_parameter_is_reported() -> None:
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
        "required": ["query", "limit"],
    }
    with pytest.raises(McpSchemaError) as caught:
        validate_value(schema, {}, code="invalid")
    assert {item["location"] for item in caught.value.diagnostics} == {
        "/arguments/query",
        "/arguments/limit",
    }


def test_unknown_parameter_feedback_lists_reviewed_names_not_unknown_keys() -> None:
    issue = tool_input_issue(
        {
            "spec": {
                "input_schema": {
                    "entity_id": "string",
                    "entity_type": "string",
                    "payload": "object",
                    "status": "string",
                }
            }
        },
        {"private-extra": "private-value"},
    )
    assert issue is not None
    assert issue.violations[0]["allowed_parameters"] == [
        "/arguments/entity_id",
        "/arguments/entity_type",
        "/arguments/payload",
        "/arguments/status",
    ]
    assert "private" not in str(issue.to_dict())
