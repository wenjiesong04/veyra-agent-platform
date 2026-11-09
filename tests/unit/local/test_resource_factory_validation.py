from __future__ import annotations

import pytest

from veyra_agent_platform.local.resources.factory_validation import (
    ResourceFactoryValidationError,
    validate_skill_draft,
    validate_tool_wrapper,
)
from veyra_agent_platform.local.resources.resource_factory import skill_instruction_for


def test_generated_skill_instruction_passes() -> None:
    instruction = skill_instruction_for("structured_comparison_method")
    result = validate_skill_draft(
        instruction=instruction,
        capabilities=["structured_comparison_method"],
        name="Structured Comparison Method",
        description="Factory Skill for structured comparison.",
    )
    assert result["passed"] is True
    assert result["kind"] == "skill"


def test_skill_missing_section_fails() -> None:
    with pytest.raises(ResourceFactoryValidationError) as caught:
        validate_skill_draft(
            instruction="Purpose\nDo the work.\n",
            capabilities=["structured_comparison_method"],
            name="Incomplete",
            description="Missing sections",
        )
    assert caught.value.code == "factory_validation_failed"


def test_skill_secret_value_rejected() -> None:
    instruction = skill_instruction_for("structured_comparison_method")
    with pytest.raises(ResourceFactoryValidationError):
        validate_skill_draft(
            instruction=instruction + "\nUse sk-abcdefghijklmnopqrstuvwxyz012345.",
            capabilities=["structured_comparison_method"],
            name="Leaked",
            description="Has a secret",
        )


def test_skill_code_claim_rejected() -> None:
    instruction = skill_instruction_for("structured_comparison_method").replace(
        "Produce the expected output structure.",
        "execute python on the host.",
    )
    with pytest.raises(ResourceFactoryValidationError):
        validate_skill_draft(
            instruction=instruction,
            capabilities=["structured_comparison_method"],
            name="Code claim",
            description="Claims execution",
        )


def test_http_wrapper_requires_frozen_boundary() -> None:
    result = validate_tool_wrapper(
        {
            "base_adapter": "veyra.runtime.http.request",
            "allowed_hosts": ["127.0.0.1"],
            "methods": ["GET"],
            "path_prefix": "/status",
            "input_schema": {"code": "string"},
            "output_schema": {"body": "string", "status": "integer"},
            "timeout_ms": 2000,
            "max_response_bytes": 4096,
        }
    )
    assert result["passed"] is True
    assert result["base_adapter"] == "veyra.runtime.http.request"


def test_unrestricted_http_inputs_rejected() -> None:
    with pytest.raises(ResourceFactoryValidationError) as caught:
        validate_tool_wrapper(
            {
                "base_adapter": "veyra.runtime.http.request",
                "allowed_hosts": ["127.0.0.1"],
                "methods": ["GET"],
                "path_prefix": "/status",
                "input_schema": {
                    "url": "string",
                    "method": "string",
                    "headers": "object",
                },
            }
        )
    assert caught.value.code == "factory_validation_failed"


def test_wildcard_host_validation_rejected() -> None:
    with pytest.raises(ResourceFactoryValidationError) as caught:
        validate_tool_wrapper(
            {
                "base_adapter": "veyra.runtime.http.request",
                "allowed_hosts": ["*"],
                "methods": ["GET"],
                "path_prefix": "/anything",
            }
        )
    assert "Wildcard" in str(caught.value)


def test_open_route_rejected() -> None:
    with pytest.raises(ResourceFactoryValidationError):
        validate_tool_wrapper(
            {
                "base_adapter": "veyra.runtime.http.request",
                "allowed_hosts": ["127.0.0.1"],
                "methods": ["GET"],
                "path_prefix": "/",
            }
        )


def test_unknown_adapter_rejected() -> None:
    with pytest.raises(ResourceFactoryValidationError) as caught:
        validate_tool_wrapper({"base_adapter": "veyra.runtime.python.eval"})
    assert caught.value.code == "factory_unsupported"


def test_python_adapter_rejected() -> None:
    with pytest.raises(ResourceFactoryValidationError) as caught:
        validate_tool_wrapper({"adapter": "veyra.runtime.shell.exec"})
    assert caught.value.code == "factory_unsupported"


def test_filesystem_write_wrapper_rejected() -> None:
    with pytest.raises(ResourceFactoryValidationError) as caught:
        validate_tool_wrapper(
            {
                "base_adapter": "veyra.runtime.filesystem.write",
                "path_prefix": "docs",
            }
        )
    assert caught.value.code == "factory_unsupported"


def test_filesystem_read_wrapper_accepted() -> None:
    result = validate_tool_wrapper(
        {
            "base_adapter": "veyra.runtime.filesystem.search",
            "path_prefix": "docs",
            "input_schema": {"query": "string"},
            "output_schema": {"matches": "array"},
        }
    )
    assert result["passed"] is True


def test_secret_field_rejected() -> None:
    with pytest.raises(ResourceFactoryValidationError):
        validate_tool_wrapper(
            {
                "base_adapter": "veyra.runtime.http.request",
                "allowed_hosts": ["127.0.0.1"],
                "methods": ["GET"],
                "path_prefix": "/status",
                "api_key": "sk-abcdefghijklmnopqrstuvwxyz012345",
            }
        )
