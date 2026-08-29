"""Immutable, server-owned descriptors for local Factory and Studio resources."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Final, Literal

from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import SCHEMA_VERSION

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

_EMPTY_PERMISSIONS: Final[dict[str, Any]] = {
    "network_hosts": [],
    "tools": [],
    "filesystem_read_roots": [],
    "filesystem_write_roots": [],
    "shell_workspace_only": False,
}

_COMPONENTS: Final[tuple[tuple[str, list[str], list[str], RuntimeStatus], ...]] = (
    ("Start", [], ["next"], "supported"),
    ("Agent", ["model_ref", "system_prompt"], ["next"], "runtime_not_configured"),
    ("Tool", ["uses"], ["next"], "runtime_not_supported"),
    ("Condition", ["expression"], ["true", "false"], "supported"),
    ("Transform", ["mapping"], ["next"], "supported"),
    ("HumanApproval", ["prompt"], ["approved", "rejected"], "runtime_not_supported"),
    ("Verifier", ["checks"], ["passed", "failed"], "supported"),
    ("Output", ["output_name"], [], "supported"),
)


class ResourceCatalogError(ValueError):
    """Raised when a requested catalog filter or immutable reference is invalid."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ResourceCatalog:
    """Expose copies of a closed in-code catalog; callers cannot mutate its state."""

    def __init__(self) -> None:
        resources = [self._component(*definition) for definition in _COMPONENTS]
        resources.extend(self._skill_resources())
        resources.extend(self._policy_resources())
        resources.extend(self._template_resources())
        self._resources = tuple(self._descriptor(resource) for resource in resources)
        self._by_reference = {
            (resource["resource_id"], resource["version"]): resource
            for resource in self._resources
        }
        if len(self._by_reference) != len(self._resources):
            raise RuntimeError("resource catalog references must be unique")

    def resources(
        self, *, kind: str | None = None, availability: str | None = None
    ) -> dict[str, Any]:
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
        resource = self._by_reference.get((resource_id, version))
        if resource is None:
            raise ResourceCatalogError(
                "resource_not_found",
                "resource version is not registered in this catalog",
            )
        return deepcopy(resource)

    def components(self) -> list[dict[str, Any]]:
        """Project component Resources into the legacy Studio endpoint shape."""
        return [
            {
                "type": resource["name"],
                "fields": deepcopy(resource["spec"]["fields"]),
                "output_ports": deepcopy(resource["spec"]["output_ports"]),
                "runtime_status": resource["runtime_status"],
            }
            for resource in self._resources
            if resource["kind"] == "component"
        ]

    @staticmethod
    def _descriptor(resource: dict[str, Any]) -> dict[str, Any]:
        material = deepcopy(resource)
        material["schema_version"] = SCHEMA_VERSION
        material["version"] = "1.0.0"
        material["reference"] = f"{material['resource_id']}@{material['version']}"
        material["origin"] = "builtin"
        material["content_hash"] = sha256_digest(material)
        return material

    @staticmethod
    def _component(
        name: str,
        fields: list[str],
        output_ports: list[str],
        runtime_status: RuntimeStatus,
    ) -> dict[str, Any]:
        availability: Availability = (
            "requires_configuration"
            if name == "Agent"
            else "design_only"
            if runtime_status == "runtime_not_supported"
            else "ready"
        )
        return {
            "resource_id": f"veyra.component.{name.lower()}",
            "kind": "component",
            "name": name,
            "description": f"Platform-owned {name} graph component.",
            "availability": availability,
            "factory_selectable": True,
            "runtime_status": runtime_status,
            "required_permissions": deepcopy(_EMPTY_PERMISSIONS),
            "tags": ["graph", "builtin"],
            "spec": {"fields": fields, "output_ports": output_ports},
        }

    @staticmethod
    def _skill_resources() -> list[dict[str, Any]]:
        return [
            {
                "resource_id": "veyra.skill.research-brief",
                "kind": "skill",
                "name": "Research Brief",
                "description": (
                    "Structure a bounded research brief with sources and open "
                    "questions."
                ),
                "availability": "ready",
                "factory_selectable": True,
                "runtime_status": "runtime_not_configured",
                "required_permissions": deepcopy(_EMPTY_PERMISSIONS),
                "tags": ["research", "instruction"],
                "spec": {
                    "instruction": (
                        "State scope, evidence, findings, and open questions."
                    )
                },
            },
            {
                "resource_id": "veyra.skill.document-analyzer",
                "kind": "skill",
                "name": "Document Analyzer",
                "description": (
                    "Extract claims, decisions, risks, and traceable citations "
                    "from documents."
                ),
                "availability": "ready",
                "factory_selectable": True,
                "runtime_status": "runtime_not_configured",
                "required_permissions": deepcopy(_EMPTY_PERMISSIONS),
                "tags": ["document", "instruction"],
                "spec": {
                    "instruction": (
                        "Separate quoted evidence from inference and uncertainty."
                    )
                },
            },
            {
                "resource_id": "veyra.skill.content-planner",
                "kind": "skill",
                "name": "Content Planner",
                "description": (
                    "Plan audience, outline, dependencies, review points, and success "
                    "criteria."
                ),
                "availability": "ready",
                "factory_selectable": True,
                "runtime_status": "runtime_not_configured",
                "required_permissions": deepcopy(_EMPTY_PERMISSIONS),
                "tags": ["planning", "instruction"],
                "spec": {
                    "instruction": "Produce a reviewable plan before drafting content."
                },
            },
        ]

    @staticmethod
    def _policy_resources() -> list[dict[str, Any]]:
        policies = (
            (
                "local-only",
                "Local Only",
                "Keep execution and data handling local.",
                {"network": "deny"},
            ),
            (
                "verification-required",
                "Verification Required",
                "Require verification before completion.",
                {"verification": "required"},
            ),
            (
                "external-write-requires-approval",
                "External Write Requires Approval",
                "Require approval for external writes.",
                {"external_write": "approval_required"},
            ),
        )
        return [
            {
                "resource_id": f"veyra.policy.{slug}",
                "kind": "policy",
                "name": name,
                "description": description,
                "availability": "ready",
                "factory_selectable": True,
                "runtime_status": "supported",
                "required_permissions": deepcopy(_EMPTY_PERMISSIONS),
                "tags": ["policy", "builtin"],
                "spec": spec,
            }
            for slug, name, description, spec in policies
        ]

    @staticmethod
    def _template_resources() -> list[dict[str, Any]]:
        templates = (
            (
                "starter-agent",
                "Starter Agent",
                "A safe local-first starting point for a new Agent.",
            ),
        )
        return [
            {
                "resource_id": f"veyra.template.{slug}",
                "kind": "template",
                "name": name,
                "description": description,
                "availability": "ready",
                "factory_selectable": True,
                "runtime_status": "runtime_not_configured",
                "required_permissions": deepcopy(_EMPTY_PERMISSIONS),
                "tags": ["template", "forkable"],
                "spec": {
                    "component_references": [
                        "veyra.component.start@1.0.0",
                        "veyra.component.agent@1.0.0",
                        "veyra.component.output@1.0.0",
                    ]
                },
            }
            for slug, name, description in templates
        ]

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
