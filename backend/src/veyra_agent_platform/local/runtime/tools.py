"""Safe, catalog-backed Tool Runtime adapters for local Agent runs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from veyra_agent_platform.contracts.agent import AgentSource, FlowNode
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.local.mcp.service import McpError, McpService
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceCatalogError

_MAX_FILE_BYTES = 1_000_000
_FORBIDDEN_NAMES = {".env", "credentials.json", "id_rsa"}
_FORBIDDEN_SUFFIXES = (".key", ".pem", ".p12", ".token")
_READ_ADAPTER = "veyra.runtime.filesystem.read"
_WRITE_ADAPTER = "veyra.runtime.filesystem.write"
_MCP_ADAPTER = "veyra.runtime.mcp.call"


class ToolRuntimeError(RuntimeError):
    """A typed Tool Runtime failure safe to include in Run evidence."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ToolAuthorization:
    """Permission decision recorded before any adapter effect."""

    tool_reference: str
    adapter: str | None
    decision: Literal["allowed", "denied"]
    code: str
    reason: str
    input_digest: str
    approval_required: bool
    resource: dict[str, Any] | None


@dataclass(frozen=True)
class ToolExecution:
    output: dict[str, Any]
    receipt: dict[str, Any]


class ToolRuntime:
    """Resolve exact catalog references and execute only registered adapters."""

    def __init__(self, catalog: ResourceCatalog, mcp: McpService | None = None) -> None:
        self.catalog = catalog
        self.mcp = mcp

    def authorize(
        self, *, source: AgentSource, node: FlowNode, values: dict[str, Any]
    ) -> ToolAuthorization:
        if node.uses is None:
            return self._denied(
                None,
                "tool_reference_missing",
                "Tool node has no uses reference",
                values,
            )
        try:
            resource_id, version = node.uses.rsplit("@", 1)
            resource = self.catalog.detail(resource_id, version)
        except (ValueError, ResourceCatalogError):
            return self._denied(
                node.uses,
                "tool_not_registered",
                "Tool reference is not registered in the catalog",
                values,
            )
        if resource["kind"] not in {"tool", "mcp_tool"}:
            return self._denied(
                node.uses,
                "tool_not_executable",
                "Resource is not an executable Tool",
                values,
                resource,
            )
        if resource["availability"] != "ready":
            return self._denied(
                node.uses,
                "tool_unavailable",
                "Tool is not ready for local execution",
                values,
                resource,
            )
        if resource["runtime_status"] != "supported":
            return self._denied(
                node.uses,
                "tool_runtime_unavailable",
                "Tool has no local Runtime adapter",
                values,
                resource,
            )
        if source.lock.get(node.uses) != resource["content_hash"]:
            return self._denied(
                node.uses,
                "tool_lock_invalid",
                "Tool lock does not match the catalog version",
                values,
                resource,
            )
        try:
            self._authorize(source, resource)
        except ToolRuntimeError as exc:
            return self._denied(node.uses, exc.code, str(exc), values, resource)
        adapter = resource.get("spec", {}).get("adapter")
        if adapter not in {_READ_ADAPTER, _WRITE_ADAPTER, _MCP_ADAPTER}:
            return self._denied(
                node.uses,
                "tool_runtime_unavailable",
                "Tool adapter is not installed",
                values,
                resource,
            )
        if adapter == _MCP_ADAPTER and self.mcp is None:
            return self._denied(
                node.uses,
                "tool_runtime_unavailable",
                "MCP Runtime adapter is not installed",
                values,
                resource,
            )
        return ToolAuthorization(
            tool_reference=node.uses,
            adapter=str(adapter),
            decision="allowed",
            code="allowed",
            reason="catalog permission subset matched",
            input_digest=_input_digest(resource, values),
            approval_required=bool(resource.get("spec", {}).get("approval_required")),
            resource=resource,
        )

    def execute(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        if authorization.decision != "allowed" or authorization.resource is None:
            raise ToolRuntimeError(authorization.code, authorization.reason)
        if node.uses is None or source.lock.get(
            node.uses
        ) != authorization.resource.get("content_hash"):
            raise ToolRuntimeError(
                "tool_lock_invalid", "Tool lock does not match the catalog version"
            )
        if authorization.approval_required and not approved:
            raise ToolRuntimeError(
                "approval_required",
                "This Tool requires an approved HumanApproval on the current path",
            )
        adapter = authorization.adapter
        if adapter == _READ_ADAPTER:
            output, byte_length, relative_path = self._read_project_file(
                project_root, values.get("path")
            )
        elif adapter == _WRITE_ADAPTER:
            output, byte_length, relative_path = self._write_project_file(
                project_root, values.get("path"), values.get("content")
            )
        elif adapter == _MCP_ADAPTER:
            output, byte_length, relative_path = self._call_mcp(
                authorization.resource, values
            )
        else:
            raise ToolRuntimeError(
                "tool_runtime_unavailable", "Tool adapter is not installed"
            )
        receipt = {
            "tool_reference": authorization.tool_reference,
            "adapter": adapter,
            "permission": "allowed",
            "authorization": "allowed",
            "input_digest": authorization.input_digest,
            "output_digest": sha256_digest(output),
            "byte_length": byte_length,
            "relative_path": relative_path,
        }
        return ToolExecution(output=output, receipt=receipt)

    @staticmethod
    def _denied(
        reference: str | None,
        code: str,
        reason: str,
        values: dict[str, Any],
        resource: dict[str, Any] | None = None,
    ) -> ToolAuthorization:
        return ToolAuthorization(
            tool_reference=reference or "",
            adapter=(resource or {}).get("spec", {}).get("adapter"),
            decision="denied",
            code=code,
            reason=reason,
            input_digest=_input_digest(resource, values),
            approval_required=bool(
                (resource or {}).get("spec", {}).get("approval_required")
            ),
            resource=resource,
        )

    @staticmethod
    def _authorize(source: AgentSource, resource: dict[str, Any]) -> None:
        permissions = source.permissions
        required = resource["required_permissions"]
        if not set(required.get("tools", [])) <= set(permissions.tools):
            raise ToolRuntimeError(
                "tool_permission_denied", "Agent permissions do not include this Tool"
            )
        if not set(required.get("network_hosts", [])) <= set(permissions.network_hosts):
            raise ToolRuntimeError(
                "tool_permission_denied",
                "Agent permissions do not include required network access",
            )
        if not set(required.get("filesystem_read_roots", [])) <= set(
            permissions.filesystem_read_roots
        ):
            raise ToolRuntimeError(
                "tool_permission_denied",
                "Agent permissions do not include required file access",
            )
        if not set(required.get("filesystem_write_roots", [])) <= set(
            permissions.filesystem_write_roots
        ):
            raise ToolRuntimeError(
                "tool_permission_denied",
                "Agent permissions do not include required write access",
            )
        if (
            required.get("shell_workspace_only", False)
            and not permissions.shell_workspace_only
        ):
            raise ToolRuntimeError(
                "tool_permission_denied",
                "Agent permissions do not include required shell scope",
            )

    @classmethod
    def _read_project_file(
        cls, project_root: Path, raw_path: Any
    ) -> tuple[dict[str, Any], int, str]:
        target, relative_path = cls._project_target(
            project_root, raw_path, create_parents=False
        )
        if not target.is_file():
            raise ToolRuntimeError(
                "tool_input_invalid", "Tool path is not a regular file"
            )
        try:
            content = target.read_bytes()
        except OSError as exc:
            raise ToolRuntimeError(
                "tool_failed", "Tool could not read the Project file"
            ) from exc
        if len(content) > _MAX_FILE_BYTES:
            raise ToolRuntimeError(
                "tool_output_too_large", "Tool file exceeds the 1 MiB limit"
            )
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ToolRuntimeError(
                "tool_output_invalid", "Tool file is not UTF-8 text"
            ) from exc
        return {"content": text}, len(content), relative_path

    @classmethod
    def _write_project_file(
        cls, project_root: Path, raw_path: Any, raw_content: Any
    ) -> tuple[dict[str, Any], int, str]:
        if not isinstance(raw_content, str):
            raise ToolRuntimeError(
                "tool_input_invalid", "Filesystem Write requires UTF-8 text content"
            )
        encoded = raw_content.encode("utf-8")
        if len(encoded) > _MAX_FILE_BYTES:
            raise ToolRuntimeError(
                "tool_output_too_large", "Tool file exceeds the 1 MiB limit"
            )
        target, relative_path = cls._project_target(
            project_root, raw_path, create_parents=True
        )
        if target.exists() and not target.is_file():
            raise ToolRuntimeError(
                "tool_input_invalid", "Tool path is not a regular file"
            )
        try:
            target.write_bytes(encoded)
        except OSError as exc:
            raise ToolRuntimeError(
                "tool_failed", "Tool could not write the Project file"
            ) from exc
        return {"written": True}, len(encoded), relative_path

    def _call_mcp(
        self, resource: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any], int, str]:
        if self.mcp is None:
            raise ToolRuntimeError(
                "tool_runtime_unavailable", "MCP Runtime adapter is not installed"
            )
        spec = resource.get("spec") or {}
        server_id = spec.get("mcp_server_id")
        tool_name = spec.get("mcp_tool_name")
        if not isinstance(server_id, str) or not isinstance(tool_name, str):
            raise ToolRuntimeError(
                "tool_runtime_unavailable", "MCP tool descriptor is incomplete"
            )
        arguments = {
            name: values.get(name)
            for name in (spec.get("input_schema") or {})
            if name in values
        }
        try:
            result = self.mcp.call(server_id, tool_name, arguments)
        except McpError as exc:
            raise ToolRuntimeError(exc.code, str(exc)) from exc
        if result.get("isError"):
            raise ToolRuntimeError("mcp_tool_failed", "MCP tool returned an error")
        output = {"result": result}
        encoded = json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
        if len(encoded) > _MAX_FILE_BYTES:
            raise ToolRuntimeError(
                "tool_output_too_large", "MCP tool output exceeds the 1 MiB limit"
            )
        return output, len(encoded), ""

    @staticmethod
    def _project_target(
        project_root: Path, raw_path: Any, *, create_parents: bool
    ) -> tuple[Path, str]:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ToolRuntimeError(
                "tool_input_invalid", "Filesystem tool requires a relative path"
            )
        if "\x00" in raw_path or os.path.isabs(raw_path):
            raise ToolRuntimeError(
                "tool_path_denied", "Tool paths must be relative to the Project"
            )
        portable = PurePosixPath(raw_path)
        if portable.is_absolute() or any(
            part in {"", ".", ".."} for part in portable.parts
        ):
            raise ToolRuntimeError(
                "tool_path_denied", "Tool paths may not escape the Project directory"
            )
        relative_path = portable.as_posix()
        if any(
            part.lower() in _FORBIDDEN_NAMES
            or part.lower().endswith(_FORBIDDEN_SUFFIXES)
            for part in portable.parts
        ):
            raise ToolRuntimeError(
                "tool_path_denied", "Tool cannot access secret material"
            )
        root = project_root.expanduser().absolute()
        if root.is_symlink() or not root.is_dir():
            raise ToolRuntimeError(
                "project_unavailable", "Project directory is unavailable"
            )
        current = root
        parents = portable.parts[:-1]
        for part in parents:
            current = current / part
            if current.is_symlink():
                raise ToolRuntimeError(
                    "tool_path_denied", "Tool cannot follow Project symlinks"
                )
            if current.exists() and not current.is_dir():
                raise ToolRuntimeError(
                    "tool_path_denied", "Tool path parent is not a directory"
                )
            if create_parents and not current.exists():
                current.mkdir(parents=False, exist_ok=True)
        target = current / portable.name
        if target.is_symlink():
            raise ToolRuntimeError(
                "tool_path_denied", "Tool cannot follow Project symlinks"
            )
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ToolRuntimeError(
                "tool_path_denied", "Tool path is outside the Project directory"
            ) from exc
        return target, relative_path


def _input_digest(resource: dict[str, Any] | None, values: dict[str, Any]) -> str:
    schema = (resource or {}).get("spec", {}).get("input_schema") or {"path": "string"}
    material: dict[str, Any] = {}
    for name in schema:
        value = values.get(name)
        if name == "content" and isinstance(value, str):
            material[name] = sha256_digest(value)
        else:
            material[name] = value
    return sha256_digest(material)
