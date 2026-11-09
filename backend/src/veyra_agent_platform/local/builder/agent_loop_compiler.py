"""Compile an AgentSpecification into a loop AgentSource.

The graph skeleton is Start → Model → Output so historical Studio and hashes
keep working. Runtime ignores that skeleton when execution_kind is loop.
Tools, knowledge, skills, and policies are capabilities, not DAG stages.

New create_agent generation must call ResourceResolver then compose_loop_agent.
This module keeps blueprint helpers and a convenience wrapper for tests and
workflow companions. It does not select resources via hardcoded capability maps.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.agent_spec import AgentSpecification
from veyra_agent_platform.contracts.common import thaw_json
from veyra_agent_platform.contracts.typed_io import typed_fields_to_wire
from veyra_agent_platform.local.builder.agent_composer import compose_loop_agent
from veyra_agent_platform.local.builder.capability_requirements import (
    derive_capability_requirements,
)
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.resources.resolver import ResourceResolver


def compile_loop_agent(
    specification: AgentSpecification,
    catalog: ResourceCatalog,
    *,
    agent_id: str | None = None,
    requirement: str = "",
    project_resources: list[dict[str, Any]] | None = None,
    knowledge_inventory: list[dict[str, Any]] | None = None,
) -> AgentSource:
    """Legacy convenience: resolve then compose.

    Factory create_agent must not rely on this wrapper to hide selection.
    """

    requirements = derive_capability_requirements(specification, requirement)
    plan = ResourceResolver(catalog).resolve(
        specification,
        requirements,
        project_resources=project_resources or [],
        knowledge_inventory=knowledge_inventory or [],
        requirement_text=requirement,
    )
    return compose_loop_agent(
        specification, plan, requirement=requirement, agent_id=agent_id
    )


def loop_agent_blueprint(source: AgentSource) -> dict[str, Any]:
    """Factory review payload: capability graph, not a multi-stage DAG."""

    tool_refs = [
        str(entry.get("reference"))
        for entry in (source.ui.get("bindings") or {}).values()
        if isinstance(entry, Mapping) and entry.get("kind") in {"tool", "mcp_tool"}
    ]
    return {
        "schema_version": "1.0",
        "goal": source.description,
        "inputs": typed_fields_to_wire(source.inputs),
        "outputs": typed_fields_to_wire(source.outputs),
        "nodes": [node.to_dict() for node in source.nodes],
        "transitions": [item.to_dict() for item in source.transitions],
        "required_capabilities": {
            "component_types": ["Start", "Model", "Output"],
            "tool_refs": tool_refs,
            "skill_refs": list(source.skill_refs),
            "policy_refs": list(source.policy_refs),
        },
        "requested_permissions": source.permissions.to_dict(),
        "verification": source.verification.to_dict(),
        "ui_suggestions": thaw_json(source.ui),
        "execution_kind": source.execution_kind,
        "instructions": source.instructions,
        "max_turns": source.max_turns,
    }


def loop_agent_blueprint_payload(source: AgentSource) -> dict[str, Any]:
    """AgentBlueprint-compatible subset for Factory session storage.

    Loop tools live on ui.bindings, not as DAG Tool nodes. AgentBlueprint still
    requires tool_refs to match Tool nodes, so the stored Blueprint keeps an
    empty tool_refs list and resource_plan reads bindings instead.
    """

    blueprint = loop_agent_blueprint(source)
    capabilities = dict(blueprint["required_capabilities"])
    capabilities["tool_refs"] = []
    blueprint["required_capabilities"] = capabilities
    allowed = {
        "schema_version",
        "goal",
        "inputs",
        "outputs",
        "nodes",
        "transitions",
        "required_capabilities",
        "requested_permissions",
        "verification",
        "ui_suggestions",
    }
    return {key: value for key, value in blueprint.items() if key in allowed}
