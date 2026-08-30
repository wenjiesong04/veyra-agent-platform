"""Compile a validated Blueprint and catalog plan into AgentSource."""

from __future__ import annotations

from typing import Any

from veyra_agent_platform.contracts.agent import AgentBlueprint, AgentSource
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.resources import ResourceCatalog


def compile_blueprint(
    blueprint: AgentBlueprint,
    catalog: ResourceCatalog,
    *,
    name: str | None = None,
    description: str | None = None,
) -> AgentSource:
    """Create a new stable Agent identity from a validated Blueprint."""

    resources = catalog.resources()["resources"]
    by_name = {
        resource["name"]: resource
        for resource in resources
        if resource["kind"] == "component"
    }
    lock: dict[str, str] = {}
    for component_type in blueprint.required_capabilities.component_types:
        resource = by_name.get(component_type.value)
        if resource is None:
            raise ValueError(
                f"component resource is not registered: {component_type.value}"
            )
        lock[resource["reference"]] = resource["content_hash"]
    for tool_ref in blueprint.required_capabilities.tool_refs:
        resource_id, version = tool_ref.rsplit("@", 1)
        resource = catalog.detail(resource_id, version)
        if resource["kind"] not in {"tool", "mcp_tool"}:
            raise ValueError(f"resource is not executable: {tool_ref}")
        lock[resource["reference"]] = resource["content_hash"]
    runtime_reference = "veyra.runtime.profile@1.0.0"
    lock[runtime_reference] = sha256_digest(
        {"runtime_profile": "veyra-runtime-profile/1"}
    )
    description_text = (description or blueprint.goal).strip() or blueprint.goal
    source = {
        "schema_version": "1.0",
        "agentspec_version": "26.1",
        "component_type": "Flow",
        "agent_id": new_uuid7(),
        "slug": "generated-agent",
        "name": (name or "Generated Agent").strip() or "Generated Agent",
        "description": description_text,
        "inputs": dict(blueprint.inputs),
        "outputs": dict(blueprint.outputs),
        "nodes": [node.to_dict() for node in blueprint.nodes],
        "transitions": [transition.to_dict() for transition in blueprint.transitions],
        "extensions": {
            "veyra": {
                "runtime_profile": "veyra-runtime-profile/1",
                "secret_refs": [],
                "permissions": _derived_permissions(blueprint, catalog),
                "verification": blueprint.verification.to_dict(),
            }
        },
        "ui": {"positions": dict(blueprint.ui_suggestions["positions"])},
        "lock": lock,
    }
    return AgentSource.from_dict(source)


def _derived_permissions(
    blueprint: AgentBlueprint, catalog: ResourceCatalog
) -> dict[str, Any]:
    """Derive authority from selected catalog adapters, never from model output."""

    permissions: dict[str, Any] = {
        "network_hosts": set(),
        "tools": set(),
        "filesystem_read_roots": set(),
        "filesystem_write_roots": set(),
        "shell_workspace_only": False,
    }
    for tool_ref in blueprint.required_capabilities.tool_refs:
        resource_id, version = tool_ref.rsplit("@", 1)
        resource = catalog.detail(resource_id, version)
        required = resource["required_permissions"]
        permissions["network_hosts"].update(required.get("network_hosts", []))
        permissions["tools"].update(required.get("tools", []))
        permissions["filesystem_read_roots"].update(
            required.get("filesystem_read_roots", [])
        )
        permissions["filesystem_write_roots"].update(
            required.get("filesystem_write_roots", [])
        )
        permissions["shell_workspace_only"] = permissions[
            "shell_workspace_only"
        ] or bool(required.get("shell_workspace_only", False))
    return {
        "network_hosts": sorted(permissions["network_hosts"]),
        "tools": sorted(permissions["tools"]),
        "filesystem_read_roots": sorted(permissions["filesystem_read_roots"]),
        "filesystem_write_roots": sorted(permissions["filesystem_write_roots"]),
        "shell_workspace_only": permissions["shell_workspace_only"],
    }
