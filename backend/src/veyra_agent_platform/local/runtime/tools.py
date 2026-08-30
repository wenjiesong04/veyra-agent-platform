"""Safe, catalog-backed Tool Runtime adapters for local Agent runs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource, FlowNode
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceCatalogError

_MAX_READ_BYTES = 1_000_000
_FORBIDDEN_NAMES = {".env", "credentials.json", "id_rsa"}
_FORBIDDEN_SUFFIXES = {".key", ".pem", ".p12", ".token"}


class ToolRuntimeError(RuntimeError):
    """A typed, non-retriable Tool Runtime failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ToolExecution:
    output: dict[str, Any]
    receipt: dict[str, Any]


class ToolRuntime:
    """Resolve exact catalog references and execute only registered adapters."""

    def __init__(self, catalog: ResourceCatalog) -> None:
        self.catalog = catalog

    def execute(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
    ) -> ToolExecution:
        if node.uses is None:
            raise ToolRuntimeError(
                "tool_reference_missing", "Tool node has no uses reference"
            )
        try:
            resource_id, version = node.uses.rsplit("@", 1)
            resource = self.catalog.detail(resource_id, version)
        except (ValueError, ResourceCatalogError) as exc:
            raise ToolRuntimeError(
                "tool_not_registered", "Tool reference is not registered in the catalog"
            ) from exc
        if resource["kind"] not in {"tool", "mcp_tool"}:
            raise ToolRuntimeError(
                "tool_not_executable", "Resource is not an executable Tool"
            )
        if resource["availability"] != "ready":
            raise ToolRuntimeError(
                "tool_unavailable", "Tool is not ready for local execution"
            )
        if resource["runtime_status"] != "supported":
            raise ToolRuntimeError(
                "tool_runtime_unavailable", "Tool has no local Runtime adapter"
            )
        if source.lock.get(node.uses) != resource["content_hash"]:
            raise ToolRuntimeError(
                "tool_lock_invalid", "Tool lock does not match the catalog version"
            )
        self._authorize(source, resource)
        adapter = resource.get("spec", {}).get("adapter")
        input_digest = sha256_digest({"path": values.get("path")})
        if adapter == "veyra.runtime.filesystem.read":
            output, byte_length, relative_path = self._read_project_file(
                project_root, values.get("path")
            )
        else:
            raise ToolRuntimeError(
                "tool_runtime_unavailable", "Tool adapter is not installed"
            )
        receipt = {
            "tool_reference": node.uses,
            "adapter": adapter,
            "permission": "allowed",
            "input_digest": input_digest,
            "output_digest": sha256_digest(output),
            "byte_length": byte_length,
            "relative_path": relative_path,
        }
        return ToolExecution(output=output, receipt=receipt)

    @staticmethod
    def _authorize(source: AgentSource, resource: dict[str, Any]) -> None:
        resource_id = resource["resource_id"]
        permissions = source.permissions
        if resource_id not in permissions.tools:
            raise ToolRuntimeError(
                "tool_permission_denied", "Agent permissions do not include this Tool"
            )
        required = resource["required_permissions"]
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

    @staticmethod
    def _read_project_file(
        project_root: Path, raw_path: Any
    ) -> tuple[dict[str, str], int, str]:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ToolRuntimeError(
                "tool_input_invalid", "Read Project File requires a relative path"
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
            or part.lower().endswith(tuple(_FORBIDDEN_SUFFIXES))
            for part in portable.parts
        ):
            raise ToolRuntimeError(
                "tool_path_denied", "Tool cannot read secret material"
            )
        root = project_root.expanduser().absolute()
        if root.is_symlink() or not root.is_dir():
            raise ToolRuntimeError(
                "project_unavailable", "Project directory is unavailable"
            )
        current = root
        for part in portable.parts:
            current = current / part
            if current.is_symlink():
                raise ToolRuntimeError(
                    "tool_path_denied", "Tool cannot follow Project symlinks"
                )
        target = current
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ToolRuntimeError(
                "tool_path_denied", "Tool path is outside the Project directory"
            ) from exc
        if not target.is_file():
            raise ToolRuntimeError(
                "tool_input_invalid", "Tool path is not a regular file"
            )
        try:
            size = target.stat().st_size
            if size > _MAX_READ_BYTES:
                raise ToolRuntimeError(
                    "tool_output_too_large", "Tool file exceeds the 1 MiB limit"
                )
            content = target.read_bytes()
            if len(content) > _MAX_READ_BYTES:
                raise ToolRuntimeError(
                    "tool_output_too_large", "Tool file exceeds the 1 MiB limit"
                )
        except OSError as exc:
            raise ToolRuntimeError(
                "tool_failed", "Tool could not read the Project file"
            ) from exc
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ToolRuntimeError(
                "tool_output_invalid", "Tool file is not UTF-8 text"
            ) from exc
        return {"result": text}, len(content), relative_path
