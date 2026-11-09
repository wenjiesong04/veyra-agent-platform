from __future__ import annotations

from dataclasses import replace

from veyra_agent_platform.local.factory.capability_profile import (
    PROBE_VERSION,
    classify_provider_error,
    derive_provider_capability_profile,
    generate_structured_output,
    structured_response_format,
)
from veyra_agent_platform.local.factory.config import FactorySettings


def test_moonshot_china_host_declares_mfjs_json_schema() -> None:
    profile = derive_provider_capability_profile(FactorySettings())
    payload = profile.to_dict()
    assert payload["provider_id"] == "moonshot"
    assert payload["provider_family"] == "moonshot"
    assert payload["model"] == "kimi-k3"
    assert payload["endpoint_kind"] == "chat_completions"
    assert payload["structured_output"] == "json_schema"
    assert payload["schema_flavor"] == "moonshot_mfjs"
    assert payload["schema_profile"] == "mfjs"
    assert payload["strict_json_schema"] is True
    assert payload["json_object_fallback"] is True
    assert payload["reasoning_effort"] is True
    assert payload["supports_reasoning_effort"] is True
    assert payload["strict_json_schema_support"] == "unknown"
    assert payload["json_object_support"] == "unknown"
    assert payload["source"] == "static_known"
    assert payload["status"] == "unknown"
    assert payload["probed"] is False
    assert payload["probe_version"] == PROBE_VERSION
    assert payload["checked_at"] is None
    assert "query" not in payload
    assert "api_key" not in payload
    assert payload["summary"]["provider"] == "Moonshot"
    assert payload["summary"]["structured_output"] == "Strict JSON Schema"
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
    assert profile.schema_profile == "mfjs"


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
    assert profile.status == "unknown"
    assert structured_response_format(
        profile, name="agent_semantic_plan", schema={"type": "object"}
    ) == {"type": "json_object"}


def test_lookalike_host_is_not_treated_as_moonshot() -> None:
    profile = derive_provider_capability_profile(
        FactorySettings(model_base_url="https://api.moonshot.example/v1")
    )
    assert profile.provider_family == "openai_compatible"


def test_query_string_is_not_part_of_fingerprint_or_profile() -> None:
    plain = derive_provider_capability_profile(
        FactorySettings(model_base_url="https://api.moonshot.cn/v1")
    )
    noisy = derive_provider_capability_profile(
        FactorySettings(model_base_url="https://api.moonshot.cn/v1?api_key=secret")
    )
    assert plain.base_url_fingerprint == noisy.base_url_fingerprint
    assert "secret" not in noisy.to_dict()["base_url_fingerprint"]
    assert "api.moonshot.cn" not in noisy.base_url_fingerprint


def test_model_and_endpoint_change_identity() -> None:
    moonshot = derive_provider_capability_profile(FactorySettings())
    other_model = derive_provider_capability_profile(
        FactorySettings(model_id="kimi-k2")
    )
    other_endpoint = derive_provider_capability_profile(
        FactorySettings(model_base_url="https://api.moonshot.ai/v1")
    )
    other_version = replace(moonshot, probe_version="old-probe")
    assert moonshot.identity_key != other_model.identity_key
    assert moonshot.identity_key != other_endpoint.identity_key
    assert moonshot.identity_key != other_version.identity_key


def test_known_probe_drives_generate_strategy() -> None:
    seed = derive_provider_capability_profile(FactorySettings())
    strict = replace(
        seed,
        status="known",
        source="probe",
        probed=True,
        strict_json_schema_support="supported",
        json_object_support="unknown",
    )
    json_object = replace(
        seed,
        status="known",
        source="fallback",
        probed=True,
        structured_output="json_object",
        strict_json_schema=False,
        json_object_fallback=False,
        strict_json_schema_support="unsupported",
        json_object_support="supported",
    )
    unsupported = replace(
        json_object,
        json_object_support="unsupported",
        source="probe",
    )
    assert generate_structured_output(strict) == "json_schema"
    assert generate_structured_output(json_object) == "json_object"
    assert generate_structured_output(unsupported) is None
    assert generate_structured_output(seed) == "json_schema"


def test_error_classification_does_not_treat_rate_limits_as_schema() -> None:
    assert classify_provider_error("factory_unauthorized") == "credentials"
    assert classify_provider_error("factory_forbidden") == "forbidden"
    assert classify_provider_error("factory_rate_limited") == "rate_limited"
    assert classify_provider_error("factory_provider_error") == "provider_failure"
    assert (
        classify_provider_error(
            "factory_request_invalid",
            details={
                "rejected_field": "response_format.json_schema",
                "bounded_message": "not a valid moonshot flavored json schema",
            },
        )
        == "schema_incompatible"
    )
    assert (
        classify_provider_error(
            "factory_request_invalid",
            details={
                "rejected_field": "response_format",
                "bounded_message": "response_format type is unsupported",
            },
        )
        == "response_format_unsupported"
    )
    assert (
        classify_provider_error(
            "factory_request_invalid",
            details={"http_status": "400", "bounded_message": "bad request"},
        )
        == "request_invalid"
    )
