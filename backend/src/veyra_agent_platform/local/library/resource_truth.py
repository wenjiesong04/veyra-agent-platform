"""Catalog + Project pin + Agent lock as one authorization chain.

Catalog presence is not enough. A loop Agent may use a resource only when the
Project pins the same version/hash the Agent lock records. Apply pins the
Proposal snapshot; Runtime never silently upgrades or invents a pin.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceCatalogError
from veyra_agent_platform.local.resources.project import ProjectResourceService

BindStatus = Literal[
    "already_bound",
    "will_bind",
    "requires_configuration",
    "unavailable",
]

PINNABLE_KINDS = frozenset({"tool", "mcp_tool", "skill"})
_RUNTIME_PROFILE_PREFIX = "veyra.runtime.profile@"
_HOST_CONFIG_ADAPTERS = frozenset(
    {
        "veyra.runtime.http.request",
        "veyra.runtime.browser.navigate",
    }
)
_BLOCKED_AVAILABILITY = frozenset({"unavailable", "disabled", "quarantined"})


def project_pin(
    project_resources: Sequence[Mapping[str, Any]], resource_id: str
) -> dict[str, Any] | None:
    """Return the unique Project pin for a catalog resource_id, if any."""

    matches = [
        dict(item)
        for item in project_resources
        if item.get("scope") == "project"
        and item.get("resource_id") == resource_id
        and isinstance(item.get("reference"), str)
    ]
    if not matches:
        return None
    return matches[0]


def project_pin_by_reference(
    project_resources: Sequence[Mapping[str, Any]], reference: str
) -> dict[str, Any] | None:
    for item in project_resources:
        if item.get("scope") == "project" and item.get("reference") == reference:
            return dict(item)
    return None


def pin_hash(resource: Mapping[str, Any]) -> str | None:
    digest = resource.get("bound_content_hash") or resource.get("content_hash")
    return str(digest) if isinstance(digest, str) and digest else None


def catalog_tool(catalog: ResourceCatalog, resource_id: str) -> dict[str, Any] | None:
    try:
        matches = [
            item
            for item in catalog.resources(kind="tool")["resources"]
            if item.get("resource_id") == resource_id
            and item.get("factory_selectable") is True
        ]
    except ResourceCatalogError:
        return None
    return dict(matches[0]) if matches else None


def resolve_loop_tool(
    catalog: ResourceCatalog,
    project_resources: Sequence[Mapping[str, Any]],
    resource_id: str,
) -> dict[str, Any] | None:
    """Prefer an existing Project pin over the latest catalog version."""

    pinned = [
        dict(item)
        for item in project_resources
        if item.get("scope") == "project"
        and item.get("resource_id") == resource_id
        and isinstance(item.get("reference"), str)
    ]
    selected = catalog_tool(catalog, resource_id)
    chosen: Mapping[str, Any] | None = None
    if pinned:
        if selected is not None:
            chosen = next(
                (
                    item
                    for item in pinned
                    if item.get("reference") == selected.get("reference")
                ),
                pinned[0],
            )
        else:
            chosen = pinned[0]
    elif selected is not None:
        chosen = selected
    if chosen is None:
        return None
    try:
        resource = dict(catalog.by_reference(str(chosen["reference"])))
    except ResourceCatalogError:
        return None
    digest = pin_hash(chosen) if pinned else str(resource["content_hash"])
    resource["lock_hash"] = digest or str(resource["content_hash"])
    resource["project_pinned"] = bool(pinned)
    return resource


def needs_host_configuration(resource: Mapping[str, Any]) -> bool:
    spec = resource.get("spec")
    adapter = spec.get("adapter") if isinstance(spec, Mapping) else None
    required = resource.get("required_permissions") or {}
    hosts = required.get("network_hosts") if isinstance(required, Mapping) else None
    return adapter in _HOST_CONFIG_ADAPTERS and not hosts


def bind_status_for(
    resource: Mapping[str, Any],
    *,
    project_resources: Sequence[Mapping[str, Any]],
) -> BindStatus:
    availability = str(resource.get("availability") or "")
    if availability in _BLOCKED_AVAILABILITY:
        return "unavailable"
    pinned = project_pin_by_reference(
        project_resources, str(resource.get("reference") or "")
    )
    if pinned is not None:
        if needs_host_configuration(resource):
            return "requires_configuration"
        if availability == "requires_configuration":
            return "requires_configuration"
        return "already_bound"
    if needs_host_configuration(resource) or availability == "requires_configuration":
        return "requires_configuration"
    if availability != "ready":
        return "unavailable"
    return "will_bind"


def annotate_resource_plan(
    plan: Sequence[Mapping[str, Any]],
    *,
    catalog: ResourceCatalog,
    project_resources: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Add Proposal-visible bind_status without changing run_availability inputs."""

    annotated: list[dict[str, Any]] = []
    for raw in plan:
        item = dict(raw)
        reference = str(item.get("reference") or "")
        kind = str(item.get("kind") or "")
        if kind in PINNABLE_KINDS and reference:
            try:
                resource = catalog.by_reference(reference)
            except ResourceCatalogError:
                item["bind_status"] = "unavailable"
                annotated.append(item)
                continue
            item["name"] = str(resource.get("name") or item.get("name") or reference)
            item["bind_status"] = bind_status_for(
                resource, project_resources=project_resources
            )
        annotated.append(item)
    return annotated


def catalog_lock_pins(
    source: AgentSource, catalog: ResourceCatalog
) -> list[dict[str, str]]:
    """Immutable Catalog pins an Apply must write, using the Proposal lock hashes."""

    pins: list[dict[str, str]] = []
    for reference, digest in source.lock.items():
        if reference.startswith(_RUNTIME_PROFILE_PREFIX):
            continue
        try:
            resource = catalog.by_reference(reference)
        except ResourceCatalogError:
            continue
        if resource["kind"] not in PINNABLE_KINDS:
            continue
        pins.append(
            {
                "reference": reference,
                "content_hash": digest,
                "kind": str(resource["kind"]),
            }
        )
    return pins


def pin_catalog_locks(
    project_resources: ProjectResourceService,
    catalog: ResourceCatalog,
    project_id: str,
    source: AgentSource,
) -> None:
    """Pin Proposal lock hashes. Never substitute a newer catalog version."""

    for item in catalog_lock_pins(source, catalog):
        project_resources.add(
            project_id,
            item["reference"],
            source="factory",
            content_hash=item["content_hash"],
        )


def reuse_project_skills(
    project_resources: Sequence[Mapping[str, Any]],
    catalog: ResourceCatalog,
    requirement: str,
) -> list[dict[str, Any]]:
    """Legacy name-matching Skill reuse. New create_agent must not call this."""

    folded = requirement.casefold()
    if not folded:
        return []
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in project_resources:
        if item.get("kind") != "skill" or item.get("scope") != "project":
            continue
        reference = str(item.get("reference") or "")
        if not reference or reference in seen:
            continue
        name = str(item.get("name") or "").casefold()
        resource_id = str(item.get("resource_id") or "")
        token = resource_id.rsplit(".", 1)[-1].replace("-", " ").casefold()
        if not ((name and name in folded) or (token and token in folded)):
            continue
        try:
            resource = dict(catalog.by_reference(reference))
        except ResourceCatalogError:
            continue
        resource["lock_hash"] = pin_hash(item) or str(resource["content_hash"])
        resource["project_pinned"] = True
        seen.add(reference)
        selected.append(resource)
    return selected
