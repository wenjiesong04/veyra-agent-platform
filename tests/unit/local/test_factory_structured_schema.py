from __future__ import annotations

import json
from copy import deepcopy

from tests.integration.local.test_factory_routes import VALID_BLUEPRINT
from veyra_agent_platform.contracts.agent import AgentBlueprint
from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.local.factory.capability_profile import (
    derive_provider_capability_profile,
)
from veyra_agent_platform.local.factory.config import FactorySettings
from veyra_agent_platform.local.factory.service import (
    _blueprint_response_format,
    _generation_schema,
    _prepare_blueprint_payload,
)
from veyra_agent_platform.local.factory.structured_schema import (
    project_moonshot_json_schema,
)


def test_moonshot_projection_adds_enum_types_and_rewrites_unions() -> None:
    original = _generation_schema()
    snapshot = deepcopy(original)
    projected = project_moonshot_json_schema(original)
    dumped = json.dumps(projected)
    assert original == snapshot
    assert "$schema" not in projected
    assert "$defs" not in projected
    assert "$ref" not in dumped
    assert "oneOf" not in dumped
    assert "const" not in dumped
    assert "anyOf" in dumped
    items = projected["properties"]["required_capabilities"]["properties"][
        "component_types"
    ]["items"]
    assert items["type"] == "string"
    assert "Start" in items["enum"]
    assert "hyphens" in projected["properties"]["inputs"]["description"]
    verification = projected["properties"]["verification"]
    assert verification["required"] == ["required", "checks"]
    assert "checks" in verification["description"]
    start = projected["properties"]["nodes"]["items"]["anyOf"][0]
    assert start["properties"]["component_type"] == {
        "type": "string",
        "enum": ["Start"],
    }


def test_blueprint_compatibility_bridge_follows_moonshot_profile() -> None:
    fmt = _blueprint_response_format(
        derive_provider_capability_profile(FactorySettings())
    )
    dumped = json.dumps(fmt)
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "agent_blueprint"
    assert "oneOf" not in dumped
    assert '"const"' not in dumped
    openai = _blueprint_response_format(
        derive_provider_capability_profile(
            FactorySettings(model_base_url="https://llm.example.test/v1")
        )
    )
    assert openai == {"type": "json_object"}


def test_projected_output_still_requires_agent_blueprint_contract() -> None:
    AgentBlueprint.from_dict(VALID_BLUEPRINT)
    try:
        AgentBlueprint.from_dict({"schema_version": "1.0", "goal": "wrap a gift"})
    except (ContractValidationError, TypeError, ValueError):
        return
    raise AssertionError("schema-invalid Blueprint must be rejected")


def test_empty_verification_defaults_still_pass_contract() -> None:
    payload = json.loads(json.dumps(VALID_BLUEPRINT))
    payload["verification"] = {}
    prepared = _prepare_blueprint_payload(payload)
    AgentBlueprint.from_dict(prepared)


def test_prepare_does_not_invent_required_checks() -> None:
    payload = json.loads(json.dumps(VALID_BLUEPRINT))
    payload["verification"] = {"required": True}
    try:
        AgentBlueprint.from_dict(_prepare_blueprint_payload(payload))
    except ContractValidationError:
        return
    raise AssertionError("required verification without checks must be rejected")
