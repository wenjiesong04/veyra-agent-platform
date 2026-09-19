from __future__ import annotations

from veyra_agent_platform.local.factory.capability_profile import (
    derive_provider_capability_profile,
    structured_response_format,
)
from veyra_agent_platform.local.factory.config import FactorySettings


def test_moonshot_china_host_declares_mfjs_json_schema() -> None:
    profile = derive_provider_capability_profile(FactorySettings())
    assert profile.to_dict() == {
        "schema_version": "1.0",
        "provider_family": "moonshot",
        "structured_output": "json_schema",
        "schema_flavor": "moonshot_mfjs",
        "strict_json_schema": True,
        "json_object_fallback": True,
        "reasoning_effort": True,
        "source": "host_defaults",
        "probed": False,
    }
    fmt = structured_response_format(
        profile, name="agent_semantic_plan", schema={"type": "object"}
    )
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True


def test_moonshot_international_host_is_still_moonshot() -> None:
    profile = derive_provider_capability_profile(
        FactorySettings(model_base_url="https://api.moonshot.ai/v1")
    )
    assert profile.provider_family == "moonshot"
    assert profile.schema_flavor == "moonshot_mfjs"


def test_unknown_openai_compatible_host_fails_closed_to_json_object() -> None:
    profile = derive_provider_capability_profile(
        FactorySettings(model_base_url="https://llm.example.test/v1")
    )
    assert profile.provider_family == "openai_compatible"
    assert profile.structured_output == "json_object"
    assert profile.schema_flavor == "none"
    assert profile.json_object_fallback is False
    assert profile.reasoning_effort is False
    assert profile.probed is False
    assert structured_response_format(
        profile, name="agent_semantic_plan", schema={"type": "object"}
    ) == {"type": "json_object"}


def test_lookalike_host_is_not_treated_as_moonshot() -> None:
    profile = derive_provider_capability_profile(
        FactorySettings(model_base_url="https://api.moonshot.example/v1")
    )
    assert profile.provider_family == "openai_compatible"
