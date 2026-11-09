"""Opt-in, offline result validation for catalog-owned Tool contracts."""

from collections.abc import Mapping
from typing import Any

from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.local.mcp.schema import (
    McpSchemaError,
    prepare_contract,
    validate_value,
)


class ToolOutputContractError(ValueError):
    def __init__(self, code: str, verification: dict[str, str] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.verification = verification


def prepare_tool_output_contract(spec: Mapping[str, Any]) -> dict[str, Any] | None:
    """Legacy descriptive schemas remain unchanged; declared validation is strict."""
    enabled = spec.get("output_validation", False)
    if not isinstance(enabled, bool):
        raise ToolOutputContractError("tool_output_schema_invalid")
    if not enabled:
        return None
    schema = spec.get("output_json_schema")
    if not isinstance(schema, Mapping):
        raise ToolOutputContractError("tool_output_schema_invalid")
    prepared = prepare_contract({"type": "object"}, dict(schema))
    if prepared["schema_status"] != "supported":
        raise ToolOutputContractError("tool_output_schema_invalid")
    return dict(prepared["output_json_schema"])


def verify_tool_output_contract(
    schema: dict[str, Any] | None, output: Any
) -> dict[str, str] | None:
    if schema is None:
        return None
    verification = {
        "method": "json_schema",
        "schema_hash": sha256_digest(schema),
        "status": "passed",
    }
    try:
        validate_value(schema, output, code="tool_output_invalid")
    except McpSchemaError as exc:
        raise ToolOutputContractError(
            exc.code, {**verification, "status": "failed"}
        ) from None
    return verification
