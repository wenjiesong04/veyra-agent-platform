"""Pure compiler from a validated Factory draft to a portable Agent source."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from veyra_agent_platform.contracts.agent import AgentBlueprint, AgentSource
from veyra_agent_platform.contracts.typed_io import typed_fields_to_wire


@dataclass(frozen=True)
class AgentDefinition:
    """Validated definition plus its three canonical hashes."""

    source: AgentSource
    source_hash: str
    behavior_hash: str
    lock_hash: str


def compile_agent_definition(
    blueprint: AgentBlueprint,
    *,
    agent_id: str,
    slug: str,
    name: str,
    description: str,
    runtime_profile: str,
    secret_refs: list[str],
    lock: Mapping[str, str],
    skill_refs: list[str] | None = None,
    policy_refs: list[str] | None = None,
) -> AgentDefinition:
    """Compile only known typed structures; no code or permission expansion occurs."""
    resolved_skills = list(
        skill_refs
        if skill_refs is not None
        else blueprint.required_capabilities.skill_refs
    )
    resolved_policies = list(
        policy_refs
        if policy_refs is not None
        else blueprint.required_capabilities.policy_refs
    )
    ui = dict(blueprint.ui_suggestions)
    bindings = merge_catalog_bindings(
        existing=ui.get("bindings"),
        skill_refs=resolved_skills,
        policy_refs=resolved_policies,
        reserved_ids={node.id for node in blueprint.nodes},
    )
    if bindings:
        ui["bindings"] = bindings
    source = AgentSource.from_dict(
        {
            "schema_version": blueprint.schema_version,
            "agentspec_version": "26.1",
            "component_type": "Flow",
            "agent_id": agent_id,
            "slug": slug,
            "name": name,
            "description": description,
            "inputs": typed_fields_to_wire(blueprint.inputs),
            "outputs": typed_fields_to_wire(blueprint.outputs),
            "nodes": [node.to_dict() for node in blueprint.nodes],
            "transitions": [
                transition.to_dict() for transition in blueprint.transitions
            ],
            **(
                {"data_edges": [edge.to_dict() for edge in blueprint.data_edges]}
                if blueprint.data_edges
                else {}
            ),
            "extensions": {
                "veyra": {
                    "runtime_profile": runtime_profile,
                    "secret_refs": secret_refs,
                    "permissions": blueprint.requested_permissions.to_dict(),
                    "verification": blueprint.verification.to_dict(),
                    "skill_refs": resolved_skills,
                    "policy_refs": resolved_policies,
                }
            },
            "ui": ui,
            "lock": dict(lock),
        }
    )
    return AgentDefinition(
        source, source.source_hash, source.behavior_hash, source.lock_hash
    )


def merge_catalog_bindings(
    *,
    existing: Mapping[str, Any] | None,
    skill_refs: Sequence[str],
    policy_refs: Sequence[str] = (),
    reserved_ids: Iterable[str] = (),
) -> dict[str, dict[str, Any]]:
    """Place Skill/Policy refs on the canvas as bindings, not Flow nodes."""
    bindings = {
        key: dict(value) if isinstance(value, Mapping) else value
        for key, value in dict(existing or {}).items()
    }
    reserved = set(reserved_ids) | set(bindings)
    seen = {
        str(entry.get("reference"))
        for entry in bindings.values()
        if isinstance(entry, Mapping)
    }
    index = 0
    for kind, reference in (
        *(("skill", item) for item in skill_refs),
        *(("policy", item) for item in policy_refs),
    ):
        if reference in seen:
            continue
        while True:
            index += 1
            binding_id = f"bind_{kind}{index}"
            if binding_id not in reserved:
                break
        bindings[binding_id] = {
            "kind": kind,
            "reference": reference,
            "x": 720,
            "y": 40 + (len(bindings) * 90),
        }
        reserved.add(binding_id)
        seen.add(reference)
    return bindings
