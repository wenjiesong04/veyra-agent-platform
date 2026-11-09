"""Deterministic Project-owned Tool resolution and Agent source mutation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from veyra_agent_platform.contracts.agent import PermissionContract
from veyra_agent_platform.contracts.typed_io import wire_field_compact_type

FILESYSTEM_READ_RESOURCE_ID = "veyra.tool.filesystem.read"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_PATH_INPUT = re.compile(r"(^|_)(path|file|document)(_|$)", re.IGNORECASE)
_EXACT_FILESYSTEM_READ_REFERENCE = re.compile(
    r"veyra\.tool\.filesystem\.read@[0-9]+\.[0-9]+\.[0-9]+",
    re.IGNORECASE,
)
_FILESYSTEM_READ_INTENT = (
    re.compile(r"\bfilesystem[._ -]?read\b", re.IGNORECASE),
    re.compile(r"\bread\s+files?\b", re.IGNORECASE),
    re.compile(
        r"\bread(?:ing)?\b.{0,24}\b(?:project|workspace)\b.{0,12}\bfiles?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bfiles?\b.{0,24}\bread(?:ing)?\b", re.IGNORECASE),
    re.compile(r"(?:读取|读)(?:这个|当前)?(?:项目|工作区)(?:里|内|中的)?(?:的)?文件"),
    re.compile(r"(?:文件读取|读取文件)(?:能力)?"),
)

ResourceMatchStatus = Literal["resolved", "ambiguous", "unbound", "unresolved"]
ResourceReadiness = Literal[
    "ready",
    "requires_configuration",
    "design_only",
    "unavailable",
    "quarantined",
    "unsupported",
    "stale",
]


@dataclass(frozen=True)
class ResourceMatch:
    """A Project-scoped match; global-only resources are never selected."""

    status: ResourceMatchStatus
    selected: dict[str, Any] | None
    candidates: tuple[dict[str, Any], ...]


class ResourceMutationError(ValueError):
    """The requested Tool cannot be added without guessing graph semantics."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def is_resource_binding_intent(instruction: str) -> bool:
    """Return whether this focused adapter owns the user request."""

    return any(pattern.search(instruction) for pattern in _FILESYSTEM_READ_INTENT)


def _explicit_references(
    resources: list[dict[str, Any]], instruction: str
) -> list[dict[str, Any]]:
    folded = instruction.casefold()
    return [
        resource
        for resource in resources
        if str(resource.get("reference") or "").casefold() in folded
    ]


def _filesystem_read_resources(
    resources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        resource
        for resource in resources
        if resource.get("kind") == "tool"
        and resource.get("resource_id") == FILESYSTEM_READ_RESOURCE_ID
    ]


def resolve_project_resource(
    project_resources: list[dict[str, Any]],
    catalog_resources: list[dict[str, Any]],
    instruction: str,
) -> ResourceMatch:
    """Resolve only an exact Project-owned filesystem.read resource.

    A full reference can narrow multiple Project-bound versions. Natural-language
    capability aliases intentionally select every bound filesystem.read version,
    forcing clarification when more than one is available.
    """

    project_owned = [
        resource for resource in project_resources if resource.get("scope") == "project"
    ]
    mentioned_references = {
        item.casefold()
        for item in _EXACT_FILESYSTEM_READ_REFERENCE.findall(instruction)
    }
    explicit = _explicit_references(project_owned, instruction)
    if mentioned_references:
        if len(mentioned_references) == 1 and len(explicit) == 1:
            return ResourceMatch("resolved", explicit[0], (explicit[0],))
        known = tuple(
            resource
            for resource in [*project_owned, *catalog_resources]
            if str(resource.get("reference") or "").casefold() in mentioned_references
        )
        return ResourceMatch(
            "ambiguous" if len(mentioned_references) > 1 else "unbound",
            None,
            known,
        )
    if len(explicit) == 1:
        selected = explicit[0]
        if selected.get("resource_id") != FILESYSTEM_READ_RESOURCE_ID:
            return ResourceMatch("unresolved", None, ())
        return ResourceMatch("resolved", selected, (selected,))
    if len(explicit) > 1:
        return ResourceMatch("ambiguous", None, tuple(explicit))

    if not is_resource_binding_intent(instruction):
        return ResourceMatch("unresolved", None, ())
    candidates = tuple(_filesystem_read_resources(project_owned))
    if len(candidates) == 1:
        return ResourceMatch("resolved", candidates[0], candidates)
    if candidates:
        return ResourceMatch("ambiguous", None, candidates)

    globally_known = _filesystem_read_resources(catalog_resources)
    return ResourceMatch(
        "unbound" if globally_known else "unresolved",
        None,
        tuple(globally_known),
    )


_IDENTITY_NOISE = re.compile(r"[^a-z0-9]+")


def _normalized_identity(value: object) -> str:
    return _IDENTITY_NOISE.sub(" ", str(value or "").casefold()).strip()


def _resource_identity_keys(resource: dict[str, Any]) -> set[str]:
    reference = str(resource.get("reference") or "")
    resource_id = str(resource.get("resource_id") or "")
    keys = {
        _normalized_identity(resource.get("name")),
        _normalized_identity(resource_id),
        _normalized_identity(reference),
        _normalized_identity(reference.split("@", 1)[0]),
    }
    parts = [part for part in resource_id.split(".") if part]
    if len(parts) >= 2:
        keys.add(_normalized_identity(" ".join(parts[-2:])))
    return {key for key in keys if len(key) >= 4}


def _unique_by_reference(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for resource in resources:
        reference = str(resource.get("reference") or "")
        if not reference or reference in seen:
            continue
        seen.add(reference)
        unique.append(resource)
    return unique


def _prefer_ready(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ready = [
        resource
        for resource in matches
        if resource_readiness(resource)["readiness"] == "ready"
    ]
    return ready or matches


def project_capability_catalog(
    project_resources: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Provider-safe Project capability names. No hashes, pins, or versions."""

    catalog: list[dict[str, str]] = []
    seen: set[str] = set()
    for resource in project_resources:
        if resource.get("scope") != "project":
            continue
        if resource.get("kind") not in {"tool", "mcp_tool"} and not (
            resource.get("kind") == "component"
            and resource.get("component_class") == "composite"
        ):
            continue
        resource_id = str(resource.get("resource_id") or "")
        if not resource_id or resource_id in seen:
            continue
        seen.add(resource_id)
        catalog.append(
            {
                "name": str(resource.get("name") or resource_id),
                "resource_id": resource_id,
                "kind": str(resource.get("kind") or "tool"),
                "readiness": str(resource_readiness(resource)["readiness"]),
            }
        )
    return catalog


def resolve_capability_intent(
    project_resources: list[dict[str, Any]],
    catalog_resources: list[dict[str, Any]],
    instruction: str,
) -> ResourceMatch:
    """Resolve a capability step against Project-bound tools only.

    Reuses the filesystem.read resolver first. Other Project-bound tools are
    selected only on a unique name, resource_id, or exact reference match.
    Catalog-only resources are never auto-installed.
    """

    match = resolve_project_resource(project_resources, catalog_resources, instruction)
    if match.status != "unresolved":
        return match
    project_owned = [
        resource
        for resource in project_resources
        if resource.get("scope") == "project"
        and resource.get("binding_status") != "stale"
        and (
            resource.get("kind") in {"tool", "mcp_tool"}
            or (
                resource.get("kind") == "component"
                and resource.get("component_class") == "composite"
            )
        )
    ]
    folded = instruction.casefold()
    identity = _normalized_identity(instruction)
    exact_reference = [
        resource
        for resource in project_owned
        if str(resource.get("reference") or "").casefold() == folded
    ]
    if len(exact_reference) == 1:
        return ResourceMatch("resolved", exact_reference[0], (exact_reference[0],))
    exact_id = [
        resource
        for resource in project_owned
        if str(resource.get("resource_id") or "").casefold() == folded
    ]
    if len(exact_id) == 1:
        return ResourceMatch("resolved", exact_id[0], (exact_id[0],))
    exact_name = [
        resource
        for resource in project_owned
        if str(resource.get("name") or "").casefold() == folded
    ]
    if len(exact_name) == 1:
        return ResourceMatch("resolved", exact_name[0], (exact_name[0],))
    identical = [
        resource
        for resource in project_owned
        if identity and identity in _resource_identity_keys(resource)
    ]
    identical = _unique_by_reference(identical)
    if len(identical) == 1:
        return ResourceMatch("resolved", identical[0], (identical[0],))
    if len(identical) > 1:
        return ResourceMatch("ambiguous", None, tuple(identical))
    named = [
        resource
        for resource in project_owned
        if any(
            len(key) >= 8 and key in identity
            for key in _resource_identity_keys(resource)
        )
        or str(resource.get("name") or "").casefold() in folded
        or str(resource.get("resource_id") or "").casefold() in folded
    ]
    named = _unique_by_reference(named)
    if len(named) == 1:
        return ResourceMatch("resolved", named[0], (named[0],))
    if len(named) > 1:
        return ResourceMatch("ambiguous", None, tuple(named))
    catalog_known = [
        resource
        for resource in catalog_resources
        if resource.get("kind") in {"tool", "mcp_tool"}
    ]
    return ResourceMatch(
        "unbound" if catalog_known else "unresolved",
        None,
        tuple(catalog_known[:8]),
    )


def resource_readiness(resource: dict[str, Any]) -> dict[str, Any]:
    """Expose Project pin, live readiness and minimum permissions for review."""

    availability = str(resource.get("availability") or "unavailable")
    runtime_status = str(resource.get("runtime_status") or "runtime_not_supported")
    if resource.get("binding_status") == "stale":
        readiness: ResourceReadiness = "stale"
    elif availability == "quarantined":
        readiness = "quarantined"
    elif availability == "requires_configuration":
        readiness = "requires_configuration"
    elif availability == "design_only":
        readiness = "design_only"
    elif availability == "unavailable" and runtime_status == "runtime_not_supported":
        readiness = "unsupported"
    elif availability != "ready" or runtime_status != "supported":
        readiness = "unavailable"
    else:
        readiness = "ready"
    return {
        "reference": str(resource["reference"]),
        "name": str(resource["name"]),
        "bound_content_hash": str(resource["bound_content_hash"]),
        "catalog_content_hash": str(resource["content_hash"]),
        "binding_status": str(resource["binding_status"]),
        "readiness": readiness,
        "availability": availability,
        "runtime_status": runtime_status,
        "required_permissions": resource["required_permissions"],
        "blocking_reasons": resource.get("blocking_reasons", []),
        "project_resource_changed": False,
        "automatic_upgrade": False,
    }


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def grant_required_permissions(
    current: dict[str, Any], required: dict[str, Any]
) -> dict[str, Any]:
    """Merge exactly the descriptor's required permissions into the Agent grant."""

    return PermissionContract.from_dict(
        {
            "network_hosts": _unique(
                [*current.get("network_hosts", []), *required["network_hosts"]]
            ),
            "tools": _unique([*current.get("tools", []), *required["tools"]]),
            "filesystem_read_roots": _unique(
                [
                    *current.get("filesystem_read_roots", []),
                    *required["filesystem_read_roots"],
                ]
            ),
            "filesystem_write_roots": _unique(
                [
                    *current.get("filesystem_write_roots", []),
                    *required["filesystem_write_roots"],
                ]
            ),
            "shell_workspace_only": bool(current.get("shell_workspace_only"))
            or bool(required["shell_workspace_only"]),
        }
    ).to_dict()


def _new_node_id(source: dict[str, Any]) -> str:
    existing = {str(node["id"]) for node in source["nodes"]}
    base = "filesystem_read"
    if base not in existing:
        return base
    index = 2
    while f"{base}_{index}" in existing:
        index += 1
    return f"{base}_{index}"


def _path_input(source: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    inputs = dict(source["inputs"])
    selected = next(
        (
            name
            for name, value_type in inputs.items()
            if wire_field_compact_type(value_type) == "string"
            and _PATH_INPUT.search(name)
        ),
        None,
    )
    if selected is None:
        selected = "path"
        if selected in inputs and wire_field_compact_type(inputs[selected]) != "string":
            raise ResourceMutationError(
                "resource_input_conflict",
                "The Agent already has a non-text path input; review it in Studio.",
            )
        inputs[selected] = "string"
    return selected, inputs


def bind_project_tool(
    source: dict[str, Any], resource: dict[str, Any]
) -> dict[str, Any]:
    """Build an Agent candidate using the Project pin, never the Catalog hash."""

    reference = str(resource["reference"])
    bound_hash = resource.get("bound_content_hash")
    if (
        resource.get("scope") != "project"
        or resource.get("resource_id") != FILESYSTEM_READ_RESOURCE_ID
        or resource.get("kind") != "tool"
        or not isinstance(bound_hash, str)
        or _HASH.fullmatch(bound_hash) is None
    ):
        raise ResourceMutationError(
            "resource_not_project_bound",
            "filesystem.read must already be bound to this Project.",
        )
    if any(node.get("uses") == reference for node in source["nodes"]):
        raise ResourceMutationError(
            "resource_already_bound",
            "This filesystem.read version is already used by the Agent.",
        )

    start = next(
        (node for node in source["nodes"] if node.get("component_type") == "Start"),
        None,
    )
    outgoing = [
        transition
        for transition in source["transitions"]
        if start is not None
        and transition.get("from") == start["id"]
        and transition.get("port") == "next"
    ]
    if start is None or len(outgoing) != 1:
        raise ResourceMutationError(
            "resource_flow_ambiguous",
            "The Agent has no unique Start edge; place the Tool in Studio.",
        )

    node_id = _new_node_id(source)
    path_input, inputs = _path_input(source)
    edge = outgoing[0]
    nodes = [
        *source["nodes"],
        {
            "id": node_id,
            "component_type": "Tool",
            "uses": reference,
            "input_mapping": {"path": path_input},
        },
    ]
    transitions = [
        (
            {"from": edge["from"], "port": edge["port"], "to": node_id}
            if transition is edge
            else transition
        )
        for transition in source["transitions"]
    ]
    transitions.append({"from": node_id, "port": "next", "to": edge["to"]})

    positions = dict(source["ui"]["positions"])
    before = positions.get(str(start["id"]), {"x": 0, "y": 0})
    after = positions.get(str(edge["to"]), {"x": before["x"] + 240, "y": before["y"]})
    positions[node_id] = {
        "x": round((int(before["x"]) + int(after["x"])) / 2),
        "y": round((int(before["y"]) + int(after["y"])) / 2),
    }
    current_permissions = source["extensions"]["veyra"]["permissions"]
    permissions = grant_required_permissions(
        current_permissions, resource["required_permissions"]
    )
    return {
        **source,
        "inputs": inputs,
        "nodes": nodes,
        "transitions": transitions,
        "extensions": {
            **source["extensions"],
            "veyra": {
                **source["extensions"]["veyra"],
                "permissions": permissions,
            },
        },
        "ui": {**source["ui"], "positions": positions},
        "lock": {**source["lock"], reference: bound_hash},
    }
