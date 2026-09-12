"""Configure MCP servers, normalize discovered tools, and execute locked calls."""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from veyra_agent_platform.contracts.common import SCHEMA_VERSION, new_uuid7
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.resources.registry import NodePackageError
from veyra_agent_platform.local.secrets import SecretStore, resolve_secret

from .store import McpServerStore
from .transport import (
    McpTransport,
    McpTransportError,
    StdioMcpTransport,
    TransportFactory,
)

_COMMAND = re.compile(r"^[A-Za-z0-9._/-]+$")
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_SECRET_REF = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_TOOL_SLUG = re.compile(r"[^a-z0-9]+")
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,63}$")


class McpError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class McpService:
    """Host-owned MCP configuration and Runtime adapter. Secrets stay in env names."""

    def __init__(
        self,
        store: McpServerStore,
        overlay_root: Path,
        catalog: ResourceCatalog,
        transport_factory: TransportFactory | None = None,
        secret_store: SecretStore | None = None,
    ) -> None:
        self.store = store
        self.overlay_root = overlay_root
        self.catalog = catalog
        self._transport_factory = transport_factory or _stdio_factory
        self._secret_store = secret_store

    def list_servers(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "servers": [McpServerStore.payload(row) for row in self.store.list()],
        }

    def create_server(
        self,
        *,
        name: str,
        command: str,
        args: list[str] | None = None,
        env_names: dict[str, str] | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        clean_name = _text(name, "mcp_name_invalid", "MCP server name is required")
        if _NAME.fullmatch(clean_name) is None:
            raise McpError(
                "mcp_name_invalid", "MCP server name is not a safe identifier"
            )
        clean_command = _command(command)
        clean_args = _args(args or [])
        clean_env = _env_names(env_names or {})
        server_id = new_uuid7()
        now = _now()
        with self.store.transaction() as connection:
            self.store.create(
                connection,
                server_id=server_id,
                name=clean_name,
                command=clean_command,
                args=clean_args,
                env_names=clean_env,
                enabled=enabled,
                created_at=now,
            )
        row = self.store.get(server_id)
        if row is None:
            raise McpError("mcp_server_not_found", "MCP server was not found")
        return {
            "schema_version": SCHEMA_VERSION,
            "server": McpServerStore.payload(row),
        }

    def delete_server(self, server_id: str) -> dict[str, Any]:
        row = self.store.get(server_id)
        if row is None:
            raise McpError("mcp_server_not_found", "MCP server was not found")
        self.store.delete(server_id)
        self._clear_discovered(server_id)
        self.catalog.reload_overlays()
        return {
            "schema_version": SCHEMA_VERSION,
            "server_id": server_id,
            "deleted": True,
        }

    def update_server(self, server_id: str, *, enabled: bool) -> dict[str, Any]:
        """Enable or pause one configured MCP server without deleting its tools."""
        self._require(server_id)
        row = self.store.set_enabled(server_id, enabled=enabled, updated_at=_now())
        if row is None:
            raise McpError("mcp_server_not_found", "MCP server was not found")
        return {
            "schema_version": SCHEMA_VERSION,
            "server": McpServerStore.payload(row),
        }

    def edit_server(
        self,
        server_id: str,
        *,
        name: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        env_names: dict[str, str] | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        """Edit one MCP configuration and invalidate stale discovery metadata."""
        current = self._require(server_id)
        clean_name = _text(
            name if name is not None else current["name"],
            "mcp_name_invalid",
            "MCP server name is required",
        )
        if _NAME.fullmatch(clean_name) is None:
            raise McpError(
                "mcp_name_invalid", "MCP server name is not a safe identifier"
            )
        old_args = list(json.loads(current["args_json"]))
        old_env = dict(json.loads(current["env_names_json"]))
        clean_command = _command(command if command is not None else current["command"])
        clean_args = _args(args if args is not None else old_args)
        clean_env = _env_names(env_names if env_names is not None else old_env)
        clean_enabled = bool(current["enabled"]) if enabled is None else enabled
        row = self.store.update(
            server_id,
            name=clean_name,
            command=clean_command,
            args=clean_args,
            env_names=clean_env,
            enabled=clean_enabled,
            updated_at=_now(),
        )
        if row is None:
            raise McpError("mcp_server_not_found", "MCP server was not found")
        if (
            clean_name != current["name"]
            or clean_command != current["command"]
            or clean_args != old_args
            or clean_env != old_env
        ):
            self._clear_discovered(server_id)
            self.catalog.reload_overlays()
        return {
            "schema_version": SCHEMA_VERSION,
            "server": McpServerStore.payload(row),
        }

    def approve_tool(
        self, server_id: str, resource_id: str, version: str
    ) -> dict[str, Any]:
        """Promote one discovered descriptor after an explicit user review."""
        self._require(server_id)
        try:
            descriptor = self.catalog.detail(resource_id, version)
        except ValueError as exc:
            raise McpError("mcp_tool_not_found", "MCP tool was not found") from exc
        if descriptor.get("origin") != "discovered":
            raise McpError(
                "mcp_tool_not_discovered", "Only discovered MCP tools can be reviewed"
            )
        spec = descriptor.get("spec") or {}
        if spec.get("mcp_server_id") != server_id:
            raise McpError(
                "mcp_tool_server_mismatch", "MCP tool belongs to another server"
            )
        target = self._discovered_package(server_id, resource_id, version)
        if target is None:
            raise McpError("mcp_tool_not_found", "MCP tool package was not found")
        try:
            payload = yaml.safe_load(target.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise McpError(
                "mcp_discovery_invalid", "MCP tool package could not be read"
            ) from exc
        if not isinstance(payload, dict):
            raise McpError("mcp_discovery_invalid", "MCP tool package is invalid")
        payload["factory_selectable"] = True
        package_spec = payload.get("spec")
        if not isinstance(package_spec, dict):
            raise McpError("mcp_discovery_invalid", "MCP tool spec is invalid")
        package_spec["review_required"] = False
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
            raise McpError(
                "mcp_discovery_invalid", "MCP tool could not be approved"
            ) from exc
        return {
            "schema_version": SCHEMA_VERSION,
            "server_id": server_id,
            "resource": self.catalog.detail(resource_id, version),
        }

    def discover(self, server_id: str) -> dict[str, Any]:
        row = self._require(server_id)
        if not row["enabled"]:
            raise McpError("mcp_server_disabled", "MCP server is disabled")
        transport = self._transport(row)
        try:
            tools = transport.list_tools()
        except McpTransportError as exc:
            raise McpError(exc.code, str(exc)) from exc
        written: list[dict[str, Any]] = []
        for tool in tools:
            descriptor = self._write_discovered(row["server_id"], row["name"], tool)
            if descriptor is not None:
                written.append(descriptor)
        try:
            self.catalog.reload_overlays()
        except NodePackageError as exc:
            raise McpError("mcp_discovery_invalid", str(exc)) from exc
        resources = [
            self.catalog.detail(item["resource_id"], item["version"])
            for item in written
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            "server_id": server_id,
            "tools": resources,
        }

    def call(
        self, server_id: str, tool_name: str, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        row = self._require(server_id)
        if not row["enabled"]:
            raise McpError("mcp_server_disabled", "MCP server is disabled")
        transport = self._transport(row)
        try:
            return transport.call_tool(tool_name, arguments)
        except McpTransportError as exc:
            raise McpError(exc.code, str(exc)) from exc

    def readiness(self, server_id: str) -> dict[str, Any]:
        """Check an MCP server without spawning its process or calling a tool."""
        try:
            row = self._require(server_id)
        except McpError as exc:
            return {"ready": False, "code": exc.code, "detail": str(exc)}
        if not row["enabled"]:
            return {
                "ready": False,
                "code": "mcp_server_disabled",
                "detail": "MCP server is disabled",
            }
        env_names = json.loads(row["env_names_json"])
        for binding in env_names.values():
            secret_ref = binding if _SECRET_REF.fullmatch(binding) else ""
            value = resolve_secret(
                self._secret_store if secret_ref else None,
                secret_ref,
                binding,
            )
            if not value:
                return {
                    "ready": False,
                    "code": "mcp_env_missing",
                    "detail": "MCP server environment binding is not configured",
                }
        return {
            "ready": True,
            "code": "ready",
            "detail": (
                "MCP server is enabled and its environment bindings are configured"
            ),
        }

    def _require(self, server_id: str) -> Any:
        row = self.store.get(server_id)
        if row is None:
            raise McpError("mcp_server_not_found", "MCP server was not found")
        return row

    def _transport(self, row: Any) -> McpTransport:
        env_names = dict(json.loads(row["env_names_json"]))
        env: dict[str, str] = {}
        for mcp_key, binding in env_names.items():
            secret_ref = binding if _SECRET_REF.fullmatch(binding) else ""
            value = resolve_secret(
                self._secret_store if secret_ref else None,
                secret_ref,
                binding,
            )
            if not value:
                raise McpError(
                    "mcp_env_missing",
                    f"MCP binding {binding} is not configured",
                )
            env[mcp_key] = value
        args = list(json.loads(row["args_json"]))
        return self._transport_factory(row["command"], args, env)

    def _write_discovered(
        self, server_id: str, server_name: str, tool: dict[str, Any]
    ) -> dict[str, str] | None:
        name = tool.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        tool_slug = _TOOL_SLUG.sub("-", name.lower()).strip("-") or "tool"
        package_id = f"{_package_prefix(server_id)}-{tool_slug}"[:80]
        server_slug = _TOOL_SLUG.sub("-", server_name.lower()).strip("-")
        resource_id = f"veyra.mcp.{server_slug}.{tool_slug}"
        description = tool.get("description")
        if not isinstance(description, str) or not description.strip():
            description = f"Discovered MCP tool {name}"
        input_schema = _input_schema(tool.get("inputSchema"))
        input_required = _input_required(tool.get("inputSchema"), input_schema)
        payload = {
            "resource_id": resource_id,
            "kind": "tool",
            "name": name[:120],
            "description": description.strip()[:4_000],
            "availability": "ready",
            "factory_selectable": False,
            "runtime_status": "supported",
            "required_permissions": {
                "network_hosts": [],
                "tools": [resource_id],
                "filesystem_read_roots": [],
                "filesystem_write_roots": [],
                "shell_workspace_only": False,
            },
            "tags": ["mcp", "discovered", "review_required"],
            "spec": {
                "adapter": "veyra.runtime.mcp.call",
                "approval_required": True,
                "review_required": True,
                "mcp_server_id": server_id,
                "mcp_tool_name": name,
                "input_schema": input_schema,
                "input_required": input_required,
                "tool_name": f"mcp.{name}",
                "ui": {
                    "category": "mcp",
                    "icon": "plug",
                    "title": name[:80],
                },
            },
            "version": "1.0.0",
        }
        target = self.overlay_root / "discovered" / package_id / "node.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return {"resource_id": resource_id, "version": "1.0.0"}

    def _discovered_package(
        self, server_id: str, resource_id: str, version: str
    ) -> Path | None:
        root = self.overlay_root / "discovered"
        if not root.is_dir():
            return None
        for target in root.glob("*/node.yaml"):
            if target.is_symlink() or not target.is_file():
                continue
            try:
                payload = yaml.safe_load(target.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(payload, dict):
                continue
            spec = payload.get("spec")
            if (
                payload.get("resource_id") == resource_id
                and payload.get("version") == version
                and isinstance(spec, dict)
                and spec.get("mcp_server_id") == server_id
            ):
                return target
        return None

    def _clear_discovered(self, server_id: str) -> None:
        root = self.overlay_root / "discovered"
        prefix = _package_prefix(server_id)
        if root.is_dir():
            for path in root.glob(f"{prefix}*/node.yaml"):
                shutil.rmtree(path.parent, ignore_errors=True)


def _stdio_factory(
    command: str, args: list[str], env: Mapping[str, str]
) -> McpTransport:
    return StdioMcpTransport(command, list(args), env)


def _command(value: str) -> str:
    command = value.strip()
    if not command or _COMMAND.fullmatch(command) is None or ".." in command:
        raise McpError(
            "mcp_command_invalid", "MCP command must be a simple executable path"
        )
    return command


def _args(values: list[str]) -> list[str]:
    parsed: list[str] = []
    for item in values:
        if not isinstance(item, str) or not item or "\x00" in item:
            raise McpError("mcp_args_invalid", "MCP args must be non-empty strings")
        parsed.append(item)
    return parsed


def _env_names(values: dict[str, str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for key, host_name in values.items():
        if _ENV_NAME.fullmatch(key) is None or (
            _ENV_NAME.fullmatch(host_name) is None
            and _SECRET_REF.fullmatch(host_name) is None
        ):
            raise McpError(
                "mcp_env_invalid",
                "MCP env maps server keys to host environment names or secret "
                "references",
            )
        parsed[key] = host_name
    return parsed


def _text(value: str, code: str, message: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise McpError(code, message)
    return cleaned


def _input_schema(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    properties = value.get("properties")
    if not isinstance(properties, dict):
        return {}
    schema: dict[str, str] = {}
    for name, spec in properties.items():
        if not isinstance(name, str) or not name:
            continue
        declared = "string"
        if isinstance(spec, dict) and isinstance(spec.get("type"), str):
            declared = spec["type"]
        schema[name] = (
            declared
            if declared
            in {"string", "boolean", "integer", "number", "object", "array", "null"}
            else "string"
        )
    return schema


def _input_required(value: object, schema: dict[str, str]) -> list[str]:
    if not isinstance(value, dict):
        return []
    required = value.get("required")
    if not isinstance(required, list):
        return []
    return [name for name in required if isinstance(name, str) and name in schema]


def _package_prefix(server_id: str) -> str:
    return server_id.replace("-", "")[:12]


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
