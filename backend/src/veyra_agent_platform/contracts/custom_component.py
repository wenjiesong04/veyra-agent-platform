"""Project-owned Custom Component definitions.

A Custom Component is a reusable executable capability with typed I/O. It is
not a business-specific ComponentType. Agent graphs pin component_id@version
and never copy the implementation into AgentSource.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from .agent import PermissionContract
from .canonical import sha256_digest
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
from .resource import ResourceRef, require_semver
from .typed_io import TypedField, parse_typed_fields, typed_fields_to_wire

_SLUG = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_CATALOG_REFERENCE = re.compile(r"^[a-z][a-z0-9_.-]*@[0-9]+\.[0-9]+\.[0-9]+$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_SECRET_KEY = re.compile(
    r"(api[_-]?key|authorization|secret|password|token|private[_-]?key|credential)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(?:\bsk-[A-Za-z0-9_-]{20,}|\bgh[pousr]_[A-Za-z0-9]{20,}|"
    r"\bgithub_pat_[A-Za-z0-9_]{20,}|\bxox[baprs]-[A-Za-z0-9-]{20,}|"
    r"\bAKIA[0-9A-Z]{16}\b|\bBearer\s+\S+)",
    re.IGNORECASE,
)
_ABSOLUTE_PATH = re.compile(r"^(?:/|[a-zA-Z]:\\|file://|\\\\)")
_FORBIDDEN_KINDS = frozenset(
    {
        "python",
        "javascript",
        "js",
        "code",
        "shell",
        "eval",
        "exec",
        "wasm",
        "script",
    }
)
_EMPTY_PERMISSIONS: dict[str, Any] = {
    "network_hosts": [],
    "tools": [],
    "filesystem_read_roots": [],
    "filesystem_write_roots": [],
    "shell_workspace_only": False,
}


class CustomComponentImplementationKind(StrEnum):
    MODEL_RECIPE = "model_recipe"
    TOOL_WRAPPER = "tool_wrapper"
    TRANSFORM = "transform"
    COMPOSITE_GRAPH = "composite_graph"


class CustomComponentLifecycle(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class CustomComponentProvenance(StrEnum):
    MANUAL = "manual"
    BUILDER = "builder"
    IMPORTED = "imported"


class CustomComponentReadiness(StrEnum):
    READY = "ready"
    REQUIRES_CONFIGURATION = "requires_configuration"
    DESIGN_ONLY = "design_only"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class CustomComponentDependency:
    """Exact Catalog pin used by a published Custom Component version."""

    reference: str
    content_hash: str

    @classmethod
    def from_dict(cls, data: Any) -> CustomComponentDependency:
        item = require_mapping(data, "custom component dependency")
        require_keys(
            item, allowed={"reference", "content_hash"}, required={"reference"}
        )
        reference = require_string(
            item["reference"], "dependency.reference", pattern=_CATALOG_REFERENCE
        )
        content_hash = require_string(
            item.get("content_hash", "0" * 64), "dependency.content_hash"
        )
        if not _HASH.fullmatch(content_hash):
            raise ContractValidationError(
                "custom component dependency content_hash must be SHA-256"
            )
        return cls(reference=reference, content_hash=content_hash)

    def to_dict(self) -> dict[str, str]:
        return {"reference": self.reference, "content_hash": self.content_hash}


@dataclass(frozen=True)
class CustomComponentImplementation:
    kind: CustomComponentImplementationKind
    instruction: str | None = None
    model_ref: str | None = None
    tool_reference: str | None = None
    mapping: Mapping[str, str] | None = None
    input_mapping: Mapping[str, str] | None = None
    output_mapping: Mapping[str, str] | None = None
    graph: Mapping[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: Any) -> CustomComponentImplementation:
        item = require_mapping(data, "custom component implementation")
        kind_raw = require_string(item.get("kind"), "implementation.kind")
        if kind_raw in _FORBIDDEN_KINDS:
            raise ContractValidationError(
                "arbitrary code Custom Component kinds are not allowed"
            )
        try:
            kind = CustomComponentImplementationKind(kind_raw)
        except ValueError as exc:
            raise ContractValidationError(
                "implementation.kind must be model_recipe, tool_wrapper, "
                "transform, or composite_graph"
            ) from exc
        _reject_secrets(item, "implementation")
        allowed = {
            "kind",
            "instruction",
            "model_ref",
            "tool_reference",
            "mapping",
            "input_mapping",
            "output_mapping",
            "graph",
        }
        require_keys(item, allowed=allowed, required={"kind"})
        if kind is CustomComponentImplementationKind.MODEL_RECIPE:
            require_keys(
                item,
                allowed={"kind", "instruction", "model_ref"},
                required={"kind", "instruction"},
            )
            instruction = require_string(
                item["instruction"], "implementation.instruction"
            )
            if len(instruction) > 20_000:
                raise ContractValidationError(
                    "model_recipe instruction must be at most 20000 characters"
                )
            model_ref = require_string(
                item.get("model_ref", "model.primary"), "implementation.model_ref"
            )
            if model_ref != "model.primary":
                raise ContractValidationError(
                    "model_recipe must use the Agent Runtime model.primary"
                )
            return cls(kind=kind, instruction=instruction, model_ref=model_ref)
        if kind is CustomComponentImplementationKind.TOOL_WRAPPER:
            require_keys(
                item,
                allowed={
                    "kind",
                    "tool_reference",
                    "input_mapping",
                    "output_mapping",
                },
                required={"kind", "tool_reference"},
            )
            tool_reference = require_string(
                item["tool_reference"],
                "implementation.tool_reference",
                pattern=_CATALOG_REFERENCE,
            )
            return cls(
                kind=kind,
                tool_reference=tool_reference,
                input_mapping=_string_map(
                    item.get("input_mapping"), "implementation.input_mapping"
                ),
                output_mapping=_string_map(
                    item.get("output_mapping"), "implementation.output_mapping"
                ),
            )
        if kind is CustomComponentImplementationKind.TRANSFORM:
            require_keys(
                item, allowed={"kind", "mapping"}, required={"kind", "mapping"}
            )
            mapping = _string_map(item["mapping"], "implementation.mapping")
            if mapping is None or not mapping:
                raise ContractValidationError(
                    "transform mapping must be a non-empty string map"
                )
            return cls(kind=kind, mapping=mapping)
        require_keys(item, allowed={"kind", "graph"}, required={"kind"})
        graph = item.get("graph")
        if graph is not None:
            graph = freeze_json(require_mapping(graph, "implementation.graph"))
        return cls(kind=kind, graph=graph)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind.value}
        if self.instruction is not None:
            payload["instruction"] = self.instruction
        if self.model_ref is not None:
            payload["model_ref"] = self.model_ref
        if self.tool_reference is not None:
            payload["tool_reference"] = self.tool_reference
        if self.mapping is not None:
            payload["mapping"] = thaw_json(self.mapping)
        if self.input_mapping is not None:
            payload["input_mapping"] = thaw_json(self.input_mapping)
        if self.output_mapping is not None:
            payload["output_mapping"] = thaw_json(self.output_mapping)
        if self.graph is not None:
            payload["graph"] = thaw_json(self.graph)
        return payload


@dataclass(frozen=True)
class CustomComponentDefinition:
    schema_version: str
    component_id: str
    project_id: str
    slug: str
    display_name: str
    description: str
    version: str
    inputs: Mapping[str, TypedField]
    outputs: Mapping[str, TypedField]
    implementation: CustomComponentImplementation
    metadata: Mapping[str, str]
    dependencies: tuple[CustomComponentDependency, ...]
    required_permissions: PermissionContract
    readiness: CustomComponentReadiness
    provenance: CustomComponentProvenance
    lifecycle: CustomComponentLifecycle
    created_at: str
    updated_at: str

    @classmethod
    def from_dict(cls, data: Any) -> CustomComponentDefinition:
        item = require_mapping(data, "custom component")
        require_keys(
            item,
            allowed={
                "schema_version",
                "component_id",
                "project_id",
                "slug",
                "display_name",
                "description",
                "version",
                "inputs",
                "outputs",
                "implementation",
                "metadata",
                "dependencies",
                "required_permissions",
                "readiness",
                "provenance",
                "lifecycle",
                "created_at",
                "updated_at",
            },
            required={
                "schema_version",
                "component_id",
                "project_id",
                "slug",
                "display_name",
                "description",
                "version",
                "inputs",
                "outputs",
                "implementation",
            },
        )
        require_schema_version(item)
        _reject_secrets(item, "custom component")
        implementation = CustomComponentImplementation.from_dict(item["implementation"])
        metadata = _string_map(item.get("metadata", {}), "metadata") or {}
        if any(
            not re.fullmatch(r"[a-z][a-z0-9_.-]{0,62}", key) or len(value) > 500
            for key, value in metadata.items()
        ):
            raise ContractValidationError("metadata must contain short labeled strings")
        dependencies = tuple(
            CustomComponentDependency.from_dict(value)
            for value in require_list(item.get("dependencies", []), "dependencies")
        )
        if len({dep.reference for dep in dependencies}) != len(dependencies):
            raise ContractValidationError(
                "custom component dependencies must be unique"
            )
        try:
            provenance = CustomComponentProvenance(
                item.get("provenance", CustomComponentProvenance.MANUAL.value)
            )
            lifecycle = CustomComponentLifecycle(
                item.get("lifecycle", CustomComponentLifecycle.DRAFT.value)
            )
            readiness = CustomComponentReadiness(
                item.get(
                    "readiness", CustomComponentReadiness.REQUIRES_CONFIGURATION.value
                )
            )
        except ValueError as exc:
            raise ContractValidationError(
                "custom component provenance, lifecycle, or readiness is invalid"
            ) from exc
        if implementation.kind is CustomComponentImplementationKind.COMPOSITE_GRAPH:
            readiness = CustomComponentReadiness.DESIGN_ONLY
        permissions = PermissionContract.from_dict(
            item.get("required_permissions", _EMPTY_PERMISSIONS)
        )
        return cls(
            schema_version=SCHEMA_VERSION,
            component_id=require_uuid7(item["component_id"], "component_id"),
            project_id=require_uuid7(item["project_id"], "project_id"),
            slug=require_string(item["slug"], "slug", pattern=_SLUG),
            display_name=require_string(item["display_name"], "display_name"),
            description=require_string(item["description"], "description"),
            version=require_semver(item["version"], "version"),
            inputs=parse_typed_fields(item["inputs"], "inputs"),
            outputs=parse_typed_fields(item["outputs"], "outputs"),
            implementation=implementation,
            metadata=metadata,
            dependencies=dependencies,
            required_permissions=permissions,
            readiness=readiness,
            provenance=provenance,
            lifecycle=lifecycle,
            created_at=require_string(
                item.get("created_at", "1970-01-01T00:00:00Z"), "created_at"
            ),
            updated_at=require_string(
                item.get("updated_at", "1970-01-01T00:00:00Z"), "updated_at"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "component_id": self.component_id,
            "project_id": self.project_id,
            "slug": self.slug,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "inputs": typed_fields_to_wire(self.inputs),
            "outputs": typed_fields_to_wire(self.outputs),
            "implementation": self.implementation.to_dict(),
            "metadata": thaw_json(self.metadata),
            "dependencies": [item.to_dict() for item in self.dependencies],
            "required_permissions": self.required_permissions.to_dict(),
            "readiness": self.readiness.value,
            "provenance": self.provenance.value,
            "lifecycle": self.lifecycle.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def ref(self) -> str:
        return ResourceRef.from_parts(self.component_id, self.version).as_ref()

    def content_hash(self) -> str:
        material = self.to_dict()
        material.pop("created_at", None)
        material.pop("updated_at", None)
        material.pop("readiness", None)
        return sha256_digest(material)


def empty_permissions() -> dict[str, Any]:
    return dict(_EMPTY_PERMISSIONS)


def permissions_subset(
    claimed: PermissionContract, allowed: PermissionContract
) -> bool:
    """True when claimed grants are within the union of real dependency grants."""

    return (
        set(claimed.network_hosts) <= set(allowed.network_hosts)
        and set(claimed.tools) <= set(allowed.tools)
        and set(claimed.filesystem_read_roots) <= set(allowed.filesystem_read_roots)
        and set(claimed.filesystem_write_roots) <= set(allowed.filesystem_write_roots)
        and (not claimed.shell_workspace_only or allowed.shell_workspace_only)
    )


def _string_map(value: Any, field: str) -> Mapping[str, str] | None:
    if value is None:
        return None
    mapping = require_mapping(value, field)
    if not all(
        isinstance(key, str) and key and isinstance(item, str) and item
        for key, item in mapping.items()
    ):
        raise ContractValidationError(f"{field} must be a string map")
    return cast(Mapping[str, str], freeze_json(dict(mapping)))


def _reject_secrets(value: Any, field: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and _SECRET_KEY.search(key):
                raise ContractValidationError(
                    f"{field} must not store secrets or credentials"
                )
            _reject_secrets(item, field)
        return
    if isinstance(value, list):
        for item in value:
            _reject_secrets(item, field)
        return
    if isinstance(value, str) and _ABSOLUTE_PATH.match(value):
        raise ContractValidationError(f"{field} must not store host absolute paths")
    if isinstance(value, str) and _SECRET_VALUE.search(value):
        raise ContractValidationError(f"{field} must not store secret values")
