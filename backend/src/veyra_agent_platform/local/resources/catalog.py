"""Immutable, server-owned descriptors for local Factory and Studio resources."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any, Final, Literal

from veyra_agent_platform.contracts.agent import ComponentType
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import SCHEMA_VERSION

from .registry import load_node_packages, load_overlay_packages

ResourceKind = Literal["component", "tool", "mcp_tool", "skill", "policy", "template"]
Availability = Literal[
    "ready",
    "requires_configuration",
    "design_only",
    "quarantined",
    "disabled",
    "unavailable",
]
RuntimeStatus = Literal["supported", "runtime_not_configured", "runtime_not_supported"]

RESOURCE_KINDS: Final[tuple[ResourceKind, ...]] = (
    "component",
    "tool",
    "mcp_tool",
    "skill",
    "policy",
    "template",
)
_COMPONENT_ORDER: Final[tuple[str, ...]] = tuple(item.value for item in ComponentType)


class ResourceCatalogError(ValueError):
    """Raised when a requested catalog filter or immutable reference is invalid."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ResourceCatalog:
    """Expose copies of node.yaml packages; callers cannot mutate catalog state."""

    def __init__(
        self,
        nodes_root: Path | None = None,
        overlay_root: Path | None = None,
    ) -> None:
        self._nodes_root = nodes_root
        self._overlay_root = overlay_root
        self._lock = RLock()
        self._builtin = tuple(
            self._descriptor(package.definition, origin="builtin")
            for package in load_node_packages(nodes_root)
        )
        self._rebuild()

    def reload_overlays(self) -> None:
        """Re-read application-data overlays without mutating builtin packages."""
        with self._lock:
            self._rebuild()

    def _rebuild(self) -> None:
        overlays: list[dict[str, Any]] = []
        builtin_keys = {
            (resource["resource_id"], resource["version"]) for resource in self._builtin
        }
        for package in load_overlay_packages(self._overlay_root):
            origin = "workshop" if package.family == "workshop" else "discovered"
            descriptor = self._descriptor(package.definition, origin=origin)
            key = (descriptor["resource_id"], descriptor["version"])
            if key in builtin_keys:
                continue
            overlays.append(descriptor)
            builtin_keys.add(key)
        resources = list(self._builtin) + overlays
        resources.sort(key=_resource_sort_key)
        self._resources = tuple(resources)
        self._by_reference = {
            (resource["resource_id"], resource["version"]): resource
            for resource in self._resources
        }

    def resources(
        self, *, kind: str | None = None, availability: str | None = None
    ) -> dict[str, Any]:
        with self._lock:
            self._validate_kind(kind)
            self._validate_availability(availability)
            selected = [
                resource
                for resource in self._resources
                if (kind is None or resource["kind"] == kind)
                and (availability is None or resource["availability"] == availability)
            ]
            return {
                "schema_version": SCHEMA_VERSION,
                "resources": deepcopy(selected),
                "kinds": [
                    {
                        "kind": resource_kind,
                        "count": sum(
                            resource["kind"] == resource_kind for resource in selected
                        ),
                    }
                    for resource_kind in RESOURCE_KINDS
                ],
            }

    def detail(self, resource_id: str, version: str) -> dict[str, Any]:
        with self._lock:
            resource = self._by_reference.get((resource_id, version))
            if resource is None:
                raise ResourceCatalogError(
                    "resource_not_found",
                    "resource version is not registered in this catalog",
                )
            return deepcopy(resource)

    def by_reference(self, reference: str) -> dict[str, Any]:
        if not isinstance(reference, str) or "@" not in reference:
            raise ResourceCatalogError(
                "resource_not_found",
                "resource version is not registered in this catalog",
            )
        resource_id, version = reference.rsplit("@", 1)
        return self.detail(resource_id, version)

    def factory_snapshot(self) -> list[dict[str, Any]]:
        """Return the bounded descriptors Factory may send to a model."""
        snapshot = []
        with self._lock:
            resources = self._resources
        for resource in resources:
            if not resource["factory_selectable"]:
                continue
            spec = deepcopy(resource["spec"])
            if isinstance(spec, dict):
                spec.pop("ui", None)
            item = {
                "reference": resource["reference"],
                "kind": resource["kind"],
                "name": resource["name"],
                "description": resource["description"],
                "availability": resource["availability"],
                "runtime_status": resource["runtime_status"],
                "required_permissions": deepcopy(resource["required_permissions"]),
                "spec": spec,
            }
            if resource.get("component_class"):
                item["component_class"] = resource["component_class"]
            snapshot.append(item)
        return snapshot

    def components(self) -> list[dict[str, Any]]:
        """Project component Resources into the legacy Studio endpoint shape."""
        with self._lock:
            resources = self._resources
        return [
            {
                "type": resource["name"],
                "fields": deepcopy(resource["spec"]["fields"]),
                "output_ports": deepcopy(resource["spec"]["output_ports"]),
                "runtime_status": resource["runtime_status"],
                "component_class": resource.get("component_class", "primitive"),
            }
            for resource in resources
            if resource["kind"] == "component"
            and resource.get("component_class", "primitive") == "primitive"
        ]

    @staticmethod
    def _descriptor(
        resource: dict[str, Any], *, origin: str = "builtin"
    ) -> dict[str, Any]:
        material = deepcopy(resource)
        material["schema_version"] = SCHEMA_VERSION
        material["reference"] = f"{material['resource_id']}@{material['version']}"
        material["origin"] = origin
        hashed = deepcopy(material)
        spec = hashed.get("spec")
        if isinstance(spec, dict):
            spec = dict(spec)
            spec.pop("ui", None)
            hashed["spec"] = spec
        material["content_hash"] = sha256_digest(hashed)
        if material["kind"] == "component":
            material.setdefault("component_class", "primitive")
        return material

    @staticmethod
    def _validate_kind(kind: str | None) -> None:
        if kind is not None and kind not in RESOURCE_KINDS:
            raise ResourceCatalogError(
                "invalid_resource_kind", "kind is not a catalog kind"
            )

    def _validate_availability(self, availability: str | None) -> None:
        if availability is not None and availability not in {
            resource["availability"] for resource in self._resources
        } | {"quarantined", "disabled", "unavailable"}:
            raise ResourceCatalogError(
                "invalid_resource_availability", "availability is not a catalog state"
            )


def _resource_sort_key(resource: dict[str, Any]) -> tuple[int, int, str]:
    kind_index = RESOURCE_KINDS.index(resource["kind"])
    if resource["kind"] == "component":
        try:
            name_index = _COMPONENT_ORDER.index(resource["name"])
        except ValueError:
            name_index = len(_COMPONENT_ORDER)
        return (kind_index, name_index, resource["resource_id"])
    return (kind_index, 0, resource["resource_id"])
