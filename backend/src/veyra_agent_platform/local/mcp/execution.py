"""Validate and receipt one authorized MCP call without exposing payload errors."""

from __future__ import annotations

import json
from typing import Any

from veyra_agent_platform.contracts.canonical import sha256_digest

from .schema import McpSchemaError, require_contract, validate_value
from .service import McpError, McpService

MAX_RESULT_BYTES = 1_000_000


class McpExecutionError(ValueError):
    def __init__(self, code: str, receipt: dict[str, Any]) -> None:
        super().__init__("MCP call failed validation or transport checks")
        self.code = code
        self.receipt = {**receipt, "outcome": "failed", "code": code}


def execute_call(
    service: McpService,
    spec: dict[str, Any],
    arguments: dict[str, Any],
    receipt: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Arguments are the Tool's mapped inputs, never implicitly dropped fields."""
    evidence = {
        **receipt,
        "input_digest": sha256_digest(arguments),
        "output_digest": None,
        "schema_contract_hash": spec.get("schema_contract_hash"),
        "schema_validation": {"input": "not_checked", "output": "not_checked"},
    }
    validation = evidence["schema_validation"]
    try:
        input_schema, output_schema = require_contract(spec)
        validation["input"] = "failed"
        validate_value(input_schema, arguments, code="mcp_input_schema_invalid")
        validation["input"] = "passed"
        server_id, tool_name = spec.get("mcp_server_id"), spec.get("mcp_tool_name")
        if not isinstance(server_id, str) or not isinstance(tool_name, str):
            raise McpSchemaError("mcp_descriptor_invalid")
        result = service.call(server_id, tool_name, arguments)
        output = {"result": result}
        encoded = json.dumps(output, allow_nan=False).encode("utf-8")
        evidence["output_digest"] = sha256_digest(output)
        evidence["byte_length"] = len(encoded)
        if len(encoded) > MAX_RESULT_BYTES:
            raise McpSchemaError("tool_output_too_large")
        if not isinstance(result, dict) or not isinstance(
            result.get("isError", False), bool
        ):
            raise McpSchemaError("mcp_result_invalid")
        if result.get("isError"):
            raise McpSchemaError("mcp_tool_failed")
        if output_schema is not None:
            validation["output"] = "failed"
            validate_value(
                output_schema,
                result.get("structuredContent"),
                code="mcp_output_schema_invalid",
            )
            validation["output"] = "passed"
        else:
            validation["output"] = "not_declared"
        return output, {**evidence, "outcome": "succeeded"}
    except (McpSchemaError, McpError) as exc:
        raise McpExecutionError(exc.code, evidence) from None
    except (ValueError, TypeError, RecursionError):
        raise McpExecutionError("mcp_result_invalid", evidence) from None
