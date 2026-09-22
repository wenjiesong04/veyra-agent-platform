from __future__ import annotations

import pytest

from veyra_agent_platform.contracts.agent import AgentBlueprint
from veyra_agent_platform.local.factory.compiler import (
    BlueprintCompileError,
    agent_candidate_identity,
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


def test_compile_locks_exact_ready_project_custom_component_pin() -> None:
    reference = "01a0c9a5-e95a-7323-b81b-5069d9db2f1a@1.0.0"
    digest = "a" * 64
    payload = _blueprint()
    payload["nodes"] = [
        {"id": "start", "component_type": "Start"},
        {
            "id": "normalize",
            "component_type": "CustomComponent",
            "uses": reference,
        },
        {
            "id": "analyze",
            "component_type": "Agent",
            "model_ref": "model.primary",
            "system_prompt": "Prepare the normalized brief.",
        },
        {"id": "output", "component_type": "Output", "output_name": "brief"},
    ]
    payload["transitions"] = [
        {"from": "start", "port": "next", "to": "normalize"},
        {"from": "normalize", "port": "next", "to": "analyze"},
        {"from": "analyze", "port": "next", "to": "output"},
    ]
    payload["required_capabilities"] = {
        **payload["required_capabilities"],
        "component_types": ["Start", "CustomComponent", "Agent", "Output"],
    }
    component = {
        "reference": reference,
        "kind": "component",
        "component_class": "composite",
        "scope": "project",
        "binding_status": "current",
        "factory_selectable": True,
        "availability": "ready",
        "runtime_status": "supported",
        "content_hash": digest,
        "bound_content_hash": digest,
        "required_permissions": {
            "network_hosts": [],
            "tools": [],
            "filesystem_read_roots": [],
            "filesystem_write_roots": [],
            "shell_workspace_only": False,
        },
        "spec": {},
    }

    source, plan, availability = compile_blueprint(
        AgentBlueprint.from_dict(payload),
        ResourceCatalog(),
        project_resources=[component],
    )

    assert source.lock[reference] == digest
    assert any(node.component_type.value == "CustomComponent" for node in source.nodes)
    assert {item["reference"] for item in plan} >= {reference}
    assert (
        next(item for item in plan if item["reference"] == reference)["availability"]
        == "ready"
    )
    assert availability == "requires_configuration"


def test_compile_rejects_stale_project_custom_component_pin() -> None:
    reference = "01a0c9a5-e95a-7323-b81b-5069d9db2f1a@1.0.0"
    digest = "a" * 64
    payload = _blueprint()
    payload["nodes"] = [
        {"id": "start", "component_type": "Start"},
        {"id": "normalize", "component_type": "CustomComponent", "uses": reference},
        {"id": "output", "component_type": "Output", "output_name": "brief"},
    ]
    payload["transitions"] = [
        {"from": "start", "port": "next", "to": "normalize"},
        {"from": "normalize", "port": "next", "to": "output"},
    ]
    payload["required_capabilities"] = {
        **payload["required_capabilities"],
        "component_types": ["Start", "CustomComponent", "Output"],
    }
    stale_component = {
        "reference": reference,
        "kind": "component",
        "component_class": "composite",
        "scope": "project",
        "binding_status": "stale",
        "factory_selectable": True,
        "availability": "ready",
        "runtime_status": "supported",
        "content_hash": digest,
        "bound_content_hash": "b" * 64,
    }

    with pytest.raises(BlueprintCompileError, match="current, ready Project pin"):
        compile_blueprint(
            AgentBlueprint.from_dict(payload),
            ResourceCatalog(),
            project_resources=[stale_component],
        )


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

    assert availability == "ready"
    assert source.permissions.tools == ("veyra.tool.github.read",)
    assert source.permissions.network_hosts == ("api.github.com",)
    assert source.secret_refs == ("github.main",)
    assert "veyra.tool.github.read@1.0.0" in source.lock
    assert any(item["reference"] == "veyra.tool.github.read@1.0.0" for item in plan)


def test_compile_uses_suggested_name_instead_of_generated_agent() -> None:
    source, _, _ = compile_blueprint(
        AgentBlueprint.from_dict(_blueprint()),
        ResourceCatalog(),
        name="礼物包装顾问",
    )
    assert source.name == "礼物包装顾问"
    assert source.slug.startswith("agent-")
    assert source.slug != "generated-agent"


def test_agent_candidate_identity_keeps_latin_slug_and_hashes_cjk() -> None:
    name, slug = agent_candidate_identity("Gift Wrapping Advisor")
    assert name == "Gift Wrapping Advisor"
    assert slug == "gift-wrapping-advisor"
    display, hashed = agent_candidate_identity("礼物包装顾问")
    assert display == "礼物包装顾问"
    assert hashed.startswith("agent-")
    fallback_name, fallback_slug = agent_candidate_identity(None)
    assert fallback_name == "Generated Agent"
    assert fallback_slug == "generated-agent"
