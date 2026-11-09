from __future__ import annotations

import pytest

from veyra_agent_platform.local.mcp.schema import (
    McpSchemaError,
    prepare_contract,
    require_contract,
    validate_value,
)


@pytest.mark.parametrize(
    "unsupported",
    [
        {"$ref": "https://invalid.example/schema"},
        {"type": "object", "properties": {"nested": {"$ref": "#/definitions/a"}}},
        {"type": "object", "allOf": []},
        {"type": "string", "pattern": ".*"},
        {"type": "object", "required": "not-an-array"},
    ],
)
def test_unsupported_contracts_cannot_be_executed(unsupported: object) -> None:
    spec = prepare_contract(unsupported)
    assert spec["schema_status"] == "unsupported"
    with pytest.raises(McpSchemaError):
        require_contract(spec)


def test_contract_hash_covers_nested_output_constraints_and_detects_tampering() -> None:
    spec = prepare_contract(
        {"type": "object"},
        {
            "type": "object",
            "additionalProperties": {"type": "integer"},
        },
    )
    _, output = require_contract(spec)
    validate_value(output, {"count": 1}, code="invalid")
    with pytest.raises(McpSchemaError):
        validate_value(output, {"count": True}, code="invalid")
    spec["output_json_schema"]["additionalProperties"] = False
    with pytest.raises(McpSchemaError):
        require_contract(spec)
