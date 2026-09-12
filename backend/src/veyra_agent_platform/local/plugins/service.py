"""Persist, review, and explicitly activate declarative Plugin Packs."""

from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from typing import Any

from veyra_agent_platform.contracts.common import SCHEMA_VERSION, new_uuid7
from veyra_agent_platform.local.mcp import McpError, McpService
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceWorkshop
from veyra_agent_platform.local.resources.workshop import ResourceWorkshopError

from .packaging import (
    PluginPackError,
    unpack_plugin_archive,
)

_PLUGIN_ID = re.compile(r"^veyra\.plugin\.[a-z][a-z0-9_.-]{1,63}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_STATES = {"quarantined", "active", "disabled", "activation_failed"}


class PluginError(ValueError):
    """A Plugin Pack operation failed with a safe API error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PluginService:
    """Manage packs as data; only explicit activation changes runtime resources."""

    def __init__(
        self,
        root: Path,
        catalog: ResourceCatalog,
        workshop: ResourceWorkshop,
        mcp: McpService,
    ) -> None:
        self.root = root
        self.catalog = catalog
        self.workshop = workshop
        self.mcp = mcp

    def list_packs(self) -> dict[str, Any]:
        packs: list[dict[str, Any]] = []
        if self.root.is_dir():
            for plugin_root in sorted(self.root.iterdir()):
                if plugin_root.name.startswith(".") or not plugin_root.is_dir():
                    continue
                for version_root in sorted(plugin_root.iterdir()):
                    if version_root.name.startswith(".") or not version_root.is_dir():
                        continue
                    packs.append(self._summary(*self._read_record(version_root)))
        return {"schema_version": SCHEMA_VERSION, "plugins": packs}

    def list_trash(self) -> dict[str, Any]:
        packs: list[dict[str, Any]] = []
        trash_root = self.root / ".trash"
        if trash_root.is_dir():
            for trash_entry in sorted(trash_root.iterdir()):
                if trash_entry.name.startswith(".") or not trash_entry.is_dir():
                    continue
                metadata, state = self._read_record(trash_entry)
                item = self._summary(metadata, state)
                item["trash_id"] = trash_entry.name
                packs.append(item)
        return {"schema_version": SCHEMA_VERSION, "plugins": packs}

    def import_archive(
        self, *, filename: str | None, contents: bytes
    ) -> dict[str, Any]:
        try:
            pack = unpack_plugin_archive(filename, contents)
        except PluginPackError:
            raise
        target = self._target(pack.plugin_id, pack.version)
        if target.exists():
            try:
                metadata, state = self._read_record(target)
            except PluginError as exc:
                raise PluginError(
                    "plugin_conflict", "An incomplete Plugin Pack already exists"
                ) from exc
            if metadata.get("content_hash") == pack.content_hash:
                return {
                    "schema_version": SCHEMA_VERSION,
                    "plugin": self._summary(metadata, state),
                }
            raise PluginError(
                "plugin_conflict",
                "A different Plugin Pack with this id and version is already installed",
            )
        temporary = self.root / f".{pack.plugin_id.replace('.', '-')}-{new_uuid7()}.tmp"
        try:
            temporary.mkdir(parents=True, mode=0o700)
            metadata_path = temporary / "metadata.json"
            metadata_path.write_text(
                json.dumps(
                    pack.metadata(), ensure_ascii=False, sort_keys=True, indent=2
                )
                + "\n",
                encoding="utf-8",
            )
            (temporary / "package.vplugin.zip").write_bytes(contents)
            self._write_state(
                temporary,
                {
                    "state": "quarantined",
                    "skill_resources": [],
                    "mcp_server_ids": [],
                    "activation_error": None,
                },
            )
            target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            os.replace(temporary, target)
        except OSError as exc:
            self._remove_temporary(temporary)
            raise PluginError(
                "plugin_storage_failed", "Plugin Pack could not be stored"
            ) from exc
        return {
            "schema_version": SCHEMA_VERSION,
            "plugin": self._summary(pack.metadata(), self._initial_state()),
        }

    def activate(
        self, plugin_id: str, version: str, *, confirm: bool
    ) -> dict[str, Any]:
        if not confirm:
            raise PluginError(
                "plugin_confirmation_required",
                "Explicit confirmation is required to activate a Plugin Pack",
            )
        target = self._target(plugin_id, version)
        metadata, state = self._read_record(target)
        if state["state"] == "active":
            return {
                "schema_version": SCHEMA_VERSION,
                "plugin": self._summary(metadata, state),
            }
        try:
            skill_resources = list(state["skill_resources"])
            for index, skill in enumerate(metadata["skills"]):
                if index < len(skill_resources):
                    resource_id, resource_version = _split_reference(
                        skill_resources[index]
                    )
                    self.workshop.set_skill_enabled(
                        resource_id, resource_version, enabled=True
                    )
                    continue
                draft = self.workshop.create_draft(
                    confirm=True,
                    kind="skill",
                    requested_reference=skill["reference"],
                    name=skill["name"],
                    description=skill["description"],
                    instruction=skill["instruction"],
                )
                resource = draft["resource"]
                approved = self.workshop.approve_skill(
                    resource["resource_id"], resource["version"], skill["instruction"]
                )
                skill_resources.append(approved["resource"]["reference"])
                state["skill_resources"] = skill_resources
                self._write_state(target, state)

            if metadata["mcp_servers"]:
                if not state["mcp_server_ids"]:
                    configs = [
                        dict(server, enabled=False)
                        for server in metadata["mcp_servers"]
                    ]
                    imported = self.mcp.import_servers(configs)
                    state["mcp_server_ids"] = [
                        server["server_id"] for server in imported["servers"]
                    ]
                else:
                    state["mcp_server_ids"] = self._enable_mcp_servers(
                        metadata["mcp_servers"], state["mcp_server_ids"]
                    )
                self._write_state(target, state)
            self._disable_sibling_versions(plugin_id, version)
            state["state"] = "active"
            state["activation_error"] = None
            self._write_state(target, state)
        except (McpError, ResourceWorkshopError, OSError, KeyError, TypeError) as exc:
            state["state"] = "activation_failed"
            state["activation_error"] = str(exc)[:500]
            with suppress(OSError):
                self._write_state(target, state)
            raise PluginError(
                "plugin_activation_failed", "Plugin Pack activation could not complete"
            ) from exc
        return {
            "schema_version": SCHEMA_VERSION,
            "plugin": self._summary(metadata, state),
        }

    def disable(self, plugin_id: str, version: str, *, confirm: bool) -> dict[str, Any]:
        if not confirm:
            raise PluginError(
                "plugin_confirmation_required",
                "Explicit confirmation is required to disable a Plugin Pack",
            )
        target = self._target(plugin_id, version)
        metadata, state = self._read_record(target)
        try:
            self._disable_resources(state)
            state["state"] = "disabled"
            state["activation_error"] = None
            self._write_state(target, state)
        except (McpError, ResourceWorkshopError, OSError, KeyError, TypeError) as exc:
            state["state"] = "activation_failed"
            state["activation_error"] = str(exc)[:500]
            with suppress(OSError):
                self._write_state(target, state)
            raise PluginError(
                "plugin_disable_failed", "Plugin Pack could not be disabled"
            ) from exc
        return {
            "schema_version": SCHEMA_VERSION,
            "plugin": self._summary(metadata, state),
        }

    def uninstall(
        self, plugin_id: str, version: str, *, confirm: bool
    ) -> dict[str, Any]:
        if not confirm:
            raise PluginError(
                "plugin_confirmation_required",
                "Explicit confirmation is required to move a Plugin Pack to trash",
            )
        target = self._target(plugin_id, version)
        metadata, state = self._read_record(target)
        try:
            self._disable_resources(state)
            state["state"] = "disabled"
            state["activation_error"] = None
            self._write_state(target, state)
            trash_id = new_uuid7()
            trash_target = self.root / ".trash" / trash_id
            trash_target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            os.replace(target, trash_target)
        except (McpError, ResourceWorkshopError, OSError, KeyError, TypeError) as exc:
            state["state"] = "activation_failed"
            state["activation_error"] = str(exc)[:500]
            with suppress(OSError):
                self._write_state(target, state)
            raise PluginError(
                "plugin_uninstall_failed", "Plugin Pack could not be moved to trash"
            ) from exc
        result = self._summary(metadata, state)
        result.update({"trash_id": trash_id, "disposition": "trashed"})
        return {"schema_version": SCHEMA_VERSION, "plugin": result}

    def restore(self, trash_id: str, *, confirm: bool) -> dict[str, Any]:
        if not confirm:
            raise PluginError(
                "plugin_confirmation_required",
                "Explicit confirmation is required to restore a Plugin Pack",
            )
        if (
            re.fullmatch(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                trash_id,
            )
            is None
        ):
            raise PluginError("plugin_not_found", "Plugin Pack was not found")
        trash_target = self.root / ".trash" / trash_id
        metadata, state = self._read_record(trash_target)
        target = self._target(metadata["plugin_id"], metadata["version"])
        if target.exists():
            raise PluginError(
                "plugin_conflict", "A Plugin Pack with this id and version is installed"
            )
        try:
            target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            os.replace(trash_target, target)
        except OSError as exc:
            raise PluginError(
                "plugin_storage_failed", "Plugin Pack could not be restored"
            ) from exc
        return {
            "schema_version": SCHEMA_VERSION,
            "plugin": self._summary(metadata, state),
        }

    def _disable_resources(self, state: dict[str, Any]) -> None:
        for reference in state["skill_resources"]:
            resource_id, resource_version = _split_reference(reference)
            self.workshop.set_skill_enabled(
                resource_id, resource_version, enabled=False
            )
        for server_id in state["mcp_server_ids"]:
            try:
                self.mcp.update_server(server_id, enabled=False)
            except McpError as exc:
                if exc.code != "mcp_server_not_found":
                    raise

    def _disable_sibling_versions(self, plugin_id: str, version: str) -> None:
        plugin_root = self.root / plugin_id
        if not plugin_root.is_dir():
            return
        for sibling in sorted(plugin_root.iterdir()):
            if (
                sibling.name.startswith(".")
                or not sibling.is_dir()
                or sibling.name == version
            ):
                continue
            _metadata, state = self._read_record(sibling)
            if state["state"] != "active":
                continue
            self._disable_resources(state)
            state["state"] = "disabled"
            state["activation_error"] = None
            self._write_state(sibling, state)

    def _enable_mcp_servers(
        self, configs: list[dict[str, Any]], server_ids: list[str]
    ) -> list[str]:
        existing = {
            server["server_id"] for server in self.mcp.list_servers()["servers"]
        }
        enabled_ids: list[str] = []
        for index, config in enumerate(configs):
            server_id = server_ids[index] if index < len(server_ids) else None
            if isinstance(server_id, str) and server_id in existing:
                self.mcp.update_server(server_id, enabled=True)
                enabled_ids.append(server_id)
                continue
            imported = self.mcp.import_servers([dict(config, enabled=True)])
            enabled_ids.append(imported["servers"][0]["server_id"])
        return enabled_ids

    def archive(self, plugin_id: str, version: str) -> bytes:
        """Return an installed archive after checking its stored content hash."""
        target = self._target(plugin_id, version)
        metadata, _state = self._read_record(target)
        archive_path = target / "package.vplugin.zip"
        try:
            contents = archive_path.read_bytes()
        except OSError as exc:
            raise PluginError(
                "plugin_storage_invalid", "Plugin Pack archive is missing"
            ) from exc
        if hashlib.sha256(contents).hexdigest() != metadata.get("content_hash"):
            raise PluginError(
                "plugin_storage_invalid", "Plugin Pack archive integrity check failed"
            )
        return contents

    def _target(self, plugin_id: str, version: str) -> Path:
        if (
            _PLUGIN_ID.fullmatch(plugin_id) is None
            or _VERSION.fullmatch(version) is None
        ):
            raise PluginError("plugin_not_found", "Plugin Pack was not found")
        return self.root / plugin_id / version

    def _read_record(self, target: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        if not target.is_dir():
            raise PluginError("plugin_not_found", "Plugin Pack was not found")
        try:
            metadata = json.loads(
                (target / "metadata.json").read_text(encoding="utf-8")
            )
            state = json.loads((target / "state.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PluginError(
                "plugin_storage_invalid", "Installed Plugin Pack metadata is invalid"
            ) from exc
        if not isinstance(metadata, dict) or not isinstance(state, dict):
            raise PluginError(
                "plugin_storage_invalid", "Installed Plugin Pack metadata is invalid"
            )
        if state.get("state") not in _STATES:
            raise PluginError(
                "plugin_storage_invalid", "Installed Plugin Pack state is invalid"
            )
        for field in ("skills", "mcp_servers"):
            if not isinstance(metadata.get(field), list):
                raise PluginError(
                    "plugin_storage_invalid",
                    "Installed Plugin Pack metadata is invalid",
                )
        for field in ("skill_resources", "mcp_server_ids"):
            if not isinstance(state.get(field), list):
                raise PluginError(
                    "plugin_storage_invalid", "Installed Plugin Pack state is invalid"
                )
        return metadata, state

    @staticmethod
    def _initial_state() -> dict[str, Any]:
        return {
            "state": "quarantined",
            "skill_resources": [],
            "mcp_server_ids": [],
            "activation_error": None,
        }

    @staticmethod
    def _write_state(target: Path, state: dict[str, Any]) -> None:
        temporary = target / f".state.{new_uuid7()}.tmp"
        try:
            temporary.write_text(
                json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, target / "state.json")
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _remove_temporary(target: Path) -> None:
        if not target.exists():
            return
        for path in sorted(target.rglob("*"), reverse=True):
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                path.rmdir()
        target.rmdir()

    @staticmethod
    def _summary(metadata: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(metadata)
        result.update(
            {
                "schema_version": SCHEMA_VERSION,
                "state": state["state"],
                "skill_resources": list(state["skill_resources"]),
                "mcp_server_ids": list(state["mcp_server_ids"]),
                "activation_error": state.get("activation_error"),
            }
        )
        return result


def _split_reference(reference: Any) -> tuple[str, str]:
    if not isinstance(reference, str) or reference.count("@") != 1:
        raise PluginError(
            "plugin_storage_invalid", "Installed Skill reference is invalid"
        )
    resource_id, version = reference.rsplit("@", 1)
    if not resource_id or not version:
        raise PluginError(
            "plugin_storage_invalid", "Installed Skill reference is invalid"
        )
    return resource_id, version
