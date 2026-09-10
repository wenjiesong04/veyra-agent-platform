from __future__ import annotations

import pytest

from veyra_agent_platform.contracts.agent import AgentBlueprint
from veyra_agent_platform.local.factory.compiler import (
    BlueprintCompileError,
    compile_blueprint,
)
from veyra_agent_platform.local.resources import ResourceCatalog


def _blueprint(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "goal": "Prepare a research brief from a question.",
        "inputs": {"question": "string"},
        "outputs": {"brief": "string"},
        "nodes": [
            {"id": "start", "component_type": "Start"},
            {
                "id": "analyze",
                "component_type": "Agent",
                "model_ref": "model.primary",
                "system_prompt": "Write a bounded research brief.",
            },
            {"id": "output", "component_type": "Output", "output_name": "brief"},
        ],
        "transitions": [
            {"from": "start", "port": "next", "to": "analyze"},
            {"from": "analyze", "port": "next", "to": "output"},
        ],
        "required_capabilities": {
            "component_types": ["Start", "Agent", "Output"],
            "tool_refs": [],
            "skill_refs": ["veyra.skill.research-brief@1.0.0"],
            "policy_refs": ["veyra.policy.local-only@1.0.0"],
        },
        "requested_permissions": {"network_hosts": [], "tools": []},
        "verification": {"required": False, "checks": []},
        "ui_suggestions": {"positions": {}},
    }
    payload.update(overrides)
    return payload


def test_compile_derives_permissions_and_compiles_skills() -> None:
    source, plan, availability = compile_blueprint(
        AgentBlueprint.from_dict(_blueprint()), ResourceCatalog()
    )
    assert availability == "requires_configuration"
    assert source.permissions.tools == ()
    assert "Research Brief" in (source.nodes[1].system_prompt or "")
    assert source.skill_refs == ("veyra.skill.research-brief@1.0.0",)
    assert source.policy_refs == ("veyra.policy.local-only@1.0.0",)
    assert "veyra.skill.research-brief@1.0.0" in source.lock
    bindings = source.ui.get("bindings") or {}
    assert {
        (binding["kind"], binding["reference"]) for binding in bindings.values()
    } >= {
        ("skill", "veyra.skill.research-brief@1.0.0"),
        ("policy", "veyra.policy.local-only@1.0.0"),
    }
    assert {item["kind"] for item in plan} >= {"component", "skill", "policy"}


def test_compile_uses_goal_when_optional_description_is_blank() -> None:
    source, _, _ = compile_blueprint(
        AgentBlueprint.from_dict(_blueprint()), ResourceCatalog(), description=""
    )
    assert source.description == "Prepare a research brief from a question."


def test_compile_resolves_read_tool_and_derives_full_permission_id() -> None:
    payload = _blueprint()
    payload["nodes"] = [
        {"id": "start", "component_type": "Start"},
        {
            "id": "read",
            "component_type": "Tool",
            "uses": "veyra.tool.filesystem.read@1.0.0",
        },
        {
            "id": "analyze",
            "component_type": "Agent",
            "model_ref": "model.primary",
            "system_prompt": "Summarize the supplied file.",
        },
        {"id": "output", "component_type": "Output", "output_name": "brief"},
    ]
    payload["transitions"] = [
        {"from": "start", "port": "next", "to": "read"},
        {"from": "read", "port": "next", "to": "analyze"},
        {"from": "analyze", "port": "next", "to": "output"},
    ]
    payload["required_capabilities"] = {
        "component_types": ["Start", "Tool", "Agent", "Output"],
        "tool_refs": ["veyra.tool.filesystem.read@1.0.0"],
        "skill_refs": [],
        "policy_refs": [],
    }
    blueprint = AgentBlueprint.from_dict(payload)
    source, plan, availability = compile_blueprint(blueprint, ResourceCatalog())
    assert source.permissions.tools == ("veyra.tool.filesystem.read",)
    assert source.permissions.filesystem_read_roots == ("project",)
    assert "veyra.tool.filesystem.read@1.0.0" in source.lock
    assert availability == "requires_configuration"
    assert any(item["kind"] == "tool" for item in plan)


def test_compile_rejects_writes_without_approval() -> None:
    payload = _blueprint()
    payload["nodes"] = [
        {"id": "start", "component_type": "Start"},
        {
            "id": "write",
            "component_type": "Tool",
            "uses": "veyra.tool.filesystem.write@1.0.0",
        },
        {"id": "output", "component_type": "Output", "output_name": "brief"},
    ]
    payload["transitions"] = [
        {"from": "start", "port": "next", "to": "write"},
        {"from": "write", "port": "next", "to": "output"},
    ]
    payload["required_capabilities"] = {
        "component_types": ["Start", "Tool", "Output"],
        "tool_refs": ["veyra.tool.filesystem.write@1.0.0"],
        "skill_refs": [],
        "policy_refs": [],
    }
    with pytest.raises(BlueprintCompileError, match="HumanApproval"):
        compile_blueprint(AgentBlueprint.from_dict(payload), ResourceCatalog())


def test_compile_accepts_supported_github_tool() -> None:
    payload = _blueprint()
    payload["nodes"] = [
        {"id": "start", "component_type": "Start"},
        {
            "id": "read_github",
            "component_type": "Tool",
            "uses": "veyra.tool.github.read@1.0.0",
        },
        {"id": "output", "component_type": "Output", "output_name": "brief"},
    ]
    payload["transitions"] = [
        {"from": "start", "port": "next", "to": "read_github"},
        {"from": "read_github", "port": "next", "to": "output"},
    ]
    payload["required_capabilities"] = {
        "component_types": ["Start", "Tool", "Output"],
        "tool_refs": ["veyra.tool.github.read@1.0.0"],
        "skill_refs": [],
        "policy_refs": [],
    }
    source, plan, availability = compile_blueprint(
        AgentBlueprint.from_dict(payload), ResourceCatalog()
    )

    assert availability == "requires_configuration"
    assert source.permissions.tools == ("veyra.tool.github.read",)
    assert source.permissions.network_hosts == ("api.github.com",)
    assert source.secret_refs == ("github.main",)
    assert "veyra.tool.github.read@1.0.0" in source.lock
    assert any(item["reference"] == "veyra.tool.github.read@1.0.0" for item in plan)
