"""Quarantined Resource Drafts outside Project directories and Catalog builtins."""

from __future__ import annotations

import os
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
        instruction: str | None = None,
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
        clean_instruction = (instruction or "").strip()
        if clean_instruction and len(clean_instruction) > 20_000:
            raise ResourceWorkshopError(
                "workshop_instruction_invalid", "Skill instruction is too large"
            )
        package_id = draft_id.replace("-", "")
        payload: dict[str, Any] = {
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
        if kind == "skill" and clean_instruction:
            payload["spec"]["instruction"] = clean_instruction
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

    def approve_skill(
        self, resource_id: str, version: str, instruction: str | None = None
    ) -> dict[str, Any]:
        """Promote a reviewed declarative Skill draft into the local Catalog."""
        try:
            resource = self.catalog.detail(resource_id, version)
        except ResourceCatalogError as exc:
            raise ResourceWorkshopError("workshop_draft_not_found", str(exc)) from exc
        if resource.get("origin") != "workshop" or resource.get("kind") != "skill":
            raise ResourceWorkshopError(
                "workshop_skill_invalid",
                "Only quarantined Skill drafts can be approved",
            )
        target = self._workshop_package(resource_id, version)
        if target is None:
            raise ResourceWorkshopError(
                "workshop_draft_not_found", "Skill draft package was not found"
            )
        try:
            payload = yaml.safe_load(target.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ResourceWorkshopError(
                "workshop_draft_invalid", "Skill draft could not be read"
            ) from exc
        if not isinstance(payload, dict):
            raise ResourceWorkshopError(
                "workshop_draft_invalid", "Skill draft is invalid"
            )
        spec = payload.get("spec")
        if not isinstance(spec, dict):
            raise ResourceWorkshopError(
                "workshop_draft_invalid", "Skill draft spec is invalid"
            )
        clean_instruction = (instruction or spec.get("instruction") or "").strip()
        if not clean_instruction:
            raise ResourceWorkshopError(
                "workshop_instruction_required", "Add Skill instruction before approval"
            )
        if len(clean_instruction) > 20_000:
            raise ResourceWorkshopError(
                "workshop_instruction_invalid", "Skill instruction is too large"
            )
        spec["instruction"] = clean_instruction
        payload["availability"] = "ready"
        payload["factory_selectable"] = True
        payload["runtime_status"] = "runtime_not_configured"
        payload["tags"] = ["workshop", "approved", "instruction"]
        spec["review_required"] = False
        temporary = target.with_name(f".{target.name}.{new_uuid7()}.tmp")
        try:
            temporary.write_text(
                yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            os.replace(temporary, target)
            self.catalog.reload_overlays()
        except (OSError, NodePackageError) as exc:
            temporary.unlink(missing_ok=True)
            raise ResourceWorkshopError(
                "workshop_draft_invalid", "Skill draft could not be approved"
            ) from exc
        return {
            "schema_version": "1.0",
            "resource": self.catalog.detail(resource_id, version),
        }

    def set_skill_enabled(
        self, resource_id: str, version: str, *, enabled: bool
    ) -> dict[str, Any]:
        """Toggle an approved workshop Skill without changing its instruction."""
        try:
            resource = self.catalog.detail(resource_id, version)
        except ResourceCatalogError as exc:
            raise ResourceWorkshopError("workshop_draft_not_found", str(exc)) from exc
        if resource.get("origin") != "workshop" or resource.get("kind") != "skill":
            raise ResourceWorkshopError(
                "workshop_skill_invalid",
                "Only workshop Skills can be enabled or disabled",
            )
        target = self._workshop_package(resource_id, version)
        if target is None:
            raise ResourceWorkshopError(
                "workshop_draft_not_found", "Skill draft package was not found"
            )
        try:
            payload = yaml.safe_load(target.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ResourceWorkshopError(
                "workshop_draft_invalid", "Skill draft could not be read"
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("spec"), dict):
            raise ResourceWorkshopError(
                "workshop_draft_invalid", "Skill draft is invalid"
            )
        payload["availability"] = "ready" if enabled else "disabled"
        payload["factory_selectable"] = enabled
        payload["runtime_status"] = "runtime_not_configured"
        payload["tags"] = (
            ["workshop", "approved", "instruction"]
            if enabled
            else ["workshop", "disabled", "instruction"]
        )
        payload["spec"]["review_required"] = not enabled
        temporary = target.with_name(f".{target.name}.{new_uuid7()}.tmp")
        try:
            temporary.write_text(
                yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            os.replace(temporary, target)
            self.catalog.reload_overlays()
        except (OSError, NodePackageError) as exc:
            temporary.unlink(missing_ok=True)
            raise ResourceWorkshopError(
                "workshop_draft_invalid", "Skill state could not be updated"
            ) from exc
        return {
            "schema_version": "1.0",
            "resource": self.catalog.detail(resource_id, version),
        }

    def _workshop_package(self, resource_id: str, version: str) -> Path | None:
        root = self.overlay_root / "workshop"
        if not root.is_dir():
            return None
        for target in root.glob("*/node.yaml"):
            if target.is_symlink() or not target.is_file():
                continue
            try:
                payload = yaml.safe_load(target.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                continue
            if (
                isinstance(payload, dict)
                and payload.get("resource_id") == resource_id
                and payload.get("version") == version
            ):
                return target
        return None


def _workshop_resource_id(kind: str, requested_reference: str, draft_id: str) -> str:
    identity, _, _version = requested_reference.partition("@")
    slug_source = identity.removeprefix("veyra.")
    slug = _SLUG.sub("-", slug_source.lower()).strip("-") or "draft"
    kind_slug = _KIND_SLUG[kind]
    suffix = draft_id.replace("-", "")[:8]
    return f"veyra.workshop.{kind_slug}.{slug}-{suffix}"
