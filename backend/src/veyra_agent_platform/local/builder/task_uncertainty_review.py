"""Closed review of unresolved model assessments without editing the task plan."""

from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from veyra_agent_platform.contracts.common import ContractValidationError


def task_uncertainty_review_schema(count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["resolved"],
        "properties": {
            "resolved": {
                "type": "array",
                "maxItems": count,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["index", "reason"],
                    "properties": {
                        "index": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": max(0, count - 1),
                        },
                        "reason": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 400,
                        },
                    },
                },
            }
        },
    }


def resolved_uncertainty_indices(value: dict[str, Any], count: int) -> frozenset[int]:
    if not Draft202012Validator(task_uncertainty_review_schema(count)).is_valid(value):
        raise ContractValidationError("Task uncertainty review has an invalid contract")
    resolved: set[int] = set()
    for item in value["resolved"]:
        index = item["index"]
        if (
            type(index) is not int
            or not 0 <= index < count
            or index in resolved
            or not item["reason"].strip()
        ):
            raise ContractValidationError(
                "Task uncertainty review requires unique valid indices and reasons"
            )
        resolved.add(index)
    return frozenset(resolved)
