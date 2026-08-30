"""Quarantined Resource Drafts outside Project directories and Catalog builtins."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from veyra_agent_platform.contracts.common import new_uuid7

from .catalog import ResourceCatalog, ResourceCatalogError
from .registry import NodePackageError

_RESOURCE_ID = re.compile(r"^veyra\.[a-z][a-z0-9_.-]*$")
_KIND_SLUG = {
    "tool": "tool",
    "skill": "skill",
    "policy": "policy",
    "mcp_tool": "mcp",
    "template": "template",
}
_SLUG = re.compile(r"[^a-z0-9]+")
_ALLOWED_KINDS = frozenset(_KIND_SLUG)


class ResourceWorkshopError(ValueError):
    """A typed Resource Workshop failure safe to return on the local API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ResourceWorkshop:
    """Write declarative drafts into application-data quarantine; never execute them."""

    def __init__(self, overlay_root: Path, catalog: ResourceCatalog) -> None:
        self.overlay_root = overlay_root
        self.catalog = catalog

    def create_draft(
        self,
        *,
        confirm: bool,
        kind: str,
        requested_reference: str,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        if not confirm:
            raise ResourceWorkshopError(
                "workshop_confirmation_required",
                "Explicit confirmation is required to create a quarantined "
                "Resource Draft",
            )
        if kind not in _ALLOWED_KINDS:
            raise ResourceWorkshopError(
                "workshop_kind_invalid",
                "Resource Drafts must be a Tool, Skill, Policy, MCP tool, or Template",
            )
        if not isinstance(requested_reference, str) or "@" not in requested_reference:
            raise ResourceWorkshopError(
                "workshop_reference_invalid",
                "requested_reference must be a versioned catalog reference",
            )
        draft_id = new_uuid7()
        resource_id = _workshop_resource_id(kind, requested_reference, draft_id)
        title = (name or requested_reference.rsplit("@", 1)[0]).strip() or resource_id
        detail = (
            description
            or f"Quarantined proposal for {requested_reference}. Not executable."
        ).strip()
        package_id = draft_id.replace("-", "")
        payload = {
            "resource_id": resource_id,
            "kind": kind,
            "name": title[:120],
            "description": detail[:4_000],
            "availability": "quarantined",
            "factory_selectable": False,
            "runtime_status": "runtime_not_supported",
            "required_permissions": {
                "network_hosts": [],
                "tools": [],
                "filesystem_read_roots": [],
                "filesystem_write_roots": [],
                "shell_workspace_only": False,
            },
            "tags": ["workshop", "quarantined"],
            "spec": {
                "executable": False,
                "requested_reference": requested_reference,
                "ui": {
                    "category": "workshop",
                    "icon": "box",
                    "title": title[:80],
                },
            },
            "version": "0.0.1",
        }
        target = self.overlay_root / "workshop" / package_id / "node.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        try:
            self.catalog.reload_overlays()
            resource = self.catalog.detail(resource_id, "0.0.1")
        except (NodePackageError, ResourceCatalogError) as exc:
            target.unlink(missing_ok=True)
            raise ResourceWorkshopError(
                "workshop_draft_invalid",
                "Resource Draft could not be loaded into the overlay catalog",
            ) from exc
        return {
            "schema_version": "1.0",
            "draft_id": draft_id,
            "executable": False,
            "resource": resource,
        }


def _workshop_resource_id(kind: str, requested_reference: str, draft_id: str) -> str:
    identity, _, _version = requested_reference.partition("@")
    slug_source = identity.removeprefix("veyra.")
    slug = _SLUG.sub("-", slug_source.lower()).strip("-") or "draft"
    kind_slug = _KIND_SLUG[kind]
    suffix = draft_id.replace("-", "")[:8]
    return f"veyra.workshop.{kind_slug}.{slug}-{suffix}"
