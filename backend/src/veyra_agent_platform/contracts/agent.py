"""Strict, portable Project and Agent definition contracts.

The models deliberately use only immutable standard-library values. Parsing is
fail-closed: a new field is rejected until this contract explicitly owns it.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, cast

from .canonical import behavior_hash, lock_hash, source_hash
from .common import (
    NODE_ID_RE,
    SCHEMA_VERSION,
    ContractValidationError,
    freeze_json,
    require_keys,
    require_list,
    require_mapping,
    require_schema_version,
    require_string,
    require_uuid7,
    thaw_json,
)
from .resource import (
    AgentVersionRef,
    ProjectOwnedResource,
    ProjectResourceBinding,
    ResourceKind,
    ResourceRef,
    require_semver,
)
from .typed_io import TypedField, parse_typed_fields, typed_fields_to_wire

_SLUG = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_REFERENCE = re.compile(r"^[a-z][a-z0-9_.-]*@[0-9]+\.[0-9]+\.[0-9]+$")
_HOST = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_SECRET_REF = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
HARD_MAX_NODES = 128
HARD_MAX_TRANSITIONS = 256
HARD_MAX_CONCURRENT_RUNS = 16
HARD_MAX_RUN_SECONDS = 86_400
_BINDING_KINDS = frozenset({"skill", "policy", "template", "mcp_tool", "knowledge"})


class ComponentType(StrEnum):
    START = "Start"
    AGENT = "Agent"  # Legacy wire identity; the editor labels it Model.
    MODEL = "Model"
    TOOL = "Tool"
    CONDITION = "Condition"
    TRANSFORM = "Transform"
    HUMAN_APPROVAL = "HumanApproval"
    VERIFIER = "Verifier"
    OUTPUT = "Output"
    AGENT_CALL = "AgentCall"

    @classmethod
    def parse(cls, value: Any) -> ComponentType:
        """Preserve the node wire identity when reading historical sources."""
        return cls(value)


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
    ComponentType.MODEL: frozenset({TransitionPort.NEXT}),
    ComponentType.TOOL: frozenset({TransitionPort.NEXT}),
    ComponentType.CONDITION: frozenset({TransitionPort.TRUE, TransitionPort.FALSE}),
    ComponentType.TRANSFORM: frozenset({TransitionPort.NEXT}),
    ComponentType.HUMAN_APPROVAL: frozenset(
        {TransitionPort.APPROVED, TransitionPort.REJECTED}
    ),
    ComponentType.VERIFIER: frozenset({TransitionPort.PASSED, TransitionPort.FAILED}),
    ComponentType.OUTPUT: frozenset(),
    ComponentType.AGENT_CALL: frozenset({TransitionPort.NEXT}),
}

# Agent graphs are self-contained capability graphs. AgentCall is Workflow-only.
_AGENT_GRAPH_TYPES = frozenset(
    {
        ComponentType.START,
        ComponentType.AGENT,
        ComponentType.MODEL,
        ComponentType.TOOL,
        ComponentType.CONDITION,
        ComponentType.TRANSFORM,
        ComponentType.HUMAN_APPROVAL,
        ComponentType.VERIFIER,
        ComponentType.OUTPUT,
    }
)
_WORKFLOW_GRAPH_TYPES = frozenset(
    {
        ComponentType.START,
        ComponentType.AGENT_CALL,
        ComponentType.CONDITION,
        ComponentType.TRANSFORM,
        ComponentType.HUMAN_APPROVAL,
        ComponentType.VERIFIER,
        ComponentType.OUTPUT,
    }
)


def _strict_str_list(
    value: Any, field: str, *, pattern: re.Pattern[str] | None = None
) -> tuple[str, ...]:
    parsed = tuple(
        require_string(item, field, pattern=pattern)
        for item in require_list(value, field)
    )
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
    def from_dict(cls, data: Any) -> PermissionContract:
        item = require_mapping(data, "permissions")
        require_keys(
            item,
            allowed={
                "network_hosts",
                "tools",
                "filesystem_read_roots",
                "filesystem_write_roots",
                "shell_workspace_only",
            },
            required={"network_hosts", "tools"},
        )
        shell_workspace_only = item.get("shell_workspace_only", False)
        if not isinstance(shell_workspace_only, bool):
            raise ContractValidationError(
                "permissions.shell_workspace_only must be boolean"
            )
        return cls(
            network_hosts=_strict_str_list(
                item["network_hosts"], "permissions.network_hosts", pattern=_HOST
            ),
            tools=_strict_str_list(item["tools"], "permissions.tools"),
            filesystem_read_roots=_strict_str_list(
                item.get("filesystem_read_roots", []),
                "permissions.filesystem_read_roots",
            ),
            filesystem_write_roots=_strict_str_list(
                item.get("filesystem_write_roots", []),
                "permissions.filesystem_write_roots",
            ),
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
    def from_dict(cls, data: Any) -> VerifierContract:
        item = require_mapping(data, "verification")
        require_keys(
            item, allowed={"required", "checks"}, required={"required", "checks"}
        )
        if not isinstance(item["required"], bool):
            raise ContractValidationError("verification.required must be boolean")
        checks = _strict_str_list(item["checks"], "verification.checks")
        if item["required"] and not checks:
            raise ContractValidationError(
                "required verification needs at least one check"
            )
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
    network_hosts: tuple[str, ...] | None = None
    expression: str | None = None
    mapping: Mapping[str, str] | None = None
    prompt: str | None = None
    checks: tuple[str, ...] | None = None
    output_name: str | None = None
    agent_ref: str | None = None
    input_mapping: Mapping[str, str] | None = None
    output_mapping: Mapping[str, str] | None = None

    @classmethod
    def from_dict(cls, data: Any) -> FlowNode:
        item = require_mapping(data, "node")
        fields = {
            "id",
            "component_type",
            "model_ref",
            "system_prompt",
            "uses",
            "network_hosts",
            "expression",
            "mapping",
            "prompt",
            "checks",
            "output_name",
            "agent_ref",
            "input_mapping",
            "output_mapping",
        }
        require_keys(item, allowed=fields, required={"id", "component_type"})
        node_id = require_string(item["id"], "node.id", pattern=NODE_ID_RE)
        try:
            component_type = ComponentType.parse(item["component_type"])
        except (TypeError, ValueError) as exc:
            raise ContractValidationError(
                "node.component_type is not a built-in V1 component"
            ) from exc
        values = {key: item.get(key) for key in fields - {"id", "component_type"}}
        allowed_by_type: dict[ComponentType, set[str]] = {
            ComponentType.START: set(),
            ComponentType.AGENT: {"model_ref", "system_prompt"},
            ComponentType.MODEL: {"model_ref", "system_prompt"},
            ComponentType.TOOL: {
                "uses",
                "network_hosts",
                "input_mapping",
                "output_mapping",
            },
            ComponentType.CONDITION: {"expression"},
            ComponentType.TRANSFORM: {"mapping"},
            ComponentType.HUMAN_APPROVAL: {"prompt"},
            ComponentType.VERIFIER: {"checks"},
            ComponentType.OUTPUT: {"output_name"},
            ComponentType.AGENT_CALL: {"agent_ref", "input_mapping", "output_mapping"},
        }
        present = {key for key in values if key in item}
        forbidden = present - allowed_by_type[component_type]
        if forbidden:
            forbidden_fields = ", ".join(sorted(forbidden))
            raise ContractValidationError(
                f"node {node_id} has fields not allowed for "
                f"{component_type}: {forbidden_fields}"
            )
        required_by_type: dict[ComponentType, set[str]] = {
            ComponentType.START: set(),
            ComponentType.AGENT: {"model_ref", "system_prompt"},
            ComponentType.MODEL: {"model_ref", "system_prompt"},
            ComponentType.TOOL: {"uses"},
            ComponentType.CONDITION: {"expression"},
            ComponentType.TRANSFORM: {"mapping"},
            ComponentType.HUMAN_APPROVAL: {"prompt"},
            ComponentType.VERIFIER: {"checks"},
            ComponentType.OUTPUT: {"output_name"},
            ComponentType.AGENT_CALL: {"agent_ref", "input_mapping", "output_mapping"},
        }
        missing = required_by_type[component_type] - present
        if missing:
            raise ContractValidationError(
                f"node {node_id} is missing: {', '.join(sorted(missing))}"
            )
        mapping: Mapping[str, str] | None = None
        if "mapping" in present:
            raw_mapping = require_mapping(item["mapping"], "node.mapping")
            if not raw_mapping or not all(
                isinstance(key, str) and isinstance(value, str) and value
                for key, value in raw_mapping.items()
            ):
                raise ContractValidationError(
                    "node.mapping must be a non-empty string map"
                )
            mapping = freeze_json(dict(raw_mapping))
        checks = (
            _strict_str_list(item["checks"], "node.checks")
            if "checks" in present
            else None
        )
        if checks == ():
            raise ContractValidationError("node.checks must not be empty")
        return cls(
            id=node_id,
            component_type=component_type,
            model_ref=require_string(item["model_ref"], "node.model_ref")
            if "model_ref" in present
            else None,
            system_prompt=require_string(item["system_prompt"], "node.system_prompt")
            if "system_prompt" in present
            else None,
            uses=require_string(item["uses"], "node.uses", pattern=_REFERENCE)
            if "uses" in present
            else None,
            network_hosts=(
                _strict_str_list(
                    item["network_hosts"], "node.network_hosts", pattern=_HOST
                )
                if "network_hosts" in present
                else None
            ),
            expression=require_string(item["expression"], "node.expression")
            if "expression" in present
            else None,
            mapping=mapping,
            prompt=require_string(item["prompt"], "node.prompt")
            if "prompt" in present
            else None,
            checks=checks,
            output_name=require_string(item["output_name"], "node.output_name")
            if "output_name" in present
            else None,
            agent_ref=(
                AgentVersionRef.from_string(
                    item["agent_ref"], "node.agent_ref"
                ).as_ref()
                if "agent_ref" in present
                else None
            ),
            input_mapping=(
                _call_mapping(item["input_mapping"], "node.input_mapping")
                if "input_mapping" in present
                else None
            ),
            output_mapping=(
                _call_mapping(item["output_mapping"], "node.output_mapping")
                if "output_mapping" in present
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "component_type": self.component_type.value,
        }
        for key in (
            "model_ref",
            "system_prompt",
            "uses",
            "network_hosts",
            "expression",
            "mapping",
            "prompt",
            "checks",
            "output_name",
            "agent_ref",
            "input_mapping",
            "output_mapping",
        ):
            value = getattr(self, key)
            if value is not None:
                result[key] = list(value) if key == "checks" else thaw_json(value)
        return result


def _call_mapping(value: Any, field_name: str) -> Mapping[str, str]:
    """Child field names map to Workflow values; expressions are not accepted."""
    mapping = require_mapping(value, field_name)
    parsed = {
        require_string(key, field_name, pattern=_SLUG): require_string(
            target, field_name, pattern=NODE_ID_RE
        )
        for key, target in mapping.items()
    }
    return cast(Mapping[str, str], freeze_json(parsed))


@dataclass(frozen=True)
class Transition:
    from_node: str
    port: TransitionPort
    to_node: str

    @classmethod
    def from_dict(cls, data: Any) -> Transition:
        item = require_mapping(data, "transition")
        require_keys(
            item, allowed={"from", "port", "to"}, required={"from", "port", "to"}
        )
        try:
            port = TransitionPort(item["port"])
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("transition.port is unknown") from exc
        return cls(
            from_node=require_string(
                item["from"], "transition.from", pattern=NODE_ID_RE
            ),
            port=port,
            to_node=require_string(item["to"], "transition.to", pattern=NODE_ID_RE),
        )

    def to_dict(self) -> dict[str, str]:
        return {"from": self.from_node, "port": self.port.value, "to": self.to_node}


@dataclass(frozen=True)
class ProjectAgentDirectory:
    agent_id: str
    slug: str
    path: str
    version: str = "1.0.0"
    parent_agent_id: str | None = None
    _version_present: bool = field(default=False, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: Any) -> ProjectAgentDirectory:
        item = require_mapping(data, "project agent")
        require_keys(
            item,
            allowed={"agent_id", "slug", "path", "version", "parent_agent_id"},
            required={"agent_id", "slug", "path"},
        )
        path = require_string(item["path"], "project agent.path")
        slug = require_string(item["slug"], "project agent.slug", pattern=_SLUG)
        if "\\" in path or path != f"agents/{slug}":
            raise ContractValidationError(
                "project agent.path must be exactly agents/<slug>"
            )
        return cls(
            agent_id=require_uuid7(item["agent_id"], "project agent.agent_id"),
            slug=slug,
            path=path,
            version=require_semver(
                item.get("version", "1.0.0"), "project agent.version"
            ),
            _version_present="version" in item,
            parent_agent_id=(
                None
                if item.get("parent_agent_id") is None
                else require_uuid7(
                    item["parent_agent_id"], "project agent.parent_agent_id"
                )
            ),
        )

    def to_dict(self) -> dict[str, str]:
        result = {
            "agent_id": self.agent_id,
            "slug": self.slug,
            "path": self.path,
        }
        if self._version_present or self.version != "1.0.0":
            result["version"] = self.version
        if self.parent_agent_id is not None:
            result["parent_agent_id"] = self.parent_agent_id
        return result

    def ref(self) -> str:
        return f"{self.agent_id}@{self.version}"


@dataclass(frozen=True)
class ProjectManifest:
    schema_version: str
    project_version: str
    project_id: str
    name: str
    description: str
    agents: tuple[ProjectAgentDirectory, ...]
    default_agent_id: str | None
    resource_policy: ResourcePolicy
    workflows: tuple[ProjectOwnedResource, ...] = ()
    components: tuple[ProjectOwnedResource, ...] = ()
    knowledge: tuple[ProjectOwnedResource, ...] = ()
    assets: tuple[ProjectOwnedResource, ...] = ()
    resources: tuple[ProjectResourceBinding, ...] = ()
    _resource_fields: frozenset[str] = field(
        default_factory=frozenset, repr=False, compare=False
    )

    @classmethod
    def from_dict(cls, data: Any) -> ProjectManifest:
        item = require_mapping(data, "project manifest")
        require_keys(
            item,
            allowed={
                "schema_version",
                "project_version",
                "project_id",
                "name",
                "description",
                "agents",
                "default_agent_id",
                "resource_policy",
                "workflows",
                "components",
                "knowledge",
                "assets",
                "resources",
            },
            required={
                "schema_version",
                "project_version",
                "project_id",
                "name",
                "agents",
                "default_agent_id",
                "resource_policy",
            },
        )
        require_schema_version(item)
        if item["project_version"] != "1":
            raise ContractValidationError("project_version must be exactly '1'")
        agents = tuple(
            ProjectAgentDirectory.from_dict(value)
            for value in require_list(item["agents"], "agents")
        )
        if (
            len({agent.agent_id for agent in agents}) != len(agents)
            or len({agent.slug for agent in agents}) != len(agents)
            or len({agent.path for agent in agents}) != len(agents)
        ):
            raise ContractValidationError(
                "project agents must have unique IDs, slugs, and paths"
            )
        agent_ids = {agent.agent_id for agent in agents}
        for agent in agents:
            parent_id = agent.parent_agent_id
            if parent_id is None:
                continue
            if parent_id not in agent_ids or parent_id == agent.agent_id:
                raise ContractValidationError(
                    "project agent.parent_agent_id must identify another listed Agent"
                )
            seen: set[str] = {agent.agent_id}
            current: str | None = parent_id
            while current is not None:
                if current in seen:
                    raise ContractValidationError(
                        "project Agent parent references must not contain cycles"
                    )
                seen.add(current)
                parent = next(
                    (item for item in agents if item.agent_id == current), None
                )
                current = parent.parent_agent_id if parent is not None else None
        raw_default_agent_id = item["default_agent_id"]
        if not agents and raw_default_agent_id is not None:
            raise ContractValidationError(
                "default_agent_id must be null when a Project has no Agents"
            )
        if agents and raw_default_agent_id is None:
            raise ContractValidationError(
                "default_agent_id must identify a listed Project Agent"
            )
        default_agent_id = (
            None
            if raw_default_agent_id is None
            else require_uuid7(raw_default_agent_id, "default_agent_id")
        )
        if default_agent_id is not None and default_agent_id not in {
            agent.agent_id for agent in agents
        }:
            raise ContractValidationError(
                "default_agent_id must identify a listed Project Agent"
            )
        workflows = _owned_resources(item.get("workflows", []), ResourceKind.WORKFLOW)
        components = _owned_resources(
            item.get("components", []), ResourceKind.COMPONENT
        )
        knowledge = _owned_resources(item.get("knowledge", []), ResourceKind.KNOWLEDGE)
        assets = _owned_resources(item.get("assets", []), ResourceKind.ASSET)
        resources = tuple(
            ProjectResourceBinding.from_dict(value)
            for value in require_list(item.get("resources", []), "resources")
        )
        if len({binding.reference for binding in resources}) != len(resources):
            raise ContractValidationError("project resource bindings must be unique")
        return cls(
            SCHEMA_VERSION,
            "1",
            require_uuid7(item["project_id"], "project_id"),
            require_string(item["name"], "name"),
            _project_description(item.get("description", "")),
            agents,
            default_agent_id,
            ResourcePolicy.from_dict(item["resource_policy"]),
            workflows,
            components,
            knowledge,
            assets,
            resources,
            frozenset(
                {"workflows", "components", "knowledge", "assets", "resources"}
                & set(item)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version,
            "project_version": self.project_version,
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "agents": [agent.to_dict() for agent in self.agents],
            "default_agent_id": self.default_agent_id,
            "resource_policy": self.resource_policy.to_dict(),
        }

        for key in ("workflows", "components", "knowledge", "assets"):
            entries = getattr(self, key)
            if entries or key in self._resource_fields:
                result[key] = [item.to_dict() for item in entries]
        if self.resources or "resources" in self._resource_fields:
            result["resources"] = [item.to_dict() for item in self.resources]
        return result


def _is_dependency_ref(value: str) -> bool:
    if _REFERENCE.fullmatch(value):
        return True
    try:
        ResourceRef.from_string(value)
    except ContractValidationError:
        return False
    return True


def _dependency_ref(value: Any, field: str) -> str:
    text = require_string(value, field)
    if _is_dependency_ref(text):
        return text
    raise ContractValidationError(
        f"{field} must be a catalog reference or resource_id@version"
    )


def _owned_resources(
    value: Any, kind: ResourceKind
) -> tuple[ProjectOwnedResource, ...]:
    items = tuple(
        ProjectOwnedResource.from_dict(item, expected_kind=kind)
        for item in require_list(value, kind.value)
    )
    if (
        len({item.resource_id for item in items}) != len(items)
        or len({item.slug for item in items}) != len(items)
        or len({item.path for item in items}) != len(items)
    ):
        raise ContractValidationError(
            f"project {kind.value} entries must have unique IDs, slugs, and paths"
        )
    return items


def _project_description(value: Any) -> str:
    """Normalize portable Project metadata without changing its meaning."""
    if not isinstance(value, str):
        raise ContractValidationError("description must be a string")
    description = unicodedata.normalize("NFC", value).strip()
    if len(description) > 500:
        raise ContractValidationError("description must not exceed 500 characters")
    return description


@dataclass(frozen=True)
class ResourcePolicy:
    max_concurrent_runs: int
    max_nodes_per_run: int
    max_run_seconds: int

    @classmethod
    def from_dict(cls, data: Any) -> ResourcePolicy:
        item = require_mapping(data, "resource_policy")
        required = {"max_concurrent_runs", "max_nodes_per_run", "max_run_seconds"}
        require_keys(item, allowed=required, required=required)
        values = {key: item[key] for key in required}
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in values.values()
        ):
            raise ContractValidationError(
                "resource_policy limits must be positive integers"
            )
        if (
            values["max_concurrent_runs"] > HARD_MAX_CONCURRENT_RUNS
            or values["max_nodes_per_run"] > HARD_MAX_NODES
            or values["max_run_seconds"] > HARD_MAX_RUN_SECONDS
        ):
            raise ContractValidationError(
                "resource_policy exceeds a platform hard limit"
            )
        return cls(**values)

    def to_dict(self) -> dict[str, int]:
        return {
            "max_concurrent_runs": self.max_concurrent_runs,
            "max_nodes_per_run": self.max_nodes_per_run,
            "max_run_seconds": self.max_run_seconds,
        }


@dataclass(frozen=True)
class AgentBlueprint:
    schema_version: str
    goal: str
    inputs: Mapping[str, TypedField]
    outputs: Mapping[str, TypedField]
    nodes: tuple[FlowNode, ...]
    transitions: tuple[Transition, ...]
    required_capabilities: RequiredCapabilities
    requested_permissions: PermissionContract
    verification: VerifierContract
    ui_suggestions: Mapping[str, Any]

    @classmethod
    def from_dict(cls, data: Any) -> AgentBlueprint:
        item = require_mapping(data, "agent blueprint")
        required = {
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
        require_keys(item, allowed=required, required=required)
        require_schema_version(item)
        blueprint = cls(
            schema_version=SCHEMA_VERSION,
            goal=require_string(item["goal"], "goal"),
            inputs=_typed_fields(item["inputs"], "inputs"),
            outputs=_typed_fields(item["outputs"], "outputs"),
            nodes=tuple(
                FlowNode.from_dict(value)
                for value in require_list(item["nodes"], "nodes")
            ),
            transitions=tuple(
                Transition.from_dict(value)
                for value in require_list(item["transitions"], "transitions")
            ),
            required_capabilities=RequiredCapabilities.from_dict(
                item["required_capabilities"]
            ),
            requested_permissions=PermissionContract.from_dict(
                item["requested_permissions"]
            ),
            verification=VerifierContract.from_dict(item["verification"]),
            ui_suggestions=_ui_layout(item["ui_suggestions"]),
        )
        return blueprint.validated()

    def validated(self) -> AgentBlueprint:
        _validate_graph(
            self.nodes,
            self.transitions,
            self.outputs,
            self.verification,
            allowed_types=_AGENT_GRAPH_TYPES,
        )
        self.required_capabilities.validate_nodes(self.nodes)
        _validate_ui_node_references(self.ui_suggestions, self.nodes, "ui_suggestions")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "goal": self.goal,
            "inputs": typed_fields_to_wire(self.inputs),
            "outputs": typed_fields_to_wire(self.outputs),
            "nodes": [node.to_dict() for node in self.nodes],
            "transitions": [transition.to_dict() for transition in self.transitions],
            "required_capabilities": self.required_capabilities.to_dict(),
            "requested_permissions": self.requested_permissions.to_dict(),
            "verification": self.verification.to_dict(),
            "ui_suggestions": thaw_json(self.ui_suggestions),
        }


@dataclass(frozen=True)
class RequiredCapabilities:
    component_types: tuple[ComponentType, ...]
    tool_refs: tuple[str, ...]
    skill_refs: tuple[str, ...] = ()
    policy_refs: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Any) -> RequiredCapabilities:
        item = require_mapping(data, "required_capabilities")
        require_keys(
            item,
            allowed={"component_types", "tool_refs", "skill_refs", "policy_refs"},
            required={"component_types", "tool_refs"},
        )
        raw_types = require_list(
            item["component_types"], "required_capabilities.component_types"
        )
        try:
            component_types = tuple(ComponentType.parse(value) for value in raw_types)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError(
                "required_capabilities.component_types must use "
                "built-in component types"
            ) from exc
        if not component_types or len(set(component_types)) != len(component_types):
            raise ContractValidationError(
                "required_capabilities.component_types must be non-empty and unique"
            )
        return cls(
            component_types,
            _strict_str_list(
                item["tool_refs"], "required_capabilities.tool_refs", pattern=_REFERENCE
            ),
            _strict_str_list(
                item.get("skill_refs", []),
                "required_capabilities.skill_refs",
                pattern=_REFERENCE,
            ),
            _strict_str_list(
                item.get("policy_refs", []),
                "required_capabilities.policy_refs",
                pattern=_REFERENCE,
            ),
        )

    def validate_nodes(self, nodes: tuple[FlowNode, ...]) -> None:
        node_types = {node.component_type for node in nodes}
        node_tools = {node.uses for node in nodes if node.uses is not None}
        if node_types != set(self.component_types):
            raise ContractValidationError(
                "required_capabilities.component_types must exactly match graph nodes"
            )
        if node_tools != set(self.tool_refs):
            raise ContractValidationError(
                "required_capabilities.tool_refs must exactly match "
                "Tool node references"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_types": [
                component_type.value for component_type in self.component_types
            ],
            "tool_refs": list(self.tool_refs),
            "skill_refs": list(self.skill_refs),
            "policy_refs": list(self.policy_refs),
        }


def _typed_fields(value: Any, field: str) -> Mapping[str, TypedField]:
    return parse_typed_fields(value, field)


def _ui_layout(value: Any) -> Mapping[str, Any]:
    item = require_mapping(value, "ui")
    require_keys(
        item,
        allowed={"positions", "bindings", "notes", "labels"},
        required={"positions"},
    )
    positions = require_mapping(item["positions"], "ui.positions")
    parsed: dict[str, dict[str, int]] = {}
    for node_id, point in positions.items():
        require_string(node_id, "ui.positions node", pattern=NODE_ID_RE)
        coordinates = require_mapping(point, "ui.positions coordinate")
        require_keys(coordinates, allowed={"x", "y"}, required={"x", "y"})
        x, y = coordinates["x"], coordinates["y"]
        if any(
            isinstance(number, bool) or not isinstance(number, int) for number in (x, y)
        ):
            raise ContractValidationError("ui positions must have integer x and y")
        parsed[node_id] = {"x": x, "y": y}
    layout: dict[str, Any] = {"positions": parsed}
    if "bindings" in item:
        layout["bindings"] = _ui_bindings(item["bindings"])
    if "notes" in item:
        layout["notes"] = _ui_notes(item["notes"])
    if "labels" in item:
        layout["labels"] = _ui_labels(item["labels"])
    return cast(Mapping[str, Any], freeze_json(layout))


def _ui_bindings(value: Any) -> dict[str, dict[str, Any]]:
    item = require_mapping(value, "ui.bindings")
    parsed: dict[str, dict[str, Any]] = {}
    for binding_id, payload in item.items():
        require_string(binding_id, "ui.bindings id", pattern=NODE_ID_RE)
        entry = require_mapping(payload, "ui.bindings entry")
        require_keys(
            entry,
            allowed={"kind", "reference", "x", "y"},
            required={"kind", "reference", "x", "y"},
        )
        kind = require_string(entry["kind"], "ui.bindings.kind")
        if kind not in _BINDING_KINDS:
            raise ContractValidationError(
                "ui.bindings.kind must be skill, policy, template, mcp_tool, "
                "or knowledge"
            )
        x, y = entry["x"], entry["y"]
        if any(
            isinstance(number, bool) or not isinstance(number, int) for number in (x, y)
        ):
            raise ContractValidationError("ui bindings must have integer x and y")
        parsed[binding_id] = {
            "kind": kind,
            "reference": _dependency_ref(entry["reference"], "ui.bindings.reference"),
            "x": x,
            "y": y,
        }
    return parsed


_NOTE_COLORS = frozenset({"teal", "amber", "violet", "slate"})


def _ui_labels(value: Any) -> dict[str, str]:
    item = require_mapping(value, "ui.labels")
    parsed: dict[str, str] = {}
    for node_id, label in item.items():
        require_string(node_id, "ui.labels id", pattern=NODE_ID_RE)
        text = require_string(label, "ui.labels text").strip()
        if not text or len(text) > 80:
            raise ContractValidationError("ui.labels text must be 1 to 80 characters")
        parsed[node_id] = text
    return parsed


def _ui_notes(value: Any) -> dict[str, dict[str, Any]]:
    item = require_mapping(value, "ui.notes")
    parsed: dict[str, dict[str, Any]] = {}
    for note_id, payload in item.items():
        require_string(note_id, "ui.notes id", pattern=NODE_ID_RE)
        entry = require_mapping(payload, "ui.notes entry")
        require_keys(
            entry,
            allowed={"x", "y", "text", "color", "width"},
            required={"x", "y", "text"},
        )
        if not isinstance(entry["text"], str) or len(entry["text"]) > 4000:
            raise ContractValidationError(
                "ui.notes.text must be a string up to 4000 characters"
            )
        x, y = entry["x"], entry["y"]
        if any(
            isinstance(number, bool) or not isinstance(number, int) for number in (x, y)
        ):
            raise ContractValidationError("ui notes must have integer x and y")
        note: dict[str, Any] = {"x": x, "y": y, "text": entry["text"]}
        if "color" in entry:
            color = require_string(entry["color"], "ui.notes.color")
            if color not in _NOTE_COLORS:
                raise ContractValidationError(
                    "ui.notes.color must be teal, amber, violet, or slate"
                )
            note["color"] = color
        if "width" in entry:
            width = entry["width"]
            if (
                isinstance(width, bool)
                or not isinstance(width, int)
                or width < 160
                or width > 640
            ):
                raise ContractValidationError(
                    "ui.notes.width must be an integer between 160 and 640"
                )
            note["width"] = width
        parsed[note_id] = note
    return parsed


@dataclass(frozen=True)
class AgentSource:
    schema_version: str
    agentspec_version: str
    component_type: str
    agent_id: str
    slug: str
    name: str
    description: str
    inputs: Mapping[str, TypedField]
    outputs: Mapping[str, TypedField]
    nodes: tuple[FlowNode, ...]
    transitions: tuple[Transition, ...]
    runtime_profile: str
    secret_refs: tuple[str, ...]
    permissions: PermissionContract
    verification: VerifierContract
    skill_refs: tuple[str, ...]
    policy_refs: tuple[str, ...]
    ui: Mapping[str, Any]
    lock: Mapping[str, str]
    knowledge_refs: tuple[str, ...] = ()
    version: str = "1.0.0"
    _version_present: bool = field(default=False, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: Any) -> AgentSource:
        item = require_mapping(data, "agent source")
        allowed = {
            "schema_version",
            "agentspec_version",
            "component_type",
            "agent_id",
            "slug",
            "name",
            "description",
            "version",
            "inputs",
            "outputs",
            "nodes",
            "transitions",
            "extensions",
            "ui",
            "lock",
        }
        require_keys(item, allowed=allowed, required=allowed - {"version"})
        require_schema_version(item)
        if item["agentspec_version"] != "26.1" or item["component_type"] != "Flow":
            raise ContractValidationError(
                "only AgentSpec 26.1 Flow sources are supported"
            )
        extensions = require_mapping(item["extensions"], "extensions")
        require_keys(extensions, allowed={"veyra"}, required={"veyra"})
        veyra = require_mapping(extensions["veyra"], "extensions.veyra")
        require_keys(
            veyra,
            allowed={
                "runtime_profile",
                "secret_refs",
                "permissions",
                "verification",
                "skill_refs",
                "policy_refs",
                "knowledge_refs",
            },
            required={"runtime_profile", "secret_refs", "permissions", "verification"},
        )
        ui = _ui_layout(item["ui"])
        lock = require_mapping(item["lock"], "lock")
        if not lock or not all(
            isinstance(key, str)
            and _is_dependency_ref(key)
            and isinstance(value, str)
            and re.fullmatch(r"[0-9a-f]{64}", value)
            for key, value in lock.items()
        ):
            raise ContractValidationError(
                "lock must map versioned dependency references to SHA-256 digests"
            )
        source = cls(
            schema_version=SCHEMA_VERSION,
            agentspec_version="26.1",
            component_type="Flow",
            agent_id=require_uuid7(item["agent_id"], "agent_id"),
            slug=require_string(item["slug"], "slug", pattern=_SLUG),
            name=require_string(item["name"], "name"),
            description=require_string(item["description"], "description"),
            inputs=_typed_fields(item["inputs"], "inputs"),
            outputs=_typed_fields(item["outputs"], "outputs"),
            nodes=tuple(
                FlowNode.from_dict(value)
                for value in require_list(item["nodes"], "nodes")
            ),
            transitions=tuple(
                Transition.from_dict(value)
                for value in require_list(item["transitions"], "transitions")
            ),
            runtime_profile=require_string(veyra["runtime_profile"], "runtime_profile"),
            secret_refs=_strict_str_list(
                veyra["secret_refs"], "secret_refs", pattern=_SECRET_REF
            ),
            permissions=PermissionContract.from_dict(veyra["permissions"]),
            verification=VerifierContract.from_dict(veyra["verification"]),
            skill_refs=_strict_str_list(
                veyra.get("skill_refs", []), "skill_refs", pattern=_REFERENCE
            ),
            policy_refs=_strict_str_list(
                veyra.get("policy_refs", []), "policy_refs", pattern=_REFERENCE
            ),
            knowledge_refs=tuple(
                ResourceRef.from_string(ref).as_ref()
                for ref in _strict_str_list(
                    veyra.get("knowledge_refs", []), "knowledge_refs"
                )
            ),
            ui=ui,
            lock=freeze_json(dict(lock)),
            version=require_semver(item.get("version", "1.0.0"), "version"),
            _version_present="version" in item,
        )
        if any(
            node.component_type is ComponentType.AGENT_CALL for node in source.nodes
        ):
            raise ContractValidationError(
                "Agent graphs cannot contain AgentCall nodes; those belong to Workflows"
            )
        _validate_graph(
            source.nodes,
            source.transitions,
            source.outputs,
            source.verification,
            allowed_types=_AGENT_GRAPH_TYPES,
        )
        _validate_ui_node_references(source.ui, source.nodes, "ui")
        tool_references = {
            node.uses.rsplit("@", 1)[0] for node in source.nodes if node.uses
        }
        if not tool_references.issubset(set(source.permissions.tools)):
            raise ContractValidationError(
                "every Tool node must be included in permissions.tools"
            )
        exact_tool_references = {node.uses for node in source.nodes if node.uses}
        catalog_references = (
            exact_tool_references
            | set(source.skill_refs)
            | set(source.policy_refs)
            | set(source.knowledge_refs)
            | {
                str(binding["reference"])
                for binding in (source.ui.get("bindings") or {}).values()
            }
        )
        if not catalog_references.issubset(set(source.lock)):
            raise ContractValidationError(
                "every Tool, Skill, Policy, and catalog binding "
                "reference must be locked"
            )
        return source

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version,
            "agentspec_version": self.agentspec_version,
            "component_type": self.component_type,
            "agent_id": self.agent_id,
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "inputs": typed_fields_to_wire(self.inputs),
            "outputs": typed_fields_to_wire(self.outputs),
            "nodes": [node.to_dict() for node in self.nodes],
            "transitions": [transition.to_dict() for transition in self.transitions],
            "extensions": {
                "veyra": {
                    "runtime_profile": self.runtime_profile,
                    "secret_refs": list(self.secret_refs),
                    "permissions": self.permissions.to_dict(),
                    "verification": self.verification.to_dict(),
                    "skill_refs": list(self.skill_refs),
                    "policy_refs": list(self.policy_refs),
                }
            },
            "ui": thaw_json(self.ui),
            "lock": thaw_json(self.lock),
        }

        if self.knowledge_refs:
            result["extensions"]["veyra"]["knowledge_refs"] = list(self.knowledge_refs)
        if self._version_present or self.version != "1.0.0":
            result["version"] = self.version
        return result

    @property
    def source_hash(self) -> str:
        return source_hash(self.to_dict())

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
    def from_dict(cls, data: Any) -> AgentDraft:
        item = require_mapping(data, "agent draft")
        required = {
            "schema_version",
            "draft_id",
            "project_id",
            "agent_id",
            "revision",
            "blueprint",
        }
        require_keys(item, allowed=required, required=required)
        require_schema_version(item)
        revision = item["revision"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ContractValidationError(
                "draft revision must be a non-negative integer"
            )
        return cls(
            SCHEMA_VERSION,
            require_uuid7(item["draft_id"], "draft_id"),
            require_uuid7(item["project_id"], "project_id"),
            require_uuid7(item["agent_id"], "agent_id"),
            revision,
            AgentBlueprint.from_dict(item["blueprint"]),
        )


def _validate_ui_node_references(
    ui: Mapping[str, Any], nodes: tuple[FlowNode, ...], field: str
) -> None:
    positions = ui["positions"]
    unknown = set(positions) - {node.id for node in nodes}
    if unknown:
        unknown_nodes = ", ".join(sorted(unknown))
        raise ContractValidationError(
            f"{field}.positions references unknown node(s): {unknown_nodes}"
        )
    bindings = ui.get("bindings") or {}
    overlap = set(bindings) & {node.id for node in nodes}
    if overlap:
        colliding = ", ".join(sorted(overlap))
        raise ContractValidationError(
            f"{field}.bindings collide with Flow node id(s): {colliding}"
        )
    notes = ui.get("notes") or {}
    note_ids = set(notes)
    note_nodes = note_ids & {node.id for node in nodes}
    if note_nodes:
        colliding = ", ".join(sorted(note_nodes))
        raise ContractValidationError(
            f"{field}.notes collide with Flow node id(s): {colliding}"
        )
    note_bindings = note_ids & set(bindings)
    if note_bindings:
        colliding = ", ".join(sorted(note_bindings))
        raise ContractValidationError(
            f"{field}.notes collide with ui.bindings id(s): {colliding}"
        )
    labels = ui.get("labels") or {}
    unknown_labels = set(labels) - {node.id for node in nodes}
    if unknown_labels:
        colliding = ", ".join(sorted(unknown_labels))
        raise ContractValidationError(
            f"{field}.labels references unknown node(s): {colliding}"
        )


def _validate_graph(
    nodes: tuple[FlowNode, ...],
    transitions: tuple[Transition, ...],
    outputs: Mapping[str, TypedField],
    verification: VerifierContract,
    *,
    allowed_types: frozenset[ComponentType] = _AGENT_GRAPH_TYPES,
) -> None:
    if len(nodes) > HARD_MAX_NODES:
        raise ContractValidationError(
            f"Flow graph exceeds the {HARD_MAX_NODES}-node platform limit"
        )
    if len(transitions) > HARD_MAX_TRANSITIONS:
        raise ContractValidationError(
            f"Flow graph exceeds the {HARD_MAX_TRANSITIONS}-transition platform limit"
        )
    if not nodes or len({node.id for node in nodes}) != len(nodes):
        raise ContractValidationError("nodes must be non-empty with unique IDs")
    types = {node.id: node.component_type for node in nodes}
    unknown = {node.component_type for node in nodes} - allowed_types
    if unknown:
        names = ", ".join(sorted(item.value for item in unknown))
        raise ContractValidationError(
            f"graph contains component types not allowed at this layer: {names}"
        )
    if sum(node.component_type is ComponentType.START for node in nodes) != 1:
        raise ContractValidationError("a Flow needs exactly one Start node")
    if not any(node.component_type is ComponentType.OUTPUT for node in nodes):
        raise ContractValidationError("a Flow needs at least one Output node")
    output_names = [
        node.output_name
        for node in nodes
        if node.component_type is ComponentType.OUTPUT
    ]
    if any(name is None or name not in outputs for name in output_names):
        raise ContractValidationError("every Output node must name a declared output")
    if len(output_names) != len(set(output_names)):
        raise ContractValidationError("Output node output_name values must be unique")
    if len(output_names) > 1 and set(output_names) != set(outputs):
        raise ContractValidationError(
            "every declared output must have exactly one matching Output node"
        )
    if verification.required and not any(
        node.component_type is ComponentType.VERIFIER for node in nodes
    ):
        raise ContractValidationError("required verification needs a Verifier node")
    verifier_checks = {
        check
        for node in nodes
        if node.component_type is ComponentType.VERIFIER and node.checks is not None
        for check in node.checks
    }
    if verifier_checks != set(verification.checks):
        raise ContractValidationError(
            "Verifier node checks must exactly implement declared verification checks"
        )
    seen_edges: set[tuple[str, TransitionPort, str]] = set()
    seen_ports: set[tuple[str, TransitionPort]] = set()
    outgoing: dict[str, list[Transition]] = {node.id: [] for node in nodes}
    for transition in transitions:
        if transition.from_node not in types or transition.to_node not in types:
            raise ContractValidationError("transition references an unknown node")
        if transition.port not in _ALLOWED_PORTS[types[transition.from_node]]:
            raise ContractValidationError(
                "transition port is not allowed by its source component"
            )
        edge = (transition.from_node, transition.port, transition.to_node)
        if edge in seen_edges:
            raise ContractValidationError("duplicate transition")
        port_edge = (transition.from_node, transition.port)
        if port_edge in seen_ports:
            raise ContractValidationError(
                "each transition port may have exactly one target"
            )
        seen_edges.add(edge)
        seen_ports.add(port_edge)
        outgoing[transition.from_node].append(transition)
    for node in nodes:
        actual_ports = {edge.port for edge in outgoing[node.id]}
        if actual_ports != _ALLOWED_PORTS[node.component_type]:
            raise ContractValidationError(
                "component transitions must cover exactly its declared output ports"
            )
    start = next(
        node.id for node in nodes if node.component_type is ComponentType.START
    )
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
    indegree = {node.id: 0 for node in nodes}
    for transitions_from_node in outgoing.values():
        for transition_item in transitions_from_node:
            indegree[transition_item.to_node] += 1
    zero_indegree = [node_id for node_id, degree in indegree.items() if degree == 0]
    processed = 0
    while zero_indegree:
        node_id = zero_indegree.pop()
        processed += 1
        for transition_item in outgoing[node_id]:
            indegree[transition_item.to_node] -= 1
            if indegree[transition_item.to_node] == 0:
                zero_indegree.append(transition_item.to_node)
    if processed != len(nodes):
        raise ContractValidationError(
            "Flow graph must be a DAG; Loop is not a V1 component"
        )
