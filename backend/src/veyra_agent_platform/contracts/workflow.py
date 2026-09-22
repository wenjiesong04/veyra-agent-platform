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
from .resource import AgentVersionRef, require_semver
from .typed_io import TypedField, typed_fields_to_wire

_SLUG = re.compile(r"^[a-z][a-z0-9-]{0,62}$")


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
            "extensions",
            "ui",
            "lock",
        }
        require_keys(item, allowed=allowed, required=allowed - {"version"})
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
        if any(node.component_type is ComponentType.TOOL for node in nodes):
            raise ContractValidationError(
                "Workflow graphs cannot contain Tool nodes; those belong to Agents"
            )
        lock = require_mapping(item["lock"], "lock")
        if lock and not all(
            isinstance(key, str)
            and _is_agent_version_ref(key)
            and isinstance(value, str)
            and re.fullmatch(r"[0-9a-f]{64}", value)
            for key, value in lock.items()
        ):
            raise ContractValidationError(
                "lock must map agent_id@version_id references to SHA-256 digests"
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
        )
        _validate_graph(
            source.nodes,
            source.transitions,
            source.outputs,
            source.verification,
            allowed_types=_WORKFLOW_GRAPH_TYPES,
        )
        _validate_ui_node_references(source.ui, source.nodes, "ui")
        agent_refs = {node.agent_ref for node in source.nodes if node.agent_ref}
        if not agent_refs.issubset(set(source.lock)):
            raise ContractValidationError(
                "every AgentCall must lock its immutable target as agent_id@version_id"
            )
        if set(source.lock) != agent_refs:
            raise ContractValidationError(
                "Workflow lock contains unused Agent references"
            )
        return source

    @property
    def component_type(self) -> str:
        return "Workflow"

    def to_dict(self) -> dict[str, Any]:
        return {
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
