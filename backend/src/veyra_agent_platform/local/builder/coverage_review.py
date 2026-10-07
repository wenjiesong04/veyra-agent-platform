"""Closed semantic coverage review over a compiled, metadata-only candidate."""

from __future__ import annotations

from typing import Any

from veyra_agent_platform.contracts.common import ContractValidationError

COVERAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "gaps"],
    "properties": {
        "verdict": {"type": "string", "enum": ["covered", "incomplete"]},
        "gaps": {
            "type": "array",
            "maxItems": 24,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["requirement", "reason"],
                "properties": {
                    "requirement": {"type": "string", "maxLength": 400},
                    "reason": {"type": "string", "maxLength": 400},
                },
            },
        },
    },
}


def coverage_gaps(value: dict[str, Any]) -> tuple[str, ...]:
    if set(value) != {"verdict", "gaps"} or value["verdict"] not in {
        "covered",
        "incomplete",
    }:
        raise ContractValidationError("Coverage review has an invalid contract")
    gaps = value["gaps"]
    if not isinstance(gaps, list) or len(gaps) > 24:
        raise ContractValidationError("Coverage review must have bounded gaps")
    diagnostics: list[str] = []
    for gap in gaps:
        if not isinstance(gap, dict) or set(gap) != {"requirement", "reason"}:
            raise ContractValidationError("Coverage gap has an invalid contract")
        requirement, reason = gap["requirement"], gap["reason"]
        if (
            not isinstance(requirement, str)
            or not requirement.strip()
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            raise ContractValidationError(
                "Coverage gap requires a requirement and reason"
            )
        diagnostics.append(f"{requirement[:400]}: {reason[:400]}")
    if (value["verdict"] == "covered") != (not diagnostics):
        raise ContractValidationError("Coverage verdict contradicts its gaps")
    return tuple(diagnostics)
