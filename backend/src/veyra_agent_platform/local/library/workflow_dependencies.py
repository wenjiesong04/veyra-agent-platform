"""Resolve Workflow calls against immutable, Project-owned Agent snapshots."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource, ComponentType
from veyra_agent_platform.contracts.resource import AgentVersionRef
from veyra_agent_platform.contracts.workflow import WorkflowSource
from veyra_agent_platform.local.projects.service import ProjectError
from veyra_agent_platform.local.storage.repositories import LocalRepository


@dataclass(frozen=True)
class ResolvedAgentCall:
    agent_id: str
    version_id: str
    source: AgentSource
    source_hash: str


def resolve_workflow_calls(
    repository: LocalRepository,
    project_id: str,
    source: WorkflowSource,
    *,
    connection: Any = None,
) -> dict[str, ResolvedAgentCall]:
    """Never resolve a call from the current draft or an implicit latest version."""
    resolved: dict[str, ResolvedAgentCall] = {}
    for node in source.nodes:
        if node.component_type is not ComponentType.AGENT_CALL:
            continue
        reference = AgentVersionRef.from_string(node.agent_ref)
        agent = repository.agent(reference.agent_id)
        if agent is None or agent["project_id"] != project_id:
            raise ProjectError(
                f"AgentCall {node.id} must reference an Agent in this Project",
                code="workflow_agent_not_found",
            )
        version = (
            connection.execute(
                "SELECT * FROM agent_versions WHERE version_id = ?",
                (reference.version_id,),
            ).fetchone()
            if connection is not None
            else repository.version(reference.version_id)
        )
        if version is None or version["agent_id"] != reference.agent_id:
            raise ProjectError(
                f"AgentCall {node.id} requires a committed Agent version",
                code="workflow_version_not_found",
            )
        if source.lock.get(reference.as_ref()) != version["source_hash"]:
            raise ProjectError(
                f"AgentCall {node.id} dependency hash does not match its version",
                code="workflow_lock_mismatch",
            )
        child = AgentSource.from_dict(json.loads(version["source_json"]))
        if (
            child.agent_id != reference.agent_id
            or child.source_hash != version["source_hash"]
        ):
            raise ProjectError(
                f"AgentCall {node.id} version snapshot failed integrity validation",
                code="workflow_version_invalid",
            )
        if set(node.input_mapping or {}) != set(child.inputs):
            raise ProjectError(
                f"AgentCall {node.id} must map every declared Agent input",
                code="workflow_input_mapping_invalid",
            )
        if set(node.output_mapping or {}) != set(child.outputs):
            raise ProjectError(
                f"AgentCall {node.id} must map every declared Agent output",
                code="workflow_output_mapping_invalid",
            )
        targets = list((node.output_mapping or {}).values())
        if len(targets) != len(set(targets)):
            raise ProjectError(
                f"AgentCall {node.id} output destinations must be unique",
                code="workflow_output_mapping_invalid",
            )
        resolved[node.id] = ResolvedAgentCall(
            reference.agent_id, reference.version_id, child, version["source_hash"]
        )
    _validate_call_dataflow(source, resolved)
    return resolved


def _validate_call_dataflow(
    source: WorkflowSource, resolved: dict[str, ResolvedAgentCall]
) -> None:
    nodes = {node.id: node for node in source.nodes}
    parents: dict[str, set[str]] = {node: set() for node in nodes}
    children: dict[str, set[str]] = {node: set() for node in nodes}
    for edge in source.transitions:
        parents[edge.to_node].add(edge.from_node)
        children[edge.from_node].add(edge.to_node)
    pending = {node: len(ancestors) for node, ancestors in parents.items()}
    ready = deque(node for node, count in pending.items() if not count)
    available: dict[str, dict[str, str]] = {}
    while ready:
        node_id = ready.popleft()
        node = nodes[node_id]
        incoming = [available[parent] for parent in parents[node_id]]
        values = (
            dict(source.inputs)
            if not incoming
            else {
                key: value
                for key, value in incoming[0].items()
                if all(other.get(key) == value for other in incoming[1:])
            }
        )
        if node_id in resolved:
            child = resolved[node_id].source
            for parameter, variable in (node.input_mapping or {}).items():
                if values.get(variable) != child.inputs[parameter]:
                    raise ProjectError(
                        f"AgentCall {node_id} input {parameter} needs a prior "
                        f"{child.inputs[parameter]} variable: {variable}",
                        code="workflow_input_mapping_invalid",
                    )
            for output, variable in (node.output_mapping or {}).items():
                values[variable] = child.outputs[output]
        elif node.component_type is ComponentType.TRANSFORM:
            values.update({key: "string" for key in (node.mapping or {})})
        available[node_id] = values
        for child_id in children[node_id]:
            pending[child_id] -= 1
            if not pending[child_id]:
                ready.append(child_id)
