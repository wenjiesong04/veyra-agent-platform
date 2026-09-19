"""Resolve catalog resources, derive permissions, and compile a Draft source."""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from typing import Any

from veyra_agent_platform.contracts.agent import (
    AgentBlueprint,
    AgentSource,
    ComponentType,
    PermissionContract,
)
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.domain.agent_definition import compile_agent_definition
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceCatalogError

_RUNTIME_PROFILE = "veyra-runtime-profile/1"
_SLUG_NOISE = re.compile(r"[^a-z0-9]+")
_AGENT_SLUG = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_WRITE_TOOLS = {
    "veyra.tool.filesystem.write",
    "veyra.tool.shell.exec",
    "veyra.tool.github.write",
}
_NETWORK_TOOLS = {
    "veyra.tool.http.request",
    "veyra.tool.github.read",
    "veyra.tool.github.write",
    "veyra.tool.browser.navigate",
}
_BLOCKED_AVAILABILITY = {"unavailable", "disabled", "quarantined"}


class BlueprintCompileError(ValueError):
    """A bounded Factory compile failure with repair diagnostics."""

    def __init__(self, diagnostics: list[str]) -> None:
        super().__init__("; ".join(diagnostics))
        self.diagnostics = diagnostics


def agent_candidate_identity(name: str | None) -> tuple[str, str]:
    """Deterministic display name and slug; CJK names keep glyphs and hash the slug."""

    display = " ".join((name or "").split()).strip() or "Generated Agent"
    folded = _SLUG_NOISE.sub("-", display.casefold()).strip("-")[:63].strip("-")
    if folded and _AGENT_SLUG.fullmatch(folded) and folded not in {"agent", "workflow"}:
        return display, folded
    digest = hashlib.sha256(display.encode("utf-8")).hexdigest()[:8]
    return display, f"agent-{digest}"


def compile_blueprint(
    blueprint: AgentBlueprint,
    catalog: ResourceCatalog,
    *,
    name: str | None = None,
    slug: str | None = None,
    description: str | None = None,
) -> tuple[AgentSource, list[dict[str, Any]], str]:
    """Compile a validated Blueprint into AgentSource without executing it."""

    diagnostics: list[str] = []
    selected = _selected_resources(blueprint, catalog, diagnostics)
    if diagnostics:
        raise BlueprintCompileError(diagnostics)
    derived = _derived_permissions(selected)
    _apply_policies(blueprint, selected, derived, diagnostics)
    nodes = _compile_skills(blueprint, selected, diagnostics)
    if diagnostics:
        raise BlueprintCompileError(diagnostics)
    payload = blueprint.to_dict()
    payload["nodes"] = [node.to_dict() for node in nodes]
    payload["requested_permissions"] = derived.to_dict()
    compiled = AgentBlueprint.from_dict(payload)
    lock = {resource["reference"]: resource["content_hash"] for resource in selected}
    lock["veyra.runtime.profile@1.0.0"] = sha256_digest(
        {"runtime_profile": _RUNTIME_PROFILE}
    )
    display, candidate_slug = agent_candidate_identity(name)
    definition = compile_agent_definition(
        compiled,
        agent_id=new_uuid7(),
        slug=(slug or "").strip() or candidate_slug,
        name=display,
        description=(description or blueprint.goal).strip() or blueprint.goal,
        runtime_profile=_RUNTIME_PROFILE,
        secret_refs=sorted(
            {
                resource["spec"]["secret_ref"]
                for resource in selected
                if resource["spec"].get("secret_ref")
            }
        ),
        lock=lock,
    )
    plan = resource_plan(compiled, catalog)
    return definition.source, plan, run_availability(plan)


def resource_plan(
    blueprint: AgentBlueprint, catalog: ResourceCatalog
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    seen: set[str] = set()
    components = {
        resource["name"]: resource
        for resource in catalog.resources(kind="component")["resources"]
    }
    for component_type in blueprint.required_capabilities.component_types:
        resource = components.get(component_type.value)
        if resource:
            _append_plan(plan, seen, resource)
    grouped = (
        blueprint.required_capabilities.tool_refs,
        blueprint.required_capabilities.skill_refs,
        blueprint.required_capabilities.policy_refs,
    )
    for references in grouped:
        for reference in references:
            try:
                _append_plan(plan, seen, catalog.by_reference(reference))
            except ResourceCatalogError:
                continue
    return plan


def run_availability(plan: list[dict[str, Any]]) -> str:
    if not plan:
        return "unavailable"
    states = {item["availability"] for item in plan}
    statuses = {item["runtime_status"] for item in plan}
    if states & _BLOCKED_AVAILABILITY:
        return "unavailable"
    if "design_only" in states or "runtime_not_supported" in statuses:
        return "design_only"
    if "requires_configuration" in states or "runtime_not_configured" in statuses:
        return "requires_configuration"
    return "ready"


def _selected_resources(
    blueprint: AgentBlueprint,
    catalog: ResourceCatalog,
    diagnostics: list[str],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    components = {
        resource["name"]: resource
        for resource in catalog.resources(kind="component")["resources"]
    }
    for component_type in blueprint.required_capabilities.component_types:
        resource = components.get(component_type.value)
        if resource is None:
            diagnostics.append(f"component {component_type.value} is not registered")
            continue
        if not _factory_selectable(resource):
            diagnostics.append(f"component {component_type.value} is not selectable")
            continue
        selected.append(resource)
    expected = {
        "tool": {"tool", "mcp_tool"},
        "skill": {"skill"},
        "policy": {"policy"},
    }
    grouped = (
        ("tool", blueprint.required_capabilities.tool_refs),
        ("skill", blueprint.required_capabilities.skill_refs),
        ("policy", blueprint.required_capabilities.policy_refs),
    )
    for kind, references in grouped:
        for reference in references:
            try:
                resource = catalog.by_reference(reference)
            except ResourceCatalogError:
                diagnostics.append(f"{kind} {reference} is not registered")
                continue
            if resource["kind"] not in expected[kind]:
                diagnostics.append(f"{reference} is not a {kind} resource")
                continue
            if not _factory_selectable(resource):
                diagnostics.append(f"{kind} {reference} is not selectable")
                continue
            selected.append(resource)
    return selected


def _factory_selectable(resource: dict[str, Any]) -> bool:
    return bool(resource["factory_selectable"]) and resource["availability"] not in (
        _BLOCKED_AVAILABILITY
    )


def _derived_permissions(selected: list[dict[str, Any]]) -> PermissionContract:
    hosts: list[str] = []
    tools: list[str] = []
    reads: list[str] = []
    writes: list[str] = []
    shell = False
    for resource in selected:
        if resource["kind"] not in {"tool", "mcp_tool"}:
            continue
        permissions = resource["required_permissions"]
        hosts.extend(permissions["network_hosts"])
        tools.extend(permissions["tools"])
        reads.extend(permissions["filesystem_read_roots"])
        writes.extend(permissions["filesystem_write_roots"])
        shell = shell or bool(permissions["shell_workspace_only"])
    return PermissionContract.from_dict(
        {
            "network_hosts": list(dict.fromkeys(hosts)),
            "tools": list(dict.fromkeys(tools)),
            "filesystem_read_roots": list(dict.fromkeys(reads)),
            "filesystem_write_roots": list(dict.fromkeys(writes)),
            "shell_workspace_only": shell,
        }
    )


def _apply_policies(
    blueprint: AgentBlueprint,
    selected: list[dict[str, Any]],
    derived: PermissionContract,
    diagnostics: list[str],
) -> None:
    specs = [resource["spec"] for resource in selected if resource["kind"] == "policy"]
    tool_names = set(derived.tools)
    has_approval = any(
        node.component_type is ComponentType.HUMAN_APPROVAL for node in blueprint.nodes
    )
    if tool_names & _WRITE_TOOLS and not has_approval:
        diagnostics.append(
            "external writes require a HumanApproval node before compilation"
        )
    if any(spec.get("network") == "deny" for spec in specs) and (
        derived.network_hosts or tool_names & _NETWORK_TOOLS
    ):
        diagnostics.append("local-only policy forbids network tools or hosts")
    if (
        any(spec.get("verification") == "required" for spec in specs)
        and not blueprint.verification.required
    ):
        diagnostics.append("verification-required policy needs required checks")
    if (
        any(spec.get("external_write") == "approval_required" for spec in specs)
        and tool_names & _WRITE_TOOLS
        and not has_approval
    ):
        diagnostics.append("external-write policy requires a HumanApproval node")


def _compile_skills(
    blueprint: AgentBlueprint,
    selected: list[dict[str, Any]],
    diagnostics: list[str],
) -> tuple[Any, ...]:
    skills = [resource for resource in selected if resource["kind"] == "skill"]
    agent_nodes = [
        node
        for node in blueprint.nodes
        if node.component_type in {ComponentType.AGENT, ComponentType.MODEL}
    ]
    if skills and not agent_nodes:
        diagnostics.append("selected Skills require a Model node")
        return blueprint.nodes
    blocks = [
        f"[{resource['name']}] {resource['spec'].get('instruction', '').strip()}"
        for resource in skills
        if resource["spec"].get("instruction")
    ]
    suffix = "\n\n".join(block for block in blocks if block.strip())
    if not suffix:
        return blueprint.nodes
    compiled = []
    for node in blueprint.nodes:
        if (
            node.component_type in {ComponentType.AGENT, ComponentType.MODEL}
            and node.system_prompt
        ):
            compiled.append(
                replace(node, system_prompt=f"{node.system_prompt}\n\n{suffix}")
            )
        else:
            compiled.append(node)
    return tuple(compiled)


def _append_plan(
    plan: list[dict[str, Any]], seen: set[str], resource: dict[str, Any]
) -> None:
    reference = resource["reference"]
    if reference in seen:
        return
    seen.add(reference)
    plan.append(
        {
            "reference": reference,
            "kind": resource["kind"],
            "availability": resource["availability"],
            "runtime_status": resource["runtime_status"],
        }
    )
