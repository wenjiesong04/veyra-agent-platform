"""Portable Workflow source: orchestrate Agents by ID@version, not by path."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .agent import (
    _WORKFLOW_GRAPH_TYPES,
    ComponentType,
    FlowNode,
    PermissionContract,
    Transition,
    VerifierContract,
    _typed_fields,
    _ui_layout,
    _validate_graph,
    _validate_ui_node_references,
)
from .canonical import behavior_hash, lock_hash, source_hash
from .common import (
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
from .dataflow import (
    DataEdge,
    data_edges_to_wire,
    parse_data_edges,
    validate_data_edges,
)
from .resource import AgentVersionRef, require_semver
from .typed_io import TypedField, typed_fields_to_wire

_SLUG = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_CATALOG_REF = re.compile(r"^[a-z][a-z0-9_.-]*@[0-9]+\.[0-9]+\.[0-9]+$")


@dataclass(frozen=True)
class WorkflowSource:
    schema_version: str
    workflow_id: str
    slug: str
    name: str
    description: str
    version: str
    inputs: Mapping[str, TypedField]
    outputs: Mapping[str, TypedField]
    nodes: tuple[FlowNode, ...]
    transitions: tuple[Transition, ...]
    permissions: PermissionContract
    verification: VerifierContract
    ui: Mapping[str, Any]
    lock: Mapping[str, str]
    data_edges: tuple[DataEdge, ...] = ()

    @classmethod
    def from_dict(cls, data: Any) -> WorkflowSource:
        item = require_mapping(data, "workflow source")
        allowed = {
            "schema_version",
            "component_type",
            "workflow_id",
            "slug",
            "name",
            "description",
            "version",
            "inputs",
            "outputs",
            "nodes",
            "transitions",
            "data_edges",
            "extensions",
            "ui",
            "lock",
        }
        require_keys(
            item,
            allowed=allowed,
            required=allowed - {"version", "data_edges"},
        )
        require_schema_version(item)
        if item.get("component_type", "Workflow") != "Workflow":
            raise ContractValidationError(
                "workflow source component_type must be Workflow"
            )
        extensions = require_mapping(
            item.get("extensions", {"veyra": {}}), "extensions"
        )
        require_keys(extensions, allowed={"veyra"}, required={"veyra"})
        veyra = require_mapping(extensions["veyra"], "extensions.veyra")
        require_keys(
            veyra,
            allowed={"permissions", "verification"},
            required={"permissions", "verification"},
        )
        nodes = tuple(
            FlowNode.from_dict(value) for value in require_list(item["nodes"], "nodes")
        )
        if any(
            node.component_type in {ComponentType.AGENT, ComponentType.MODEL}
            for node in nodes
        ):
            raise ContractValidationError(
                "Workflow graphs cannot contain Model nodes; edit the Agent instead"
            )
        lock = require_mapping(item["lock"], "lock")
        if lock and not all(
            isinstance(key, str)
            and (_is_agent_version_ref(key) or _is_catalog_lock_key(key))
            and isinstance(value, str)
            and re.fullmatch(r"[0-9a-f]{64}", value)
            for key, value in lock.items()
        ):
            raise ContractValidationError(
                "lock must map agent_id@version_id or catalog references "
                "to SHA-256 digests"
            )
        source = cls(
            schema_version=SCHEMA_VERSION,
            workflow_id=require_uuid7(item["workflow_id"], "workflow_id"),
            slug=require_string(item["slug"], "slug", pattern=_SLUG),
            name=require_string(item["name"], "name"),
            description=require_string(item["description"], "description"),
            version=require_semver(item.get("version", "1.0.0"), "version"),
            inputs=_typed_fields(item["inputs"], "inputs"),
            outputs=_typed_fields(item["outputs"], "outputs"),
            nodes=nodes,
            transitions=tuple(
                Transition.from_dict(value)
                for value in require_list(item["transitions"], "transitions")
            ),
            permissions=PermissionContract.from_dict(veyra["permissions"]),
            verification=VerifierContract.from_dict(veyra["verification"]),
            ui=_ui_layout(item["ui"]),
            lock=freeze_json(dict(lock)),
            data_edges=parse_data_edges(item.get("data_edges"), "data_edges"),
        )
        _validate_graph(
            source.nodes,
            source.transitions,
            source.outputs,
            source.verification,
            allowed_types=_WORKFLOW_GRAPH_TYPES,
            namespaced_ports=bool(source.data_edges),
        )
        _validate_ui_node_references(source.ui, source.nodes, "ui")
        if source.data_edges:
            validate_data_edges(
                inputs=source.inputs,
                outputs=source.outputs,
                nodes=source.nodes,
                edges=source.data_edges,
            )
        agent_refs = {node.agent_ref for node in source.nodes if node.agent_ref}
        tool_refs = {node.uses for node in source.nodes if node.uses is not None}
        required_lock = agent_refs | tool_refs
        if not required_lock.issubset(set(source.lock)):
            raise ContractValidationError(
                "every AgentCall and Tool must lock its immutable target"
            )
        if set(source.lock) != required_lock:
            raise ContractValidationError("Workflow lock contains unused references")
        source.permissions.validate_input_fields(source.inputs)
        return source

    @property
    def component_type(self) -> str:
        return "Workflow"

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version,
            "component_type": "Workflow",
            "workflow_id": self.workflow_id,
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "inputs": typed_fields_to_wire(self.inputs),
            "outputs": typed_fields_to_wire(self.outputs),
            "nodes": [node.to_dict() for node in self.nodes],
            "transitions": [transition.to_dict() for transition in self.transitions],
            "extensions": {
                "veyra": {
                    "permissions": self.permissions.to_dict(),
                    "verification": self.verification.to_dict(),
                }
            },
            "ui": thaw_json(self.ui),
            "lock": thaw_json(self.lock),
        }
        if self.data_edges:
            result["data_edges"] = data_edges_to_wire(self.data_edges)
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


def _is_agent_version_ref(value: str) -> bool:
    try:
        AgentVersionRef.from_string(value)
    except ContractValidationError:
        return False
    return True


def _is_catalog_lock_key(value: str) -> bool:
    return bool(_CATALOG_REF.fullmatch(value))
