"""Compile explicit orchestration into a Workflow proposal plus companion Agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.workflow import WorkflowSource
from veyra_agent_platform.local.resources import ResourceCatalog


@dataclass(frozen=True)
class WorkflowOrchestration:
    workflow: dict[str, Any]
    companions: tuple[AgentSource, ...]
    flow: tuple[str, ...]

    def workflow_preview(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "goal": self.workflow.get("description") or "",
            "nodes": list(self.workflow.get("nodes") or []),
            "transitions": list(self.workflow.get("transitions") or []),
            "data_edges": list(self.workflow.get("data_edges") or []),
            "companion_names": [item.name for item in self.companions],
            "flow": list(self.flow),
            "execution_kind": "workflow",
        }


def compile_workflow_orchestration(
    requirement: str,
    catalog: ResourceCatalog,
    *,
    workflow_id: str | None = None,
) -> WorkflowOrchestration:
    """Build a typed Workflow from TaskStructure. Companion Agents stay loops."""

    from veyra_agent_platform.local.builder.generate_product import (
        generate_builder_product,
    )

    product = generate_builder_product(requirement, catalog)
    if product.orchestration is None:
        raise ValueError("workflow compilation produced no orchestration")
    if workflow_id:
        product.orchestration.workflow["workflow_id"] = workflow_id
    return product.orchestration


def materialize_workflow_source(
    orchestration: WorkflowOrchestration,
    version_ids: dict[str, str],
    *,
    source_hashes: dict[str, str],
) -> WorkflowSource:
    """Pin AgentCall nodes to immutable versions. Draft Agents are rejected."""

    payload = dict(orchestration.workflow)
    lock: dict[str, str] = dict(payload.get("lock") or {})
    nodes = []
    for node in payload["nodes"]:
        if node.get("component_type") != "AgentCall":
            nodes.append(node)
            continue
        agent_id = str(node["agent_ref"]).split("@", 1)[0]
        version_id = version_ids.get(agent_id)
        digest = source_hashes.get(agent_id)
        if not version_id or not digest:
            raise ValueError("Workflow AgentCall requires a committed Agent version")
        ref = f"{agent_id}@{version_id}"
        nodes.append({**node, "agent_ref": ref})
        lock[ref] = digest
    payload["nodes"] = nodes
    payload["lock"] = lock
    payload.pop("companion_agent_ids", None)
    return WorkflowSource.from_dict(payload)
