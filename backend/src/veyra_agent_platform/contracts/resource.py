"""Identity, manifests, and portable packages for Project-owned resources.

Published resources use resource_id + semver. Workflow calls use a separate
AgentVersionRef pinned to an immutable local version ID. Paths are storage hints.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

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
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_RESOURCE_REF = re.compile(
    r"^([0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})"
    r"@([0-9]+\.[0-9]+\.[0-9]+)$"
)

RESOURCE_FOLDERS: dict[str, str] = {
    "agent": "agents",
    "workflow": "workflows",
    "component": "components",
    "knowledge": "knowledge",
    "asset": "assets",
}


class ResourceKind(StrEnum):
    PROJECT = "project"
    AGENT = "agent"
    WORKFLOW = "workflow"
    COMPONENT = "component"
    KNOWLEDGE = "knowledge"
    ASSET = "asset"


class ComponentClass(StrEnum):
    """Keep marketplace Components from collapsing into one bag of nodes."""

    PRIMITIVE = "primitive"
    COMPOSITE = "composite"


def component_storage_path(component_class: ComponentClass, slug: str) -> str:
    return f"components/{component_class.value}/{slug}"


@dataclass(frozen=True)
class ResourceRef:
    """Stable cross-resource pointer: ID and version, never a filesystem path."""

    resource_id: str
    version: str

    @classmethod
    def from_string(cls, value: Any, field: str = "resource_ref") -> ResourceRef:
        text = require_string(value, field)
        matched = _RESOURCE_REF.fullmatch(text)
        if matched is None:
            raise ContractValidationError(
                f"{field} must be resource_id@version using UUIDv7 and semver"
            )
        return cls(resource_id=matched.group(1), version=matched.group(2))

    @classmethod
    def from_parts(cls, resource_id: str, version: str) -> ResourceRef:
        return cls(
            resource_id=require_uuid7(resource_id, "resource_id"),
            version=require_string(version, "version", pattern=_VERSION),
        )

    def as_ref(self) -> str:
        return f"{self.resource_id}@{self.version}"


@dataclass(frozen=True)
class AgentVersionRef:
    """A Workflow target pinned to an immutable Agent version, both UUIDv7."""

    agent_id: str
    version_id: str

    @classmethod
    def from_string(cls, value: Any, field: str = "agent_ref") -> AgentVersionRef:
        text = require_string(value, field)
        parts = text.split("@")
        try:
            if len(parts) != 2:
                raise ContractValidationError("invalid reference")
            return cls.from_parts(parts[0], parts[1])
        except ContractValidationError as exc:
            raise ContractValidationError(
                f"{field} must be agent_id@version_id using two UUIDv7 IDs; "
                "rebind the call to a saved immutable Agent version"
            ) from exc

    @classmethod
    def from_parts(cls, agent_id: str, version_id: str) -> AgentVersionRef:
        return cls(
            agent_id=require_uuid7(agent_id, "agent_id"),
            version_id=require_uuid7(version_id, "version_id"),
        )

    def as_ref(self) -> str:
        return f"{self.agent_id}@{self.version_id}"


@dataclass(frozen=True)
class ResourceManifest:
    """Per-directory identity file stored beside the resource source."""

    schema_version: str
    kind: ResourceKind
    resource_id: str
    version: str
    slug: str
    name: str
    description: str
    component_class: ComponentClass | None = None

    @classmethod
    def from_dict(cls, data: Any) -> ResourceManifest:
        item = require_mapping(data, "resource manifest")
        require_keys(
            item,
            allowed={
                "schema_version",
                "kind",
                "resource_id",
                "version",
                "slug",
                "name",
                "description",
                "component_class",
            },
            required={
                "schema_version",
                "kind",
                "resource_id",
                "version",
                "slug",
                "name",
            },
        )
        require_schema_version(item)
        try:
            kind = ResourceKind(item["kind"])
        except (TypeError, ValueError) as exc:
            raise ContractValidationError(
                "resource manifest kind is not a V1 resource kind"
            ) from exc
        if kind is ResourceKind.PROJECT:
            raise ContractValidationError(
                "project identity belongs in project.vproject.yaml"
            )
        component_class = _optional_component_class(item, kind)
        return cls(
            schema_version=SCHEMA_VERSION,
            kind=kind,
            resource_id=require_uuid7(item["resource_id"], "resource_id"),
            version=require_string(item["version"], "version", pattern=_VERSION),
            slug=require_string(item["slug"], "slug", pattern=_SLUG),
            name=require_string(item["name"], "name"),
            description=require_string(item.get("description", ""), "description"),
            component_class=component_class,
        )

    def to_dict(self) -> dict[str, str]:
        payload = {
            "schema_version": self.schema_version,
            "kind": self.kind.value,
            "resource_id": self.resource_id,
            "version": self.version,
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
        }
        if self.component_class is not None:
            payload["component_class"] = self.component_class.value
        return payload

    def ref(self) -> ResourceRef:
        return ResourceRef(resource_id=self.resource_id, version=self.version)


@dataclass(frozen=True)
class PackageEnvelope:
    """Unified import/export wrapper for one resource or a Project bundle."""

    schema_version: str
    kind: ResourceKind
    resource_id: str
    version: str
    name: str
    dependencies: tuple[ResourceRef, ...]
    component_class: ComponentClass | None = None

    @classmethod
    def from_dict(cls, data: Any) -> PackageEnvelope:
        item = require_mapping(data, "package envelope")
        require_keys(
            item,
            allowed={
                "schema_version",
                "kind",
                "resource_id",
                "version",
                "name",
                "dependencies",
                "component_class",
            },
            required={"schema_version", "kind", "resource_id", "version", "name"},
        )
        require_schema_version(item)
        try:
            kind = ResourceKind(item["kind"])
        except (TypeError, ValueError) as exc:
            raise ContractValidationError(
                "package kind is not a V1 resource kind"
            ) from exc
        dependencies = tuple(
            ResourceRef.from_string(value, "dependencies")
            for value in require_list(item.get("dependencies", []), "dependencies")
        )
        refs = [item.as_ref() for item in dependencies]
        if len(set(refs)) != len(refs):
            raise ContractValidationError("package dependencies must be unique")
        return cls(
            schema_version=SCHEMA_VERSION,
            kind=kind,
            resource_id=require_uuid7(item["resource_id"], "resource_id"),
            version=require_string(item["version"], "version", pattern=_VERSION),
            name=require_string(item["name"], "name"),
            dependencies=dependencies,
            component_class=_optional_component_class(item, kind),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "kind": self.kind.value,
            "resource_id": self.resource_id,
            "version": self.version,
            "name": self.name,
            "dependencies": [item.as_ref() for item in self.dependencies],
        }
        if self.component_class is not None:
            payload["component_class"] = self.component_class.value
        return payload


@dataclass(frozen=True)
class ProjectOwnedResource:
    """Manifest listing for one owned resource. Path is derived from kind+slug."""

    kind: ResourceKind
    resource_id: str
    slug: str
    version: str
    path: str
    component_class: ComponentClass | None = None

    @classmethod
    def from_dict(
        cls, data: Any, *, expected_kind: ResourceKind
    ) -> ProjectOwnedResource:
        item = require_mapping(data, f"project {expected_kind.value}")
        require_keys(
            item,
            allowed={
                "kind",
                "resource_id",
                "slug",
                "version",
                "path",
                "component_class",
            },
            required={"resource_id", "slug", "version", "path"},
        )
        kind = expected_kind
        if "kind" in item:
            try:
                kind = ResourceKind(item["kind"])
            except (TypeError, ValueError) as exc:
                raise ContractValidationError(
                    f"project {expected_kind.value}.kind is invalid"
                ) from exc
            if kind is not expected_kind:
                raise ContractValidationError(
                    f"project listing kind must be {expected_kind.value}"
                )
        slug = require_string(item["slug"], "slug", pattern=_SLUG)
        component_class = _optional_component_class(item, kind)
        folder = RESOURCE_FOLDERS[expected_kind.value]
        expected_path = (
            component_storage_path(component_class, slug)
            if component_class is not None
            else f"{folder}/{slug}"
        )
        path = require_string(item["path"], "path")
        if "\\" in path or path != expected_path:
            raise ContractValidationError(
                f"project {expected_kind.value}.path must be exactly {expected_path}"
            )
        return cls(
            kind=kind,
            resource_id=require_uuid7(item["resource_id"], "resource_id"),
            slug=slug,
            version=require_string(item["version"], "version", pattern=_VERSION),
            path=path,
            component_class=component_class,
        )

    def to_dict(self) -> dict[str, str]:
        payload = {
            "kind": self.kind.value,
            "resource_id": self.resource_id,
            "slug": self.slug,
            "version": self.version,
            "path": self.path,
        }
        if self.component_class is not None:
            payload["component_class"] = self.component_class.value
        return payload


def require_semver(value: Any, field: str) -> str:
    return require_string(value, field, pattern=_VERSION)


def _optional_component_class(
    item: Mapping[str, Any], kind: ResourceKind
) -> ComponentClass | None:
    raw = item.get("component_class")
    if kind is ResourceKind.COMPONENT:
        if raw is None:
            raise ContractValidationError(
                "component resources must declare component_class"
            )
        try:
            return ComponentClass(raw)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError(
                "component_class must be primitive or composite"
            ) from exc
    if raw is not None:
        raise ContractValidationError(
            "component_class is only valid on component resources"
        )
    return None
