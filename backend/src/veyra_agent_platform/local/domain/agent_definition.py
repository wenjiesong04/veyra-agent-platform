"""Pure compiler from a validated Factory draft to a portable Agent source."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from veyra_agent_platform.contracts.agent import AgentBlueprint, AgentSource
from veyra_agent_platform.contracts.common import ContractValidationError


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
) -> AgentDefinition:
    """Compile only known typed structures; no code or permission expansion occurs."""
    source = AgentSource.from_dict(
        {
            "schema_version": blueprint.schema_version,
            "agentspec_version": "26.1",
            "component_type": "Flow",
            "agent_id": agent_id,
            "slug": slug,
            "name": name,
            "description": description,
            "inputs": dict(blueprint.inputs),
            "outputs": dict(blueprint.outputs),
            "nodes": [node.to_dict() for node in blueprint.nodes],
            "transitions": [transition.to_dict() for transition in blueprint.transitions],
            "extensions": {"veyra": {"runtime_profile": runtime_profile, "secret_refs": secret_refs, "permissions": blueprint.requested_permissions.to_dict(), "verification": blueprint.verification.to_dict()}},
            "ui": blueprint.ui_suggestions,
            "lock": dict(lock),
        }
    )
    return AgentDefinition(source, source.source_hash, source.behavior_hash, source.lock_hash)
