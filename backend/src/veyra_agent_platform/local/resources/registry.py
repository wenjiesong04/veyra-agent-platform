"""Filesystem-backed node packages for the local Resource Catalog.

Each platform capability lives in `resources/nodes/<family>/<id>/node.yaml`.
That file is the only authored source; the catalog is a validated projection.
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml  # type: ignore[import-untyped]

from veyra_agent_platform.contracts.agent import ComponentType
from veyra_agent_platform.contracts.resource import ComponentClass

_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_RESOURCE_ID = re.compile(r"^veyra\.[a-z][a-z0-9_.-]*$")
_REQUIRED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "resource_id",
        "kind",
        "name",
        "description",
        "availability",
        "factory_selectable",
        "runtime_status",
        "required_permissions",
        "tags",
        "spec",
        "version",
    }
)
_PERMISSION_KEYS: Final[frozenset[str]] = frozenset(
    {
        "network_hosts",
        "tools",
        "filesystem_read_roots",
        "filesystem_write_roots",
        "shell_workspace_only",
    }
)
_KINDS: Final[frozenset[str]] = frozenset(
    {"component", "tool", "mcp_tool", "skill", "policy", "template"}
)
_AVAILABILITY: Final[frozenset[str]] = frozenset(
    {
        "ready",
        "requires_configuration",
        "design_only",
        "quarantined",
        "disabled",
        "unavailable",
    }
)
_RUNTIME_STATUS: Final[frozenset[str]] = frozenset(
    {"supported", "runtime_not_configured", "runtime_not_supported"}
)
_FAMILY_KINDS: Final[dict[str, str]] = {
    "core": "component",
    "composites": "component",
    "filesystem": "tool",
    "git": "tool",
    "shell": "tool",
    "web": "tool",
    "entity": "tool",
    "mcp": "mcp_tool",
    "skills": "skill",
    "policies": "policy",
    "templates": "template",
}
_OPTIONAL_KEYS: Final[frozenset[str]] = frozenset(
    {"component_class", "capabilities", "loop_compatible"}
)
_CAPABILITY_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_OVERLAY_FAMILIES: Final[frozenset[str]] = frozenset({"workshop", "discovered"})
_COMPONENT_NAMES: Final[frozenset[str]] = frozenset(
    item.value for item in ComponentType
)
_UI_KEYS: Final[frozenset[str]] = frozenset({"category", "icon", "title"})


class NodePackageError(RuntimeError):
    """A platform node.yaml package could not be loaded."""


@dataclass(frozen=True)
class NodePackage:
    path: Path
    family: str
    package_id: str
    definition: dict[str, Any]


def default_nodes_root() -> Path:
    return Path(__file__).resolve().parents[5] / "resources" / "nodes"


def load_node_packages(root: Path | None = None) -> tuple[NodePackage, ...]:
    """Load every `node.yaml` package under the platform node root."""
    nodes_root = root or default_nodes_root()
    if not nodes_root.is_dir():
        raise NodePackageError(f"node package root is missing: {nodes_root}")
    paths = sorted(nodes_root.glob("*/*/node.yaml"))
    if not paths:
        raise NodePackageError(f"no node.yaml packages found under {nodes_root}")
    packages = tuple(_load_package(nodes_root, path) for path in paths)
    _check_unique(packages)
    _check_components(packages)
    return packages


def load_overlay_packages(root: Path | None) -> tuple[NodePackage, ...]:
    """Load quarantined workshop drafts and discovered MCP tools from app data."""
    if root is None or not root.is_dir():
        return ()
    paths = sorted(root.glob("*/*/node.yaml"))
    packages = tuple(_load_overlay_package(root, path) for path in paths)
    _check_unique(packages)
    return packages


def node_definition(
    resource_id: str, version: str, root: Path | None = None
) -> dict[str, Any]:
    for package in load_node_packages(root):
        definition = package.definition
        if (
            definition["resource_id"] == resource_id
            and definition["version"] == version
        ):
            return deepcopy(definition)
    raise NodePackageError(f"unknown node package {resource_id}@{version}")


def _load_package(root: Path, path: Path) -> NodePackage:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise NodePackageError(f"node package is outside {root}: {path}") from exc
    if len(relative.parts) != 3 or relative.name != "node.yaml":
        raise NodePackageError(f"{path}: node packages must be family/id/node.yaml")
    family, package_id, _name = relative.parts
    if family not in _FAMILY_KINDS:
        raise NodePackageError(f"{path}: unknown node family {family}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise NodePackageError(f"{path}: node.yaml could not be read") from exc
    definition = _validated(path, payload, family, overlay=False)
    return NodePackage(
        path=path,
        family=family,
        package_id=package_id,
        definition=definition,
    )


def _load_overlay_package(root: Path, path: Path) -> NodePackage:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise NodePackageError(f"overlay package is outside {root}: {path}") from exc
    if len(relative.parts) != 3 or relative.name != "node.yaml":
        raise NodePackageError(f"{path}: overlay packages must be family/id/node.yaml")
    family, package_id, _name = relative.parts
    if family not in _OVERLAY_FAMILIES:
        raise NodePackageError(f"{path}: unknown overlay family {family}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise NodePackageError(f"{path}: node.yaml could not be read") from exc
    definition = _validated(path, payload, family, overlay=True)
    return NodePackage(
        path=path,
        family=family,
        package_id=package_id,
        definition=definition,
    )


def _validated(
    path: Path, payload: object, family: str, *, overlay: bool = False
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NodePackageError(f"{path}: node.yaml must be a mapping")
    extra = set(payload) - _REQUIRED_KEYS - _OPTIONAL_KEYS
    missing = _REQUIRED_KEYS - set(payload)
    if extra or missing:
        detail = ", ".join(sorted(extra or missing))
        kind = "unsupported fields" if extra else "missing fields"
        raise NodePackageError(f"{path}: {kind}: {detail}")
    resource_id = _text(path, "resource_id", payload["resource_id"])
    if _RESOURCE_ID.fullmatch(resource_id) is None:
        raise NodePackageError(f"{path}: resource_id is not a veyra identifier")
    version = _text(path, "version", payload["version"])
    if _VERSION.fullmatch(version) is None:
        raise NodePackageError(f"{path}: version must be numeric dotted")
    kind = _text(path, "kind", payload["kind"])
    if kind not in _KINDS:
        raise NodePackageError(f"{path}: kind is not a catalog kind")
    if overlay:
        if kind == "component":
            raise NodePackageError(
                f"{path}: overlay packages cannot declare graph components"
            )
        if family == "discovered" and kind != "tool":
            raise NodePackageError(f"{path}: discovered overlays must be tools")
    else:
        expected_kind = _FAMILY_KINDS[family]
        if kind != expected_kind:
            raise NodePackageError(
                f"{path}: family {family} must declare kind {expected_kind}"
            )
    name = _text(path, "name", payload["name"])
    component_class = _component_class(path, payload, kind, family, name)
    availability = _text(path, "availability", payload["availability"])
    runtime_status = _text(path, "runtime_status", payload["runtime_status"])
    if availability not in _AVAILABILITY:
        raise NodePackageError(f"{path}: availability is not a catalog state")
    if runtime_status not in _RUNTIME_STATUS:
        raise NodePackageError(f"{path}: runtime_status is not a catalog state")
    if not isinstance(payload["factory_selectable"], bool):
        raise NodePackageError(f"{path}: factory_selectable must be a boolean")
    spec = payload["spec"]
    if not isinstance(spec, dict):
        raise NodePackageError(f"{path}: spec must be a mapping")
    _permissions(path, payload["required_permissions"])
    tags = payload["tags"]
    if not isinstance(tags, list) or not all(
        isinstance(tag, str) and tag for tag in tags
    ):
        raise NodePackageError(f"{path}: tags must be a list of strings")
    _ui(path, spec)
    if kind == "component" and component_class is ComponentClass.PRIMITIVE:
        fields = spec.get("fields")
        ports = spec.get("output_ports")
        if not isinstance(fields, list) or not all(
            isinstance(item, str) for item in fields
        ):
            raise NodePackageError(f"{path}: component spec.fields must be strings")
        if not isinstance(ports, list) or not all(
            isinstance(item, str) and item for item in ports
        ):
            raise NodePackageError(
                f"{path}: component spec.output_ports must be strings"
            )
    if kind == "component" and component_class is ComponentClass.COMPOSITE:
        primitives = spec.get("primitive_refs")
        if not isinstance(primitives, list) or not primitives:
            raise NodePackageError(
                f"{path}: composite spec.primitive_refs must list primitive components"
            )
    result = {
        "resource_id": resource_id,
        "kind": kind,
        "name": name,
        "description": _text(path, "description", payload["description"]),
        "availability": availability,
        "factory_selectable": payload["factory_selectable"],
        "runtime_status": runtime_status,
        "required_permissions": deepcopy(payload["required_permissions"]),
        "tags": list(tags),
        "spec": deepcopy(spec),
        "version": version,
        "capabilities": _capabilities(path, payload.get("capabilities")),
        "loop_compatible": _loop_compatible(path, payload, kind),
    }
    if component_class is not None and "component_class" in payload:
        result["component_class"] = component_class.value
    return result


def _permissions(path: Path, value: object) -> None:
    if not isinstance(value, dict) or set(value) != _PERMISSION_KEYS:
        raise NodePackageError(f"{path}: required_permissions keys are invalid")
    for key in _PERMISSION_KEYS - {"shell_workspace_only"}:
        items = value[key]
        if not isinstance(items, list) or not all(
            isinstance(item, str) and item for item in items
        ):
            raise NodePackageError(f"{path}: {key} must be a list of strings")
    if not isinstance(value["shell_workspace_only"], bool):
        raise NodePackageError(f"{path}: shell_workspace_only must be a boolean")


def _ui(path: Path, spec: dict[str, Any]) -> None:
    ui = spec.get("ui")
    if ui is None:
        return
    if not isinstance(ui, dict) or set(ui) != _UI_KEYS:
        raise NodePackageError(f"{path}: spec.ui must declare category, icon, title")
    if not all(isinstance(ui[key], str) and ui[key] for key in _UI_KEYS):
        raise NodePackageError(f"{path}: spec.ui values must be non-empty strings")


def _check_unique(packages: tuple[NodePackage, ...]) -> None:
    seen: set[tuple[str, str]] = set()
    for package in packages:
        key = (package.definition["resource_id"], package.definition["version"])
        if key in seen:
            raise NodePackageError(f"{package.path}: duplicate node {key[0]}@{key[1]}")
        seen.add(key)


def _check_components(packages: tuple[NodePackage, ...]) -> None:
    names = {
        package.definition["name"]
        for package in packages
        if package.definition["kind"] == "component"
        and package.definition.get("component_class", "primitive")
        == ComponentClass.PRIMITIVE.value
    }
    if names != _COMPONENT_NAMES:
        raise NodePackageError(
            "primitive component packages must declare each V1 graph type exactly once"
        )


def _component_class(
    path: Path, payload: dict[str, Any], kind: str, family: str, name: str
) -> ComponentClass | None:
    raw = payload.get("component_class")
    if kind != "component":
        if raw is not None:
            raise NodePackageError(
                f"{path}: component_class is only valid on components"
            )
        return None
    if raw is None:
        # Core V1 packages predate this classification. Preserve their hash material.
        if family == "core" and name in _COMPONENT_NAMES - {"Model", "AgentCall"}:
            raw = ComponentClass.PRIMITIVE.value
        else:
            raise NodePackageError(
                f"{path}: component packages must declare component_class"
            )
    try:
        component_class = ComponentClass(raw)
    except ValueError as exc:
        raise NodePackageError(
            f"{path}: component_class must be primitive or composite"
        ) from exc
    if component_class is ComponentClass.PRIMITIVE:
        if family != "core":
            raise NodePackageError(
                f"{path}: primitive components must live in the core family"
            )
        if name not in _COMPONENT_NAMES:
            raise NodePackageError(f"{path}: primitive name is not a V1 graph type")
    if component_class is ComponentClass.COMPOSITE:
        if family != "composites":
            raise NodePackageError(
                f"{path}: composite components must live in the composites family"
            )
        if name in _COMPONENT_NAMES:
            raise NodePackageError(
                f"{path}: composite components cannot reuse a primitive graph type name"
            )
    return component_class


def _capabilities(path: Path, value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(
        isinstance(item, str) and _CAPABILITY_NAME.fullmatch(item) for item in value
    ):
        raise NodePackageError(f"{path}: capabilities must be snake_case strings")
    return list(dict.fromkeys(value))


def _loop_compatible(path: Path, payload: dict[str, Any], kind: str) -> bool:
    raw = payload.get("loop_compatible")
    if raw is None:
        return kind != "template"
    if not isinstance(raw, bool):
        raise NodePackageError(f"{path}: loop_compatible must be a boolean")
    return raw


def _text(path: Path, field: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NodePackageError(f"{path}: {field} must be a non-empty string")
    return value
