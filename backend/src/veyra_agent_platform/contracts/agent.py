"""Strict, portable Project and Agent definition contracts.

The models deliberately use only immutable standard-library values. Parsing is
fail-closed: a new field is rejected until this contract explicitly owns it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from .canonical import behavior_hash, lock_hash, source_hash
from .common import (
    SCHEMA_VERSION,
    ContractValidationError,
    require_keys,
    require_list,
    require_mapping,
    require_schema_version,
    require_string,
    require_uuid7,
)

_SLUG = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_NODE_ID = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_REFERENCE = re.compile(r"^[a-z][a-z0-9_.-]*@[0-9]+\.[0-9]+\.[0-9]+$")
_HOST = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_SECRET_REF = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")


class ComponentType(StrEnum):
    START = "Start"
    AGENT = "Agent"
    TOOL = "Tool"
    CONDITION = "Condition"
    TRANSFORM = "Transform"
    HUMAN_APPROVAL = "HumanApproval"
    VERIFIER = "Verifier"
    OUTPUT = "Output"


class TransitionPort(StrEnum):
    NEXT = "next"
    TRUE = "true"
    FALSE = "false"
    APPROVED = "approved"
    REJECTED = "rejected"
    PASSED = "passed"
    FAILED = "failed"


_ALLOWED_PORTS: dict[ComponentType, frozenset[TransitionPort]] = {
    ComponentType.START: frozenset({TransitionPort.NEXT}),
    ComponentType.AGENT: frozenset({TransitionPort.NEXT}),
    ComponentType.TOOL: frozenset({TransitionPort.NEXT}),
    ComponentType.CONDITION: frozenset({TransitionPort.TRUE, TransitionPort.FALSE}),
    ComponentType.TRANSFORM: frozenset({TransitionPort.NEXT}),
    ComponentType.HUMAN_APPROVAL: frozenset({TransitionPort.APPROVED, TransitionPort.REJECTED}),
    ComponentType.VERIFIER: frozenset({TransitionPort.PASSED, TransitionPort.FAILED}),
    ComponentType.OUTPUT: frozenset(),
}


def _strict_str_list(value: Any, field: str, *, pattern: re.Pattern[str] | None = None) -> tuple[str, ...]:
    parsed = tuple(require_string(item, field, pattern=pattern) for item in require_list(value, field))
    if len(set(parsed)) != len(parsed):
        raise ContractValidationError(f"{field} must not contain duplicates")
    return parsed


@dataclass(frozen=True)
class PermissionContract:
    network_hosts: tuple[str, ...]
    tools: tuple[str, ...]
    filesystem_read_roots: tuple[str, ...] = ()
    filesystem_write_roots: tuple[str, ...] = ()
    shell_workspace_only: bool = False

    @classmethod
    def from_dict(cls, data: Any) -> "PermissionContract":
        item = require_mapping(data, "permissions")
        require_keys(
            item,
            allowed={"network_hosts", "tools", "filesystem_read_roots", "filesystem_write_roots", "shell_workspace_only"},
            required={"network_hosts", "tools"},
        )
        shell_workspace_only = item.get("shell_workspace_only", False)
        if not isinstance(shell_workspace_only, bool):
            raise ContractValidationError("permissions.shell_workspace_only must be boolean")
        return cls(
            network_hosts=_strict_str_list(item["network_hosts"], "permissions.network_hosts", pattern=_HOST),
            tools=_strict_str_list(item["tools"], "permissions.tools"),
            filesystem_read_roots=_strict_str_list(item.get("filesystem_read_roots", []), "permissions.filesystem_read_roots"),
            filesystem_write_roots=_strict_str_list(item.get("filesystem_write_roots", []), "permissions.filesystem_write_roots"),
            shell_workspace_only=shell_workspace_only,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "network_hosts": list(self.network_hosts),
            "tools": list(self.tools),
            "filesystem_read_roots": list(self.filesystem_read_roots),
            "filesystem_write_roots": list(self.filesystem_write_roots),
            "shell_workspace_only": self.shell_workspace_only,
        }


@dataclass(frozen=True)
class VerifierContract:
    required: bool
    checks: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: Any) -> "VerifierContract":
        item = require_mapping(data, "verification")
        require_keys(item, allowed={"required", "checks"}, required={"required", "checks"})
        if not isinstance(item["required"], bool):
            raise ContractValidationError("verification.required must be boolean")
        checks = _strict_str_list(item["checks"], "verification.checks")
        if item["required"] and not checks:
            raise ContractValidationError("required verification needs at least one check")
        return cls(required=item["required"], checks=checks)

    def to_dict(self) -> dict[str, Any]:
        return {"required": self.required, "checks": list(self.checks)}


@dataclass(frozen=True)
class FlowNode:
    id: str
    component_type: ComponentType
    model_ref: str | None = None
    system_prompt: str | None = None
    uses: str | None = None
    expression: str | None = None
    mapping: Mapping[str, str] | None = None
    prompt: str | None = None
    checks: tuple[str, ...] | None = None
    output_name: str | None = None

    @classmethod
    def from_dict(cls, data: Any) -> "FlowNode":
        item = require_mapping(data, "node")
        fields = {"id", "component_type", "model_ref", "system_prompt", "uses", "expression", "mapping", "prompt", "checks", "output_name"}
        require_keys(item, allowed=fields, required={"id", "component_type"})
        node_id = require_string(item["id"], "node.id", pattern=_NODE_ID)
        try:
            component_type = ComponentType(item["component_type"])
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("node.component_type is not a built-in V1 component") from exc
        values = {key: item.get(key) for key in fields - {"id", "component_type"}}
        allowed_by_type: dict[ComponentType, set[str]] = {
            ComponentType.START: set(),
            ComponentType.AGENT: {"model_ref", "system_prompt"},
            ComponentType.TOOL: {"uses"},
            ComponentType.CONDITION: {"expression"},
            ComponentType.TRANSFORM: {"mapping"},
            ComponentType.HUMAN_APPROVAL: {"prompt"},
            ComponentType.VERIFIER: {"checks"},
            ComponentType.OUTPUT: {"output_name"},
        }
        present = {key for key in values if key in item}
        forbidden = present - allowed_by_type[component_type]
        if forbidden:
            raise ContractValidationError(f"node {node_id} has fields not allowed for {component_type}: {', '.join(sorted(forbidden))}")
        required_by_type: dict[ComponentType, set[str]] = {
            ComponentType.START: set(), ComponentType.AGENT: {"model_ref", "system_prompt"},
            ComponentType.TOOL: {"uses"}, ComponentType.CONDITION: {"expression"},
            ComponentType.TRANSFORM: {"mapping"}, ComponentType.HUMAN_APPROVAL: {"prompt"},
            ComponentType.VERIFIER: {"checks"}, ComponentType.OUTPUT: {"output_name"},
        }
        missing = required_by_type[component_type] - present
        if missing:
            raise ContractValidationError(f"node {node_id} is missing: {', '.join(sorted(missing))}")
        mapping: Mapping[str, str] | None = None
        if "mapping" in present:
            raw_mapping = require_mapping(item["mapping"], "node.mapping")
            if not raw_mapping or not all(isinstance(key, str) and isinstance(value, str) for key, value in raw_mapping.items()):
                raise ContractValidationError("node.mapping must be a non-empty string map")
            mapping = dict(raw_mapping)
        checks = _strict_str_list(item["checks"], "node.checks") if "checks" in present else None
        if checks == ():
            raise ContractValidationError("node.checks must not be empty")
        return cls(
            id=node_id,
            component_type=component_type,
            model_ref=require_string(item["model_ref"], "node.model_ref") if "model_ref" in present else None,
            system_prompt=require_string(item["system_prompt"], "node.system_prompt") if "system_prompt" in present else None,
            uses=require_string(item["uses"], "node.uses", pattern=_REFERENCE) if "uses" in present else None,
            expression=require_string(item["expression"], "node.expression") if "expression" in present else None,
            mapping=mapping,
            prompt=require_string(item["prompt"], "node.prompt") if "prompt" in present else None,
            checks=checks,
            output_name=require_string(item["output_name"], "node.output_name") if "output_name" in present else None,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"id": self.id, "component_type": self.component_type.value}
        for key in ("model_ref", "system_prompt", "uses", "expression", "mapping", "prompt", "checks", "output_name"):
            value = getattr(self, key)
            if value is not None:
                result[key] = list(value) if key == "checks" else value
        return result


@dataclass(frozen=True)
class Transition:
    from_node: str
    port: TransitionPort
    to_node: str

    @classmethod
    def from_dict(cls, data: Any) -> "Transition":
        item = require_mapping(data, "transition")
        require_keys(item, allowed={"from", "port", "to"}, required={"from", "port", "to"})
        try:
            port = TransitionPort(item["port"])
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("transition.port is unknown") from exc
        return cls(
            from_node=require_string(item["from"], "transition.from", pattern=_NODE_ID),
            port=port,
            to_node=require_string(item["to"], "transition.to", pattern=_NODE_ID),
        )

    def to_dict(self) -> dict[str, str]:
        return {"from": self.from_node, "port": self.port.value, "to": self.to_node}


@dataclass(frozen=True)
class ProjectAgentDirectory:
    agent_id: str
    path: str

    @classmethod
    def from_dict(cls, data: Any) -> "ProjectAgentDirectory":
        item = require_mapping(data, "project agent")
        require_keys(item, allowed={"agent_id", "path"}, required={"agent_id", "path"})
        path = require_string(item["path"], "project agent.path")
        if path.startswith("/") or ".." in path.split("/") or not path.startswith("agents/"):
            raise ContractValidationError("project agent.path must be a relative agents/ directory")
        return cls(agent_id=require_string(item["agent_id"], "project agent.agent_id", pattern=_SLUG), path=path)

    def to_dict(self) -> dict[str, str]:
        return {"agent_id": self.agent_id, "path": self.path}


@dataclass(frozen=True)
class ProjectManifest:
    schema_version: str
    project_version: str
    project_id: str
    name: str
    agents: tuple[ProjectAgentDirectory, ...]

    @classmethod
    def from_dict(cls, data: Any) -> "ProjectManifest":
        item = require_mapping(data, "project manifest")
        require_keys(item, allowed={"schema_version", "project_version", "project_id", "name", "agents"}, required={"schema_version", "project_version", "project_id", "name", "agents"})
        require_schema_version(item)
        if item["project_version"] != "1":
            raise ContractValidationError("project_version must be exactly '1'")
        agents = tuple(ProjectAgentDirectory.from_dict(value) for value in require_list(item["agents"], "agents"))
        if not agents or len({agent.agent_id for agent in agents}) != len(agents) or len({agent.path for agent in agents}) != len(agents):
            raise ContractValidationError("project agents must be non-empty with unique IDs and paths")
        return cls(SCHEMA_VERSION, "1", require_uuid7(item["project_id"], "project_id"), require_string(item["name"], "name"), agents)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "project_version": self.project_version, "project_id": self.project_id, "name": self.name, "agents": [agent.to_dict() for agent in self.agents]}


@dataclass(frozen=True)
class AgentBlueprint:
    schema_version: str
    goal: str
    inputs: Mapping[str, str]
    outputs: Mapping[str, str]
    nodes: tuple[FlowNode, ...]
    transitions: tuple[Transition, ...]
    requested_permissions: PermissionContract
    verification: VerifierContract

    @classmethod
    def from_dict(cls, data: Any) -> "AgentBlueprint":
        item = require_mapping(data, "agent blueprint")
        required = {"schema_version", "goal", "inputs", "outputs", "nodes", "transitions", "requested_permissions", "verification"}
        require_keys(item, allowed=required, required=required)
        require_schema_version(item)
        return cls(
            schema_version=SCHEMA_VERSION,
            goal=require_string(item["goal"], "goal"),
            inputs=_typed_fields(item["inputs"], "inputs"),
            outputs=_typed_fields(item["outputs"], "outputs"),
            nodes=tuple(FlowNode.from_dict(value) for value in require_list(item["nodes"], "nodes")),
            transitions=tuple(Transition.from_dict(value) for value in require_list(item["transitions"], "transitions")),
            requested_permissions=PermissionContract.from_dict(item["requested_permissions"]),
            verification=VerifierContract.from_dict(item["verification"]),
        ).validated()

    def validated(self) -> "AgentBlueprint":
        _validate_graph(self.nodes, self.transitions, self.verification)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "goal": self.goal, "inputs": dict(self.inputs), "outputs": dict(self.outputs), "nodes": [node.to_dict() for node in self.nodes], "transitions": [transition.to_dict() for transition in self.transitions], "requested_permissions": self.requested_permissions.to_dict(), "verification": self.verification.to_dict()}


def _typed_fields(value: Any, field: str) -> Mapping[str, str]:
    item = require_mapping(value, field)
    if not item or not all(isinstance(key, str) and _SLUG.fullmatch(key) and isinstance(item_value, str) and item_value for key, item_value in item.items()):
        raise ContractValidationError(f"{field} must be a non-empty map of slug names to non-empty types")
    return dict(item)


def _ui_layout(value: Any) -> Mapping[str, Any]:
    item = require_mapping(value, "ui")
    require_keys(item, allowed={"positions"}, required={"positions"})
    positions = require_mapping(item["positions"], "ui.positions")
    parsed: dict[str, dict[str, int]] = {}
    for node_id, point in positions.items():
        require_string(node_id, "ui.positions node", pattern=_NODE_ID)
        coordinates = require_mapping(point, "ui.positions coordinate")
        require_keys(coordinates, allowed={"x", "y"}, required={"x", "y"})
        x, y = coordinates["x"], coordinates["y"]
        if any(isinstance(number, bool) or not isinstance(number, int) for number in (x, y)):
            raise ContractValidationError("ui positions must have integer x and y")
        parsed[node_id] = {"x": x, "y": y}
    return {"positions": parsed}


@dataclass(frozen=True)
class AgentSource:
    schema_version: str
    agentspec_version: str
    component_type: str
    id: str
    name: str
    description: str
    inputs: Mapping[str, str]
    outputs: Mapping[str, str]
    nodes: tuple[FlowNode, ...]
    transitions: tuple[Transition, ...]
    runtime_profile: str
    secret_refs: tuple[str, ...]
    permissions: PermissionContract
    verification: VerifierContract
    ui: Mapping[str, Any]
    lock: Mapping[str, str]

    @classmethod
    def from_dict(cls, data: Any) -> "AgentSource":
        item = require_mapping(data, "agent source")
        allowed = {"schema_version", "agentspec_version", "component_type", "id", "name", "description", "inputs", "outputs", "nodes", "transitions", "extensions", "ui", "lock"}
        require_keys(item, allowed=allowed, required=allowed)
        require_schema_version(item)
        if item["agentspec_version"] != "26.1" or item["component_type"] != "Flow":
            raise ContractValidationError("only AgentSpec 26.1 Flow sources are supported")
        extensions = require_mapping(item["extensions"], "extensions")
        require_keys(extensions, allowed={"veyra"}, required={"veyra"})
        veyra = require_mapping(extensions["veyra"], "extensions.veyra")
        require_keys(veyra, allowed={"runtime_profile", "secret_refs", "permissions", "verification"}, required={"runtime_profile", "secret_refs", "permissions", "verification"})
        ui = _ui_layout(item["ui"])
        lock = require_mapping(item["lock"], "lock")
        if not lock or not all(isinstance(key, str) and _REFERENCE.fullmatch(key) and isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for key, value in lock.items()):
            raise ContractValidationError("lock must map versioned dependency references to SHA-256 digests")
        source = cls(
            schema_version=SCHEMA_VERSION,
            agentspec_version="26.1",
            component_type="Flow",
            id=require_string(item["id"], "id", pattern=_SLUG),
            name=require_string(item["name"], "name"),
            description=require_string(item["description"], "description"),
            inputs=_typed_fields(item["inputs"], "inputs"), outputs=_typed_fields(item["outputs"], "outputs"),
            nodes=tuple(FlowNode.from_dict(value) for value in require_list(item["nodes"], "nodes")), transitions=tuple(Transition.from_dict(value) for value in require_list(item["transitions"], "transitions")),
            runtime_profile=require_string(veyra["runtime_profile"], "runtime_profile"),
            secret_refs=_strict_str_list(veyra["secret_refs"], "secret_refs", pattern=_SECRET_REF),
            permissions=PermissionContract.from_dict(veyra["permissions"]), verification=VerifierContract.from_dict(veyra["verification"]),
            ui=ui, lock=dict(lock),
        )
        _validate_graph(source.nodes, source.transitions, source.verification)
        tool_references = {node.uses.rsplit("@", 1)[0] for node in source.nodes if node.uses}
        if not tool_references.issubset(set(source.permissions.tools)):
            raise ContractValidationError("every Tool node must be included in permissions.tools")
        return source

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "agentspec_version": self.agentspec_version, "component_type": self.component_type, "id": self.id, "name": self.name, "description": self.description, "inputs": dict(self.inputs), "outputs": dict(self.outputs), "nodes": [node.to_dict() for node in self.nodes], "transitions": [transition.to_dict() for transition in self.transitions], "extensions": {"veyra": {"runtime_profile": self.runtime_profile, "secret_refs": list(self.secret_refs), "permissions": self.permissions.to_dict(), "verification": self.verification.to_dict()}}, "ui": dict(self.ui), "lock": dict(self.lock)}

    @property
    def source_hash(self) -> str:
        return source_hash(self.to_dict())

    @property
    def file_hash(self) -> str:
        """Compatibility name for the complete portable-source hash."""
        return self.source_hash

    @property
    def behavior_hash(self) -> str:
        return behavior_hash(self.to_dict())

    @property
    def lock_hash(self) -> str:
        return lock_hash(self.to_dict())


@dataclass(frozen=True)
class AgentDraft:
    schema_version: str
    draft_id: str
    project_id: str
    agent_id: str
    revision: int
    blueprint: AgentBlueprint

    @classmethod
    def from_dict(cls, data: Any) -> "AgentDraft":
        item = require_mapping(data, "agent draft")
        required = {"schema_version", "draft_id", "project_id", "agent_id", "revision", "blueprint"}
        require_keys(item, allowed=required, required=required)
        require_schema_version(item)
        revision = item["revision"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ContractValidationError("draft revision must be a non-negative integer")
        return cls(SCHEMA_VERSION, require_uuid7(item["draft_id"], "draft_id"), require_uuid7(item["project_id"], "project_id"), require_string(item["agent_id"], "agent_id", pattern=_SLUG), revision, AgentBlueprint.from_dict(item["blueprint"]))


def _validate_graph(nodes: tuple[FlowNode, ...], transitions: tuple[Transition, ...], verification: VerifierContract) -> None:
    if not nodes or len({node.id for node in nodes}) != len(nodes):
        raise ContractValidationError("nodes must be non-empty with unique IDs")
    types = {node.id: node.component_type for node in nodes}
    if sum(node.component_type is ComponentType.START for node in nodes) != 1:
        raise ContractValidationError("a Flow needs exactly one Start node")
    if not any(node.component_type is ComponentType.OUTPUT for node in nodes):
        raise ContractValidationError("a Flow needs at least one Output node")
    if verification.required and not any(node.component_type is ComponentType.VERIFIER for node in nodes):
        raise ContractValidationError("required verification needs a Verifier node")
    verifier_checks = {
        check
        for node in nodes
        if node.component_type is ComponentType.VERIFIER and node.checks is not None
        for check in node.checks
    }
    if not verifier_checks.issubset(set(verification.checks)):
        raise ContractValidationError("Verifier node checks must be declared by verification")
    seen_edges: set[tuple[str, TransitionPort, str]] = set()
    outgoing: dict[str, list[Transition]] = {node.id: [] for node in nodes}
    for transition in transitions:
        if transition.from_node not in types or transition.to_node not in types:
            raise ContractValidationError("transition references an unknown node")
        if transition.port not in _ALLOWED_PORTS[types[transition.from_node]]:
            raise ContractValidationError("transition port is not allowed by its source component")
        edge = (transition.from_node, transition.port, transition.to_node)
        if edge in seen_edges:
            raise ContractValidationError("duplicate transition")
        seen_edges.add(edge)
        outgoing[transition.from_node].append(transition)
    if any(node.component_type is not ComponentType.OUTPUT and not outgoing[node.id] for node in nodes):
        raise ContractValidationError("every non-Output node must have an outgoing transition")
    start = next(node.id for node in nodes if node.component_type is ComponentType.START)
    reached: set[str] = set()
    todo = [start]
    while todo:
        node_id = todo.pop()
        if node_id in reached:
            continue
        reached.add(node_id)
        todo.extend(edge.to_node for edge in outgoing[node_id])
    if set(types) != reached:
        raise ContractValidationError("every node must be reachable from Start")
