"""Configure MCP servers, normalize discovered tools, and execute locked calls."""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import yaml  # type: ignore[import-untyped]

from veyra_agent_platform.contracts.common import SCHEMA_VERSION, new_uuid7
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.resources.registry import NodePackageError
from veyra_agent_platform.local.secrets import (
    SecretStore,
    resolve_secret,
    secret_environment_name,
)

from .store import McpServerStore
from .transport import (
    McpTransport,
    McpTransportError,
    StdioMcpTransport,
    StreamableHttpMcpTransport,
    TransportFactory,
)

_COMMAND = re.compile(r"^[A-Za-z0-9._/-]+$")
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_SECRET_REF = re.compile(r"^[a-z][a-z0-9_-]{0,63}\.[a-z][a-z0-9_.-]{0,127}$")
_TOOL_SLUG = re.compile(r"[^a-z0-9]+")
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,63}$")
_HEADER_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,127}$")
_HEADER_PLACEHOLDER = re.compile(r"\$\{([A-Z][A-Z0-9_]{0,127})\}")
_TRANSPORTS = {"stdio", "streamable_http"}
_RESERVED_HEADERS = {"accept", "content-type", "mcp-protocol-version", "mcp-session-id"}
_SENSITIVE_HEADERS = ("authorization", "token", "key", "secret", "credential")


class McpError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def normalize_mcp_config(value: object) -> list[dict[str, Any]]:
    """Normalize a standard MCP config without resolving any secret values."""
    if not isinstance(value, Mapping):
        raise McpError("mcp_import_invalid", "MCP config must be a JSON object")
    raw = value["mcpServers"] if "mcpServers" in value else value.get("servers")
    if isinstance(raw, Mapping):
        entries = list(raw.items())
    elif isinstance(raw, list):
        entries = [(str(index), item) for index, item in enumerate(raw)]
    else:
        raise McpError("mcp_import_invalid", "MCP config has no server definitions")
    if not entries or len(entries) > 32:
        raise McpError("mcp_import_invalid", "Import between one and 32 MCP servers")

    normalized: list[dict[str, Any]] = []
    names: set[str] = set()
    for key, raw_config in entries:
        if not isinstance(raw_config, Mapping):
            raise McpError("mcp_import_invalid", "Each MCP server must be an object")
        raw_name = raw_config.get("name", key)
        name = _text(raw_name, "mcp_name_invalid", "MCP server name is required")
        args = raw_config.get("args", [])
        if not isinstance(args, list):
            raise McpError("mcp_args_invalid", "MCP args must be a list of strings")
        has_url = isinstance(raw_config.get("url"), str) and bool(
            raw_config["url"].strip()
        )
        has_command = isinstance(raw_config.get("command"), str) and bool(
            raw_config["command"].strip()
        )
        if has_url == has_command:
            raise McpError(
                "mcp_transport_invalid",
                "Each MCP server needs exactly one command or URL",
            )
        raw_env = (
            raw_config["env_names"]
            if "env_names" in raw_config
            else raw_config.get("env", {})
        )
        if raw_env is None:
            raw_env = {}
        if not isinstance(raw_env, Mapping):
            raise McpError(
                "mcp_env_invalid", "MCP environment bindings must be an object"
            )
        env_names: dict[str, str] = {}
        for env_key, binding in raw_env.items():
            if not isinstance(env_key, str) or _ENV_NAME.fullmatch(env_key) is None:
                raise McpError(
                    "mcp_env_invalid", "MCP environment names must be uppercase"
                )
            env_names[env_key] = _normalize_binding(binding)
        raw_headers = (
            raw_config["headers"]
            if "headers" in raw_config
            else raw_config.get("header_templates", {})
        )
        if raw_headers is None:
            raw_headers = {}
        if not isinstance(raw_headers, Mapping):
            raise McpError("mcp_header_invalid", "MCP HTTP headers must be an object")
        headers: dict[str, str] = {}
        for header_name, header_value in raw_headers.items():
            if not isinstance(header_name, str) or not isinstance(header_value, str):
                raise McpError(
                    "mcp_header_invalid", "MCP HTTP header bindings are invalid"
                )
            headers[header_name] = header_value
        if "enabled" in raw_config:
            enabled_value = raw_config["enabled"]
            if not isinstance(enabled_value, bool):
                raise McpError("mcp_enabled_invalid", "MCP enabled must be a boolean")
            enabled = enabled_value
        else:
            disabled_value = raw_config.get("disabled", False)
            if not isinstance(disabled_value, bool):
                raise McpError("mcp_enabled_invalid", "MCP disabled must be a boolean")
            enabled = not disabled_value
        candidate = {
            "name": name,
            "command": raw_config.get("command") if has_command else None,
            "args": args if not has_url else [],
            "env_names": env_names if not has_url else {},
            "transport": "streamable_http" if has_url else "stdio",
            "url": raw_config.get("url") if has_url else None,
            "headers": headers,
            "enabled": enabled,
        }
        cleaned = _validated_server_config(**candidate)
        if name in names:
            raise McpError(
                "mcp_import_invalid", "Imported MCP server names must be unique"
            )
        names.add(name)
        (
            clean_name,
            clean_command,
            clean_args,
            clean_env,
            clean_transport,
            clean_url,
            clean_headers,
            clean_enabled,
        ) = cleaned
        normalized.append(
            {
                "name": clean_name,
                "command": clean_command,
                "args": clean_args,
                "env_names": clean_env,
                "transport": clean_transport,
                "url": clean_url,
                "headers": clean_headers,
                "enabled": clean_enabled,
            }
        )
    return normalized


class McpService:
    """Host-owned MCP configuration and Runtime adapter. Secrets stay in env names."""

    def __init__(
        self,
        store: McpServerStore,
        overlay_root: Path,
        catalog: ResourceCatalog,
        transport_factory: TransportFactory | None = None,
        secret_store: SecretStore | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.store = store
        self.overlay_root = overlay_root
        self.catalog = catalog
        self._transport_factory = transport_factory or _stdio_factory
        self._secret_store = secret_store
        self._http_client = http_client

    def list_servers(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "servers": [McpServerStore.payload(row) for row in self.store.list()],
        }

    def create_server(
        self,
        *,
        name: str,
        command: str | None = None,
        args: list[str] | None = None,
        env_names: dict[str, str] | None = None,
        transport: str = "stdio",
        url: str | None = None,
        headers: dict[str, str] | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        (
            clean_name,
            clean_command,
            clean_args,
            clean_env,
            clean_transport,
            clean_url,
            clean_headers,
            clean_enabled,
        ) = _validated_server_config(
            name=name,
            command=command,
            args=args or [],
            env_names=env_names or {},
            transport=transport,
            url=url,
            headers=headers or {},
            enabled=enabled,
        )
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
                transport=clean_transport,
                url=clean_url,
                header_templates=clean_headers,
                enabled=clean_enabled,
                created_at=now,
            )
        row = self.store.get(server_id)
        if row is None:
            raise McpError("mcp_server_not_found", "MCP server was not found")
        return {
            "schema_version": SCHEMA_VERSION,
            "server": McpServerStore.payload(row),
        }

    def import_servers(self, configs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Atomically import already-parsed standard MCP server definitions."""
        if not configs or len(configs) > 32:
            raise McpError(
                "mcp_import_invalid", "Import between one and 32 MCP servers"
            )
        prepared = [
            _validated_server_config(
                name=config.get("name"),
                command=config.get("command"),
                args=config.get("args") or [],
                env_names=config.get("env_names") or {},
                transport=config.get("transport", "stdio"),
                url=config.get("url"),
                headers=config.get("headers") or {},
                enabled=config.get("enabled", True),
            )
            for config in configs
        ]
        names = [item[0] for item in prepared]
        if len(set(names)) != len(names):
            raise McpError(
                "mcp_import_invalid", "Imported MCP server names must be unique"
            )
        now = _now()
        server_ids = [new_uuid7() for _ in prepared]
        with self.store.transaction() as connection:
            for server_id, (
                name,
                command,
                args,
                env_names,
                transport,
                url,
                headers,
                enabled,
            ) in zip(server_ids, prepared, strict=True):
                self.store.create(
                    connection,
                    server_id=server_id,
                    name=name,
                    command=command,
                    args=args,
                    env_names=env_names,
                    transport=transport,
                    url=url,
                    header_templates=headers,
                    enabled=enabled,
                    created_at=now,
                )
        rows = [self.store.get(server_id) for server_id in server_ids]
        if any(row is None for row in rows):
            raise McpError("mcp_server_not_found", "Imported MCP server was not found")
        return {
            "schema_version": SCHEMA_VERSION,
            "servers": [McpServerStore.payload(row) for row in rows if row is not None],
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
        self._sync_discovered_state(server_id, enabled=enabled)
        self.catalog.reload_overlays()
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
        transport: str | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
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
        old_transport = str(current["transport"] or "stdio")
        old_url = current["url"]
        old_headers = dict(json.loads(current["header_templates_json"]))
        requested_transport = transport if transport is not None else old_transport
        same_transport = requested_transport == old_transport
        (
            clean_name,
            clean_command,
            clean_args,
            clean_env,
            clean_transport,
            clean_url,
            clean_headers,
            clean_enabled,
        ) = _validated_server_config(
            name=clean_name,
            command=command
            if command is not None
            else (current["command"] if same_transport else None),
            args=args if args is not None else (old_args if same_transport else []),
            env_names=env_names
            if env_names is not None
            else (old_env if same_transport else {}),
            transport=requested_transport,
            url=url if url is not None else (old_url if same_transport else None),
            headers=headers
            if headers is not None
            else (old_headers if same_transport else {}),
            enabled=bool(current["enabled"]) if enabled is None else enabled,
        )
        row = self.store.update(
            server_id,
            name=clean_name,
            command=clean_command,
            args=clean_args,
            env_names=clean_env,
            transport=clean_transport,
            url=clean_url,
            header_templates=clean_headers,
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
            or clean_transport != old_transport
            or clean_url != old_url
            or clean_headers != old_headers
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
        server = self._require(server_id)
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
        package_spec = payload.get("spec")
        if not isinstance(package_spec, dict):
            raise McpError("mcp_discovery_invalid", "MCP tool spec is invalid")
        package_spec["review_required"] = False
        payload["availability"] = "ready" if bool(server["enabled"]) else "disabled"
        payload["factory_selectable"] = bool(server["enabled"])
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
        network_hosts = self._network_hosts(row)
        for tool in tools:
            descriptor = self._write_discovered(
                row["server_id"], row["name"], tool, network_hosts=network_hosts
            )
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
        transport = str(row["transport"] or "stdio")
        if transport == "streamable_http":
            if not isinstance(row["url"], str) or not row["url"].strip():
                return {
                    "ready": False,
                    "code": "mcp_url_missing",
                    "detail": "MCP HTTP transport requires an endpoint URL",
                }
            try:
                _url(row["url"])
                self._resolve_headers(json.loads(row["header_templates_json"]))
            except McpError as exc:
                return {"ready": False, "code": exc.code, "detail": str(exc)}
            return {
                "ready": True,
                "code": "ready",
                "detail": "MCP HTTP endpoint and header bindings are configured",
            }
        if transport != "stdio":
            return {
                "ready": False,
                "code": "mcp_transport_invalid",
                "detail": "MCP transport is not supported",
            }
        env_names = json.loads(row["env_names_json"])
        for binding in env_names.values():
            try:
                self._resolve_binding(binding, "mcp_env_missing")
            except McpError as exc:
                return {
                    "ready": False,
                    "code": exc.code,
                    "detail": str(exc),
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
        transport = str(row["transport"] or "stdio")
        if transport == "streamable_http":
            url = row["url"]
            if not isinstance(url, str) or not url.strip():
                raise McpError(
                    "mcp_url_missing", "MCP HTTP transport requires an endpoint URL"
                )
            endpoint = _url(url)
            headers = self._resolve_headers(json.loads(row["header_templates_json"]))
            return StreamableHttpMcpTransport(
                endpoint, headers, http_client=self._http_client
            )
        if transport != "stdio":
            raise McpError("mcp_transport_invalid", "MCP transport is not supported")
        env_names = dict(json.loads(row["env_names_json"]))
        env: dict[str, str] = {}
        for mcp_key, binding in env_names.items():
            env[mcp_key] = self._resolve_binding(binding, "mcp_env_missing")
        args = list(json.loads(row["args_json"]))
        return self._transport_factory(row["command"], args, env)

    def _resolve_binding(self, binding: Any, code: str) -> str:
        if not isinstance(binding, str):
            raise McpError(code, "MCP host binding is not configured")
        secret_ref = binding if _SECRET_REF.fullmatch(binding) else ""
        env_name = secret_environment_name(binding) if secret_ref else binding
        value = resolve_secret(
            self._secret_store if secret_ref else None,
            secret_ref,
            env_name,
        )
        if not value:
            raise McpError(code, "MCP host binding is not configured")
        return value

    def _resolve_headers(self, templates: Any) -> dict[str, str]:
        if not isinstance(templates, dict):
            raise McpError("mcp_header_invalid", "MCP HTTP headers are invalid")
        resolved: dict[str, str] = {}
        for name, template in templates.items():
            if not isinstance(name, str) or not isinstance(template, str):
                raise McpError("mcp_header_invalid", "MCP HTTP headers are invalid")
            if _HEADER_PLACEHOLDER.search(template):
                resolved[name] = _HEADER_PLACEHOLDER.sub(
                    lambda match: self._resolve_binding(
                        match.group(1), "mcp_header_missing"
                    ),
                    template,
                )
            elif _ENV_NAME.fullmatch(template) or _SECRET_REF.fullmatch(template):
                resolved[name] = self._resolve_binding(template, "mcp_header_missing")
            else:
                resolved[name] = template
        return resolved

    @staticmethod
    def _network_hosts(row: Any) -> list[str]:
        if str(row["transport"] or "stdio") != "streamable_http":
            return []
        url = row["url"]
        if not isinstance(url, str):
            raise McpError(
                "mcp_url_missing", "MCP HTTP transport requires an endpoint URL"
            )
        endpoint = _url(url)
        hostname = urlsplit(endpoint).hostname
        if not hostname:
            raise McpError("mcp_url_invalid", "MCP HTTP endpoint URL is invalid")
        return [hostname.lower()]

    def _write_discovered(
        self,
        server_id: str,
        server_name: str,
        tool: dict[str, Any],
        *,
        network_hosts: list[str] | None = None,
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
                "network_hosts": list(network_hosts or []),
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

    def _sync_discovered_state(self, server_id: str, *, enabled: bool) -> None:
        """Keep discovered catalog availability aligned with server lifecycle."""
        root = self.overlay_root / "discovered"
        if not root.is_dir():
            return
        prefix = _package_prefix(server_id)
        for target in root.glob(f"{prefix}*/node.yaml"):
            if target.is_symlink() or not target.is_file():
                continue
            try:
                payload = yaml.safe_load(target.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(payload, dict):
                continue
            spec = payload.get("spec")
            if not isinstance(spec, dict) or spec.get("mcp_server_id") != server_id:
                continue
            payload["availability"] = "ready" if enabled else "disabled"
            payload["factory_selectable"] = bool(
                enabled and not spec.get("review_required", False)
            )
            temporary = target.with_name(f".{target.name}.{new_uuid7()}.tmp")
            try:
                temporary.write_text(
                    yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
                    encoding="utf-8",
                )
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)


def _stdio_factory(
    command: str, args: list[str], env: Mapping[str, str]
) -> McpTransport:
    return StdioMcpTransport(command, list(args), env)


def _validated_server_config(
    *,
    name: Any,
    command: Any,
    args: Any,
    env_names: Any,
    transport: Any,
    url: Any,
    headers: Any,
    enabled: Any,
) -> tuple[str, str, list[str], dict[str, str], str, str | None, dict[str, str], bool]:
    if not isinstance(name, str):
        raise McpError("mcp_name_invalid", "MCP server name is required")
    clean_name = _text(name, "mcp_name_invalid", "MCP server name is required")
    if _NAME.fullmatch(clean_name) is None:
        raise McpError("mcp_name_invalid", "MCP server name is not a safe identifier")
    if not isinstance(transport, str) or transport not in _TRANSPORTS:
        raise McpError("mcp_transport_invalid", "MCP transport is not supported")
    if not isinstance(args, list):
        raise McpError("mcp_args_invalid", "MCP args must be a list of strings")
    if not isinstance(env_names, dict):
        raise McpError("mcp_env_invalid", "MCP environment bindings must be an object")
    if not isinstance(headers, dict):
        raise McpError("mcp_header_invalid", "MCP HTTP headers must be an object")
    if not isinstance(enabled, bool):
        raise McpError("mcp_enabled_invalid", "MCP enabled must be a boolean")
    if transport == "stdio":
        if not isinstance(command, str):
            raise McpError("mcp_command_invalid", "MCP command is required")
        if url is not None or headers:
            raise McpError(
                "mcp_transport_invalid",
                "stdio MCP servers cannot define an HTTP URL or headers",
            )
        return (
            clean_name,
            _command(command),
            _args(args),
            _env_names(env_names),
            transport,
            None,
            {},
            enabled,
        )
    if command not in {None, ""} or args or env_names:
        raise McpError(
            "mcp_transport_invalid",
            "HTTP MCP servers cannot define a subprocess command or environment",
        )
    if not isinstance(url, str):
        raise McpError("mcp_url_missing", "MCP HTTP transport requires an endpoint URL")
    return (
        clean_name,
        "",
        [],
        {},
        transport,
        _url(url),
        _header_templates(headers),
        enabled,
    )


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


def _normalize_binding(value: Any) -> str:
    if not isinstance(value, str):
        raise McpError(
            "mcp_env_invalid",
            "MCP config may contain environment names or secret references only",
        )
    binding = value.strip()
    template = re.fullmatch(r"\$\{([A-Z][A-Z0-9_]{0,127})\}", binding)
    if template:
        return template.group(1)
    if _ENV_NAME.fullmatch(binding) or _SECRET_REF.fullmatch(binding):
        return binding
    raise McpError(
        "mcp_env_invalid",
        "MCP config may contain environment names or secret references only; "
        "plaintext credentials were not imported",
    )


def _url(value: str) -> str:
    url = value.strip()
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
    except ValueError as exc:
        raise McpError("mcp_url_invalid", "MCP HTTP endpoint URL is invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise McpError(
            "mcp_url_invalid",
            "MCP HTTP endpoint must be an http(s) URL without embedded credentials",
        )
    if parsed.scheme == "http" and hostname.lower() not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise McpError(
            "mcp_url_invalid",
            "Remote MCP endpoints must use HTTPS",
        )
    return url


def _header_templates(values: dict[str, str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for name, template in values.items():
        if (
            not isinstance(name, str)
            or _HEADER_NAME.fullmatch(name) is None
            or name.lower() in _RESERVED_HEADERS
            or not isinstance(template, str)
            or not template.strip()
            or len(template) > 2_000
            or "\r" in template
            or "\n" in template
        ):
            raise McpError("mcp_header_invalid", "MCP HTTP header binding is invalid")
        placeholders = list(_HEADER_PLACEHOLDER.finditer(template))
        remainder = _HEADER_PLACEHOLDER.sub("", template).strip()
        if "${" in template and len(placeholders) == 0:
            raise McpError(
                "mcp_header_invalid",
                "MCP HTTP header references must use uppercase environment "
                "placeholders",
            )
        if (
            any(part in name.lower() for part in _SENSITIVE_HEADERS)
            and not placeholders
            and not (
                _ENV_NAME.fullmatch(template.strip())
                or _SECRET_REF.fullmatch(template.strip())
            )
        ):
            raise McpError(
                "mcp_header_invalid",
                "Sensitive MCP headers must use an environment or secret reference",
            )
        if placeholders and not remainder and not template.strip().startswith("${"):
            raise McpError("mcp_header_invalid", "MCP HTTP header binding is invalid")
        parsed[name] = template.strip()
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
