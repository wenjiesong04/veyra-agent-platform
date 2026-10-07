from __future__ import annotations

import pytest

from veyra_agent_platform.contracts.capability import CapabilityRequirement
from veyra_agent_platform.local.resources.factory_strategy import (
    classify_factory_strategy,
)


def _need(capability: str) -> CapabilityRequirement:
    return CapabilityRequirement(capability=capability, required=True)


def test_generatable_skill_from_method_capability() -> None:
    strategy = classify_factory_strategy(_need("structured_comparison_method"))
    assert strategy.status == "generatable"
    assert strategy.generation_strategy == "skill_instruction"
    assert strategy.can_generate is True
    assert strategy.resource_kind == "skill"


def test_evaluation_method_is_not_false_positive_eval() -> None:
    strategy = classify_factory_strategy(_need("evaluation_method"))
    assert strategy.status == "generatable"
    assert strategy.generation_strategy == "skill_instruction"


@pytest.mark.parametrize(
    "capability", ["booking_agent", "invoice_reconciliation", "email_delivery"]
)
def test_unknown_capability_is_not_automatically_an_instruction_skill(
    capability: str,
) -> None:
    strategy = classify_factory_strategy(_need(capability))
    assert strategy.status == "unsupported"
    assert strategy.can_generate is False
    assert strategy.generation_strategy == "none"


@pytest.mark.parametrize(
    "effect",
    [{"side_effect": "write"}, {"network": "required"}, {"filesystem": "read"}],
)
def test_method_name_cannot_supply_an_effect_or_data_access(effect: dict) -> None:
    strategy = classify_factory_strategy(
        CapabilityRequirement(capability="reservation_method", **effect)
    )
    assert strategy.status == "unsupported"
    assert strategy.can_generate is False
    assert strategy.resource_kind is None


def test_http_lookup_needs_host_configuration() -> None:
    strategy = classify_factory_strategy(_need("mock_status_lookup"))
    assert strategy.status == "requires_user_configuration"
    assert strategy.generation_strategy == "http_tool_wrapper"
    assert strategy.can_generate is False
    assert "host" in strategy.requirements
    assert "endpoint" in strategy.requirements


def test_configured_http_wrapper_is_generatable() -> None:
    strategy = classify_factory_strategy(
        _need("mock_status_lookup"),
        wrapper={
            "base_adapter": "veyra.runtime.http.request",
            "allowed_hosts": ["127.0.0.1"],
            "path_prefix": "/status",
            "methods": ["GET"],
        },
    )
    assert strategy.status == "generatable"
    assert strategy.generation_strategy == "http_tool_wrapper"
    assert strategy.can_generate is True


def test_unsafe_shell_is_unsupported() -> None:
    strategy = classify_factory_strategy(_need("run_arbitrary_shell"))
    assert strategy.status == "unsupported"
    assert strategy.can_generate is False
    assert strategy.generation_strategy == "none"


def test_shell_adapter_wrapper_is_unsupported() -> None:
    strategy = classify_factory_strategy(
        _need("workspace_helper"),
        wrapper={"base_adapter": "veyra.runtime.shell.exec"},
    )
    assert strategy.status == "unsupported"


def test_image_generation_is_unsupported() -> None:
    strategy = classify_factory_strategy(_need("image_generation"))
    assert strategy.status == "unsupported"
    assert strategy.can_generate is False


def test_github_requires_external_integration() -> None:
    strategy = classify_factory_strategy(_need("github_issue_create"))
    assert strategy.status == "requires_external_integration"
    assert strategy.can_generate is False


def test_mcp_requires_external_integration() -> None:
    strategy = classify_factory_strategy(_need("mcp_custom_server"))
    assert strategy.status == "requires_external_integration"


def test_policy_generation_is_unsupported() -> None:
    strategy = classify_factory_strategy(_need("local_only"))
    assert strategy.status == "unsupported"


def test_wildcard_host_is_unsafe() -> None:
    strategy = classify_factory_strategy(
        _need("mock_status_lookup"),
        wrapper={
            "base_adapter": "veyra.runtime.http.request",
            "allowed_hosts": ["*"],
            "path_prefix": "/status",
        },
    )
    assert strategy.status == "unsupported"
