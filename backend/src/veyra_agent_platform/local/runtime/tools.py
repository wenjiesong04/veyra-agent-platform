"""Safe, catalog-backed Tool Runtime adapters for local Agent runs."""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import unicodedata
from collections.abc import Mapping
from contextlib import suppress
from contextvars import ContextVar
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlsplit

import httpx

from veyra_agent_platform.contracts.agent import AgentSource, FlowNode
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.filesystem_scope import (
    NATIVE_PROJECT_FILESYSTEM_ADAPTERS,
    filesystem_roots_satisfied,
    path_in_project_scopes,
)
from veyra_agent_platform.local.mcp.execution import McpExecutionError, execute_call
from veyra_agent_platform.local.mcp.schema import McpSchemaError, require_contract
from veyra_agent_platform.local.mcp.service import McpService
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceCatalogError
from veyra_agent_platform.local.secrets import SecretStore, resolve_secret
from veyra_agent_platform.local.state import EntityStoreError
from veyra_agent_platform.local.state.entity_store import ENTITY_HISTORY_MAX_RECORDS

from .arithmetic import ArithmeticError, calculate
from .file_sources import ArtifactReader, FileSourceError, NativeFileSources
from .input_protection import (
    InputProtectionError,
    InputProtectionScope,
    InputProtectionStore,
)
from .tabular import TABULAR_MAX_FILE_BYTES, TabularError, compare_csv
from .tool_output_contract import (
    ToolOutputContractError,
    prepare_tool_output_contract,
    verify_tool_output_contract,
)

_MAX_FILE_BYTES = 1_000_000
_FORBIDDEN_NAMES = {".env", "credentials.json", "id_rsa"}
_FORBIDDEN_SUFFIXES = (".key", ".pem", ".p12", ".token")
_READ_ADAPTER = "veyra.runtime.filesystem.read"
_LIST_ADAPTER = "veyra.runtime.filesystem.list"
_FILESYSTEM_SEARCH_ADAPTER = "veyra.runtime.filesystem.search"
_WRITE_ADAPTER = "veyra.runtime.filesystem.write"
_SHELL_ADAPTER = "veyra.runtime.shell.exec"
_MCP_ADAPTER = "veyra.runtime.mcp.call"
_HTTP_ADAPTER = "veyra.runtime.http.request"
_BROWSER_ADAPTER = "veyra.runtime.browser.navigate"
_SEARCH_ADAPTER = "veyra.runtime.web.search"
_ENTITY_READ_ADAPTER = "veyra.runtime.entity.read"
_ENTITY_QUERY_ADAPTER = "veyra.runtime.entity.query"
_ENTITY_HISTORY_ADAPTER = "veyra.runtime.entity.history"
_ENTITY_WRITE_ADAPTER = "veyra.runtime.entity.write"
_ARITHMETIC_ADAPTER = "veyra.runtime.math.calculate"
_TABULAR_COMPARE_ADAPTER = "veyra.runtime.tabular.compare"
_GITHUB_READ_ADAPTER = "veyra.runtime.github.read"
_GITHUB_WRITE_ADAPTER = "veyra.runtime.github.write"
_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}
_MAX_SHELL_COMMAND_BYTES = 16_384
_MAX_SHELL_OUTPUT_BYTES = 1_000_000
_SHELL_TIMEOUT_SECONDS = 30
_BROWSER_MAX_REDIRECTS = 5
_BROWSER_MAX_TEXT_CHARS = 200_000
_BROWSER_USER_AGENT = "Veyra-Agent-Platform/0.1"
_SEARCH_MAX_QUERY_BYTES = 2_000
_SEARCH_MAX_RESULTS = 10


class ToolRuntimeError(RuntimeError):
    """A typed Tool Runtime failure safe to include in Run evidence."""

    def __init__(
        self, code: str, message: str, *, receipt: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.receipt = receipt
        self.recovery: Literal["observe"] | None = None


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
class ProducedArtifact:
    """Bytes produced by a Tool. Runtime persists them before graph values/events."""

    field: str
    filename: str
    contents: bytes
    claimed_type: str | None = None


@dataclass(frozen=True)
class ToolExecution:
    output: dict[str, Any]
    receipt: dict[str, Any]
    produced_artifacts: tuple[ProducedArtifact, ...] = ()


class ToolAdapter(Protocol):
    """An injectable Runtime adapter for one catalog `spec.adapter` value."""

    def __call__(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution: ...


class ToolRuntime:
    """Resolve exact catalog references and execute only registered adapters."""

    def __init__(
        self,
        catalog: ResourceCatalog,
        mcp: McpService | None = None,
        adapters: Mapping[str, ToolAdapter] | None = None,
        http_client: httpx.Client | None = None,
        secret_store: SecretStore | None = None,
        entity_store: Any | None = None,
        artifacts: ArtifactReader | None = None,
        input_protection: InputProtectionStore | None = None,
    ) -> None:
        self.catalog = catalog
        self.mcp = mcp
        self._http_client = http_client or httpx.Client(
            timeout=30.0, follow_redirects=False
        )
        self._secret_store = secret_store
        self._entity_store = entity_store
        self._artifacts = artifacts
        self.input_protection = input_protection
        self._call_input_protection: ContextVar[InputProtectionScope | None] = (
            ContextVar("veyra_tool_input_protection", default=None)
        )
        self._call_input_files: ContextVar[Mapping[str, Any] | None] = ContextVar(
            "veyra_tool_input_files", default=None
        )
        self._call_project_id: ContextVar[str | None] = ContextVar(
            "veyra_tool_project_id", default=None
        )
        self._adapters: dict[str, ToolAdapter] = {
            _READ_ADAPTER: self._execute_read,
            _LIST_ADAPTER: self._execute_list,
            _FILESYSTEM_SEARCH_ADAPTER: self._execute_search,
            _WRITE_ADAPTER: self._execute_write,
            _SHELL_ADAPTER: self._execute_shell,
            _MCP_ADAPTER: self._execute_mcp,
            _HTTP_ADAPTER: self._execute_http,
            _BROWSER_ADAPTER: self._execute_browser_navigate,
            _SEARCH_ADAPTER: self._execute_web_search,
            _ENTITY_READ_ADAPTER: self._execute_entity_read,
            _ENTITY_QUERY_ADAPTER: self._execute_entity_query,
            _ENTITY_HISTORY_ADAPTER: self._execute_entity_history,
            _ENTITY_WRITE_ADAPTER: self._execute_entity_write,
            _ARITHMETIC_ADAPTER: self._execute_arithmetic,
            _TABULAR_COMPARE_ADAPTER: self._execute_tabular_compare,
            _GITHUB_READ_ADAPTER: self._execute_github_read,
            _GITHUB_WRITE_ADAPTER: self._execute_github_write,
        }
        if adapters:
            self._adapters.update(adapters)

    def authorize(
        self,
        *,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        resource: dict[str, Any] | None = None,
    ) -> ToolAuthorization:
        if node.uses is None:
            return self._denied(
                None,
                "tool_reference_missing",
                "Tool node has no uses reference",
                values,
            )
        try:
            if resource is None:
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
            reasons = resource.get("blocking_reasons", [])
            code = (
                reasons[0]["code"]
                if resource["availability"] == "requires_configuration" and reasons
                else "tool_unavailable"
            )
            return self._denied(
                node.uses,
                code,
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
        if (
            resource["reference"] != node.uses
            or source.lock.get(node.uses) != resource["content_hash"]
        ):
            return self._denied(
                node.uses,
                "tool_lock_invalid",
                "Tool lock does not match the catalog version",
                values,
                resource,
            )
        spec = resource.get("spec", {})
        if resource.get("origin") == "discovered" and (
            resource.get("factory_selectable") is not True
            or spec.get("review_required") is True
        ):
            return self._denied(
                node.uses,
                "mcp_tool_review_required",
                "Discovered MCP tools must be reviewed before execution",
                values,
                resource,
            )
        try:
            self._authorize(source, resource)
        except ToolRuntimeError as exc:
            return self._denied(node.uses, exc.code, str(exc), values, resource)
        adapter = spec.get("adapter")
        if not isinstance(adapter, str) or adapter not in self._adapters:
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
        if adapter == _MCP_ADAPTER:
            try:
                require_contract(spec)
            except McpSchemaError as exc:
                return self._denied(
                    node.uses,
                    exc.code,
                    "MCP requires a supported, reviewed schema contract",
                    values,
                    resource,
                )
        secret_ref = spec.get("secret_ref")
        secret_env = spec.get("secret_env")
        if secret_ref:
            if not isinstance(secret_ref, str) or secret_ref not in source.secret_refs:
                return self._denied(
                    node.uses,
                    "secret_ref_missing",
                    "Agent does not declare the Tool secret reference",
                    values,
                    resource,
                )
            if not isinstance(secret_env, str) or not self._secret_value(
                secret_ref, secret_env
            ):
                return self._denied(
                    node.uses,
                    "secret_not_configured",
                    "Tool secret is not configured on the host",
                    values,
                    resource,
                )
        authorization = ToolAuthorization(
            tool_reference=node.uses,
            adapter=str(adapter),
            decision="allowed",
            code="allowed",
            reason="catalog permission subset matched",
            input_digest=_input_digest(resource, values),
            approval_required=bool(resource.get("spec", {}).get("approval_required")),
            resource=resource,
        )
        try:
            self._check_native_filesystem_scope(
                source, authorization, values, allow_missing=True
            )
        except ToolRuntimeError as exc:
            return self._denied(node.uses, exc.code, str(exc), values, resource)
        return authorization

    def execute(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
        project_id: str | None = None,
        input_files: Mapping[str, Any] | None = None,
        input_protection_scope: InputProtectionScope | None = None,
    ) -> ToolExecution:
        if source.permissions.protect_input_files and input_protection_scope is None:
            raise ToolRuntimeError(
                "input_protection_unavailable",
                "Protected execution requires a Run scope",
            )
        token = self._call_project_id.set(project_id)
        files_token = self._call_input_files.set(dict(input_files or {}))
        protection_token = self._call_input_protection.set(input_protection_scope)
        try:
            return self._execute_authorized(
                project_root=project_root,
                source=source,
                node=node,
                values=values,
                authorization=authorization,
                approved=approved,
            )
        finally:
            self._call_project_id.reset(token)
            self._call_input_files.reset(files_token)
            self._call_input_protection.reset(protection_token)

    def _execute_authorized(
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
        if authorization.adapter is None:
            raise ToolRuntimeError(
                "tool_runtime_unavailable", "Tool adapter is not installed"
            )
        adapter = self._adapters.get(authorization.adapter)
        if adapter is None:
            raise ToolRuntimeError(
                "tool_runtime_unavailable", "Tool adapter is not installed"
            )
        try:
            output_contract = prepare_tool_output_contract(
                authorization.resource.get("spec") or {}
            )
        except ToolOutputContractError as exc:
            raise ToolRuntimeError(
                exc.code, "Tool output contract is invalid or unsupported"
            ) from None
        try:
            if self._call_input_protection.get() is not None:
                self._require_protection_adapter(authorization.adapter)
            self._check_native_filesystem_scope(source, authorization, values)
            execution = adapter(
                project_root=project_root,
                source=source,
                node=node,
                values=values,
                authorization=authorization,
                approved=approved,
            )
            try:
                verification = verify_tool_output_contract(
                    output_contract, execution.output
                )
            except ToolOutputContractError as exc:
                receipt = {
                    **execution.receipt,
                    "outcome": "failed",
                    "code": exc.code,
                    "output_verification": exc.verification,
                }
                raise ToolRuntimeError(
                    exc.code,
                    "Tool result does not match its declared output contract",
                    receipt=receipt,
                ) from None
            if verification is not None:
                execution = replace(
                    execution,
                    receipt={
                        **execution.receipt,
                        "output_verification": verification,
                    },
                )
            return execution
        except InputProtectionError as exc:
            raise ToolRuntimeError(exc.code, str(exc)) from None
        except ToolRuntimeError as exc:
            # A matching error code cannot establish what an injected adapter did.
            trusted_read = self._is_native_observer(adapter)
            recoverable_code = exc.code in {
                "tool_input_invalid",
                "tool_failed",
                "tool_timeout",
                "tool_output_invalid",
                "tool_output_too_large",
                "tool_redirect_limit",
                "native_file_source_invalid",
                "native_file_input_unavailable",
                "native_file_unavailable",
                "tabular_input_invalid",
                "tabular_output_too_large",
                "tabular_file_too_large",
                "tabular_csv_invalid",
                "tabular_rows_exceeded",
                "tabular_cell_too_large",
                "tabular_amount_invalid",
            }
            exc.recovery = "observe" if trusted_read and recoverable_code else None
            if exc.recovery:
                receipt = self._receipt_execution(authorization, {}, 0, "").receipt
                receipt.update(exc.receipt or {})
                receipt.update(outcome="failed", code=exc.code, recovery=exc.recovery)
                exc.receipt = receipt
            raise

    def can_refresh_observation(self, authorization: ToolAuthorization) -> bool:
        """Only native observer implementations can safely refresh unchanged input."""
        return self._is_native_observer(self._adapters.get(authorization.adapter or ""))

    def can_batch_observation(self, authorization: ToolAuthorization) -> bool:
        """Only platform-owned local observations can share a model turn."""
        return self._is_native_observer(
            self._adapters.get(authorization.adapter or ""), local_only=True
        )

    def _is_native_observer(self, adapter: Any, *, local_only: bool = False) -> bool:
        if getattr(adapter, "__self__", None) is not self:
            return False
        method = getattr(adapter, "__func__", None)
        return method in {
            ToolRuntime._execute_read,
            ToolRuntime._execute_list,
            ToolRuntime._execute_search,
            ToolRuntime._execute_entity_read,
            ToolRuntime._execute_entity_query,
            ToolRuntime._execute_entity_history,
            ToolRuntime._execute_arithmetic,
            ToolRuntime._execute_tabular_compare,
        } or (
            not local_only
            and method
            in {
                ToolRuntime._execute_browser_navigate,
                ToolRuntime._execute_web_search,
                ToolRuntime._execute_github_read,
            }
        )

    def protection_scope(
        self, project_id: str, run_kind: str, run_id: str
    ) -> InputProtectionScope | None:
        if self.input_protection is None:
            return None
        try:
            return self.input_protection.scope_for_run(project_id, run_kind, run_id)
        except InputProtectionError as exc:
            raise ToolRuntimeError(exc.code, str(exc)) from None

    def protect_inputs(
        self,
        project_id: str,
        project_root: Path,
        source: Any,
        inputs: Mapping[str, Any],
        scope: InputProtectionScope | None,
    ) -> None:
        if scope is None:
            return
        if self.input_protection is None:
            raise ToolRuntimeError(
                "input_protection_unavailable", "Input protection is unavailable"
            )
        try:
            self.input_protection.validate_scope(scope)
            for reference in source.lock:
                if reference.rsplit("@", 1)[0] not in source.permissions.tools:
                    continue
                resource = self.catalog.detail(*reference.rsplit("@", 1))
                self._require_protection_adapter(
                    resource.get("spec", {}).get("adapter")
                )
            for name in source.permissions.protected_input_fields:
                path = inputs.get(name)
                if path is None or source.inputs[name].is_artifact():
                    # Typed artifacts are immutable objects, not Project paths.
                    continue
                if not path_in_project_scopes(
                    path, source.permissions.filesystem_read_roots
                ):
                    raise ToolRuntimeError(
                        "tool_path_denied",
                        "Protected input is outside the filesystem read scope",
                    )
                NativeFileSources(
                    project_id=project_id,
                    project_target=lambda value: self._project_target(
                        project_root, value, create_parents=False
                    ),
                    selected_inputs={},
                    on_project_read=lambda target,
                    metadata,
                    payload: self.input_protection.protect_project_file(  # type: ignore[union-attr]
                        scope, project_root, target, metadata, payload
                    ),
                ).read({"path": path}, TABULAR_MAX_FILE_BYTES)
        except (InputProtectionError, FileSourceError, ResourceCatalogError) as exc:
            raise ToolRuntimeError(
                getattr(exc, "code", "input_protection_invalid"), str(exc)
            ) from None

    def _require_protection_adapter(self, adapter_name: Any) -> None:
        adapter = (
            self._adapters.get(adapter_name) if isinstance(adapter_name, str) else None
        )
        if (
            adapter is None
            or getattr(adapter, "__self__", None) is not self
            or adapter_name in {_SHELL_ADAPTER, _MCP_ADAPTER}
            or getattr(adapter, "__func__", None)
            not in {
                ToolRuntime._execute_read,
                ToolRuntime._execute_list,
                ToolRuntime._execute_search,
                ToolRuntime._execute_write,
                ToolRuntime._execute_http,
                ToolRuntime._execute_browser_navigate,
                ToolRuntime._execute_web_search,
                ToolRuntime._execute_entity_read,
                ToolRuntime._execute_entity_query,
                ToolRuntime._execute_entity_history,
                ToolRuntime._execute_entity_write,
                ToolRuntime._execute_arithmetic,
                ToolRuntime._execute_tabular_compare,
                ToolRuntime._execute_github_read,
                ToolRuntime._execute_github_write,
            }
        ):
            raise ToolRuntimeError(
                "input_protection_not_enforceable",
                "This Tool cannot enforce the Run's protected Project inputs",
            )

    def _protect_read(
        self, project_root: Path, path: Path, metadata: os.stat_result, payload: bytes
    ) -> None:
        scope = self._call_input_protection.get()
        if scope is None:
            return
        if self.input_protection is None:
            raise ToolRuntimeError(
                "input_protection_unavailable", "Input protection is unavailable"
            )
        self.input_protection.protect_project_file(
            scope, project_root, path, metadata, payload
        )

    @staticmethod
    def _check_native_filesystem_scope(
        source: AgentSource,
        authorization: ToolAuthorization,
        values: Mapping[str, Any],
        *,
        allow_missing: bool = False,
    ) -> None:
        adapter = authorization.adapter
        if adapter not in NATIVE_PROJECT_FILESYSTEM_ADAPTERS:
            return
        write = adapter == _WRITE_ADAPTER
        scopes = (
            source.permissions.filesystem_write_roots
            if write
            else source.permissions.filesystem_read_roots
        )
        directory = adapter in {_LIST_ADAPTER, _FILESYSTEM_SEARCH_ADAPTER}
        if adapter == _TABULAR_COMPARE_ADAPTER:
            paths = []
            uses_sources = "left_source" in (authorization.resource or {}).get(
                "spec", {}
            ).get("input_schema", {})
            for side in ("left", "right"):
                raw = (
                    values.get(side + "_source")
                    if uses_sources
                    else {"path": values.get(side + "_path")}
                )
                if isinstance(raw, Mapping) and set(raw) == {"input"}:
                    continue
                paths.append(raw.get("path") if isinstance(raw, Mapping) else None)
            paths = [
                unicodedata.normalize("NFKC", path) if isinstance(path, str) else path
                for path in paths
            ]
        else:
            paths = [_wrapper_project_path(authorization, values.get("path"))]
        for path in paths:
            # Catalog readiness uses no arguments, and the Agent loop repairs
            # malformed argument types offline before adapter dispatch.
            if allow_missing and (not isinstance(path, str) or not path.strip()):
                continue
            if directory and path is None:
                path = "."
            if not isinstance(path, str) or (not path.strip() and not directory):
                raise ToolRuntimeError(
                    "tool_input_invalid", "Filesystem Tool requires a relative path"
                )
            try:
                allowed = path_in_project_scopes(path, scopes, allow_root=directory)
            except ContractValidationError as exc:
                raise ToolRuntimeError(
                    "tool_path_denied", "Tool path is not a safe Project path"
                ) from exc
            if not allowed:
                raise ToolRuntimeError(
                    "tool_path_denied",
                    "Tool path is outside the Agent filesystem scope",
                )

    def _execute_read(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del source, node, approved
        path = _wrapper_project_path(authorization, values.get("path"))
        output, byte_length, relative_path = self._read_project_file(project_root, path)
        return self._receipt_execution(
            authorization, output, byte_length, relative_path
        )

    def _execute_write(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del source, node, approved
        output, byte_length, relative_path = self._write_project_file(
            project_root, values.get("path"), values.get("content")
        )
        return self._receipt_execution(
            authorization, output, byte_length, relative_path
        )

    def _execute_entity_read(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del project_root, node, approved
        store = self._entity_store
        project_id = self._call_project_id.get() or str(values.get("project_id") or "")
        entity_id = values.get("entity_id")
        if store is None or not project_id or not isinstance(entity_id, str):
            raise ToolRuntimeError(
                "tool_input_invalid", "Entity Read requires a project entity"
            )
        record = store.read(project_id, entity_id)
        if record is None:
            raise ToolRuntimeError("tool_failed", "Entity was not found")
        state_contract = getattr(source, "state_contract", None)
        if (
            state_contract is not None
            and record["entity_type"] != state_contract.entity
        ):
            raise ToolRuntimeError(
                "tool_scope_denied", "Entity type is outside the Agent state contract"
            )
        return self._receipt_execution(authorization, record, 0, "")

    def _execute_entity_write(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del project_root, source, node, approved
        store = self._entity_store
        project_id = self._call_project_id.get() or str(values.get("project_id") or "")
        entity_type = str(values.get("entity_type") or "ProjectEntity")
        payload = values.get("payload")
        status = str(values.get("status") or "active")
        entity_id = values.get("entity_id")
        if store is None or not project_id or not isinstance(payload, dict):
            raise ToolRuntimeError(
                "tool_input_invalid", "Entity Write requires a payload object"
            )
        try:
            record = store.write(
                project_id=project_id,
                entity_type=entity_type,
                payload=payload,
                status=status,
                entity_id=(
                    entity_id if isinstance(entity_id, str) and entity_id else None
                ),
                source="tool",
            )
        except EntityStoreError as exc:
            raise ToolRuntimeError("tool_input_invalid", str(exc)) from exc
        return self._receipt_execution(authorization, record, 0, "")

    def _execute_entity_query(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del project_root, source, node, approved
        store = self._entity_store
        # A model argument cannot select another Project or infer host scope.
        project_id = self._call_project_id.get()
        if store is None or not project_id:
            raise ToolRuntimeError(
                "tool_input_invalid", "Entity Query requires the current Project"
            )
        try:
            result = store.query(
                project_id=project_id,
                entity_type=values.get("entity_type"),
                filters=values.get("filters"),
                limit=values.get("limit", 20),
            )
        except EntityStoreError as exc:
            raise ToolRuntimeError("tool_input_invalid", str(exc)) from exc
        byte_length = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        return self._receipt_execution(authorization, result, byte_length, "")

    def _execute_entity_history(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del project_root, node, approved
        store = self._entity_store
        project_id = self._call_project_id.get()
        if store is None or not project_id:
            raise ToolRuntimeError(
                "tool_input_invalid", "Entity History requires the current Project"
            )
        entity_type = values.get("entity_type")
        state_contract = getattr(source, "state_contract", None)
        if state_contract is not None and entity_type != state_contract.entity:
            raise ToolRuntimeError(
                "tool_scope_denied", "Entity type is outside the Agent state contract"
            )
        try:
            result = store.history(
                project_id=project_id,
                entity_type=entity_type,
                entity_id=values.get("entity_id"),
                limit=values.get("limit", ENTITY_HISTORY_MAX_RECORDS),
                before_revision=values.get("before_revision"),
            )
        except EntityStoreError as exc:
            raise ToolRuntimeError("tool_input_invalid", str(exc)) from exc
        if result is None:
            raise ToolRuntimeError("tool_failed", "Entity history was not found")
        byte_length = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        return self._receipt_execution(authorization, result, byte_length, "")

    def _execute_arithmetic(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del project_root, source, node, approved
        try:
            output = calculate(values.get("expression"))
        except ArithmeticError as exc:
            from .tool_input_contract import ToolInputIssue

            issue = ToolInputIssue(
                str(exc),
                (
                    {
                        "category": "arithmetic_expression",
                        "location": "/arguments/expression",
                    },
                ),
            )
            raise ToolRuntimeError(
                "tool_input_invalid", str(exc), receipt={"diagnostic": issue.to_dict()}
            ) from exc
        return self._receipt_execution(
            authorization, output, len(json.dumps(output).encode("utf-8")), ""
        )

    def _execute_tabular_compare(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del source, node, approved
        reader = NativeFileSources(
            project_id=self._call_project_id.get() or "",
            project_target=lambda path: self._project_target(
                project_root, unicodedata.normalize("NFKC", path), create_parents=False
            ),
            selected_inputs=self._call_input_files.get() or {},
            artifacts=self._artifacts,
            on_project_read=lambda path, metadata, payload: self._protect_read(
                project_root, path, metadata, payload
            ),
        )
        uses_sources = "left_source" in (authorization.resource or {}).get(
            "spec", {}
        ).get("input_schema", {})
        try:
            materials = []
            for side in ("left", "right"):
                selected = (
                    values.get(side + "_source")
                    if uses_sources
                    else {"path": values.get(side + "_path")}
                )
                materials.append(
                    reader.read(
                        selected if isinstance(selected, Mapping) else {},
                        TABULAR_MAX_FILE_BYTES,
                    )
                )
        except FileSourceError as exc:
            if exc.code == "native_file_too_large":
                raise ToolRuntimeError(
                    "tool_output_too_large", "CSV file exceeds the 1 MB limit"
                ) from exc
            raise ToolRuntimeError(exc.code, str(exc)) from exc
        try:
            output = compare_csv(
                materials[0][0],
                materials[1][0],
                left_path=materials[0][1],
                right_path=materials[1][1],
                left_key=values.get("left_key"),
                right_key=values.get("right_key"),
                left_amount=values.get("left_amount"),
                right_amount=values.get("right_amount"),
                include_all_groups=values.get("include_all_groups", False),
            )
        except TabularError as exc:
            raise ToolRuntimeError(exc.code, str(exc)) from exc
        return self._receipt_execution(
            authorization,
            output,
            sum(len(content) for content, _ in materials),
            f"{materials[0][1]} | {materials[1][1]}",
        )

    def _execute_shell(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del source, node, approved
        command = values.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ToolRuntimeError(
                "tool_input_invalid", "Workspace Shell requires a command"
            )
        if "\x00" in command or len(command.encode("utf-8")) > _MAX_SHELL_COMMAND_BYTES:
            raise ToolRuntimeError(
                "tool_input_invalid", "Workspace Shell command is invalid or too large"
            )
        if not project_root.is_dir():
            raise ToolRuntimeError(
                "tool_input_invalid", "Workspace Shell project root is unavailable"
            )
        shell = "cmd.exe" if os.name == "nt" else "/bin/sh"
        shell_args = (
            [shell, "/d", "/s", "/c", command]
            if os.name == "nt"
            else [shell, "-c", command]
        )
        try:
            process = subprocess.Popen(
                shell_args,
                cwd=project_root,
                env=_shell_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=os.name != "nt",
            )
        except OSError as exc:
            raise ToolRuntimeError(
                "tool_failed", "Workspace Shell could not start"
            ) from exc
        try:
            stdout, stderr = process.communicate(timeout=_SHELL_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            if os.name == "nt":
                process.kill()
            else:
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise ToolRuntimeError(
                "tool_timeout", "Workspace Shell exceeded the 30 second limit"
            ) from exc
        output_bytes = stdout + stderr
        if len(output_bytes) > _MAX_SHELL_OUTPUT_BYTES:
            raise ToolRuntimeError(
                "tool_output_too_large",
                "Workspace Shell output exceeds the 1 MiB limit",
            )
        output = {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "exit_code": process.returncode,
        }
        return self._receipt_execution(authorization, output, len(output_bytes), ".")

    def _execute_list(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del source, node, approved
        path = _wrapper_project_path(authorization, values.get("path"))
        output, byte_length, relative_path = self._list_project_directory(
            project_root, path
        )
        return self._receipt_execution(
            authorization, output, byte_length, relative_path
        )

    def _execute_search(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del source, node, approved
        path = _wrapper_project_path(authorization, values.get("path"))
        output, byte_length, relative_path = self._search_project_files(
            project_root, path, values.get("query")
        )
        return self._receipt_execution(
            authorization, output, byte_length, relative_path
        )

    def _execute_mcp(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del project_root, source, node, approved
        if self.mcp is None:
            raise ToolRuntimeError("tool_runtime_unavailable", "MCP is not configured")
        receipt = self._receipt_execution(authorization, {}, 0, "").receipt
        try:
            output, receipt = execute_call(
                self.mcp,
                (authorization.resource or {}).get("spec", {}),
                values,
                receipt,
            )
        except McpExecutionError as exc:
            raise ToolRuntimeError(exc.code, str(exc), receipt=exc.receipt) from None
        return ToolExecution(output=output, receipt=receipt)

    def _execute_http(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del project_root, source, approved
        values = _http_wrapper_values(authorization, values)
        method = values.get("method")
        raw_url = values.get("url")
        body = values.get("body")
        spec = _wrapper_spec(authorization)
        if not isinstance(method, str) or method.upper() not in _HTTP_METHODS:
            raise ToolRuntimeError("tool_input_invalid", "HTTP method is not supported")
        if spec and spec.get("methods"):
            allowed_methods = {
                item.upper() for item in spec["methods"] if isinstance(item, str)
            }
            if method.upper() not in allowed_methods:
                raise ToolRuntimeError(
                    "tool_network_denied",
                    "HTTP method is outside the wrapper allowlist",
                )
        if not isinstance(raw_url, str) or not raw_url.strip():
            raise ToolRuntimeError("tool_input_invalid", "HTTP URL is required")
        parsed = urlsplit(raw_url)
        host = parsed.hostname
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or parsed.username
            or parsed.password
        ):
            raise ToolRuntimeError(
                "tool_network_denied", "HTTP URL is invalid or contains credentials"
            )
        allowed_hosts = {item.lower() for item in (node.network_hosts or ())}
        if spec.get("allowed_hosts"):
            allowed_hosts |= {
                str(item).lower()
                for item in spec["allowed_hosts"]
                if isinstance(item, str)
            }
        if host.lower() not in allowed_hosts:
            raise ToolRuntimeError(
                "tool_network_denied",
                "HTTP host must be explicitly listed on the Tool node",
            )
        path_prefix = str(spec.get("path_prefix") or "")
        if path_prefix:
            allowed = path_prefix.rstrip("/")
            if parsed.path != path_prefix and not parsed.path.startswith(allowed + "/"):
                raise ToolRuntimeError(
                    "tool_network_denied",
                    "HTTP path is outside the wrapper route boundary",
                )
        if body is not None and not isinstance(body, str):
            raise ToolRuntimeError("tool_input_invalid", "HTTP body must be text")
        timeout_ms = spec.get("timeout_ms")
        timeout = (
            timeout_ms / 1000.0
            if isinstance(timeout_ms, int) and timeout_ms > 0
            else None
        )
        max_bytes = spec.get("max_response_bytes")
        limit = (
            max_bytes
            if isinstance(max_bytes, int) and max_bytes > 0
            else _MAX_FILE_BYTES
        )
        limit = min(limit, _MAX_FILE_BYTES)
        try:
            response = self._http_client.request(
                method.upper(),
                raw_url,
                content=body,
                follow_redirects=False,
                timeout=timeout,
            )
            content = response.content
        except httpx.TimeoutException as exc:
            raise ToolRuntimeError("tool_timeout", "HTTP request timed out") from exc
        except httpx.HTTPError as exc:
            raise ToolRuntimeError("tool_failed", "HTTP request failed") from exc
        if len(content) > limit:
            raise ToolRuntimeError(
                "tool_output_too_large", "HTTP response exceeds the 1 MiB limit"
            )
        output = {
            "status": response.status_code,
            "body": content.decode("utf-8", errors="replace"),
        }
        return self._receipt_execution(
            authorization, output, len(content), host.lower()
        )

    def _execute_browser_navigate(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del project_root, source, approved
        raw_url = values.get("url")
        if not isinstance(raw_url, str) or not raw_url.strip():
            raise ToolRuntimeError(
                "tool_input_invalid", "Browser Navigate URL is required"
            )
        allowed_hosts = {item.lower() for item in (node.network_hosts or ())}
        current_url = self._browser_url(raw_url, allowed_hosts)
        response: httpx.Response | None = None
        redirects = 0
        for _ in range(_BROWSER_MAX_REDIRECTS + 1):
            try:
                response = self._http_client.get(
                    current_url,
                    headers={
                        "Accept": (
                            "text/html, text/plain, application/json;q=0.9, */*;q=0.1"
                        ),
                        "User-Agent": _BROWSER_USER_AGENT,
                    },
                    follow_redirects=False,
                )
            except httpx.TimeoutException as exc:
                raise ToolRuntimeError(
                    "tool_timeout", "Browser Navigate request timed out"
                ) from exc
            except httpx.HTTPError as exc:
                raise ToolRuntimeError(
                    "tool_failed", "Browser Navigate request failed"
                ) from exc
            location = response.headers.get("location")
            if response.status_code not in {301, 302, 303, 307, 308} or not location:
                break
            redirects += 1
            if redirects > _BROWSER_MAX_REDIRECTS:
                raise ToolRuntimeError(
                    "tool_redirect_limit",
                    "Browser Navigate followed too many redirects",
                )
            current_url = self._browser_url(
                urljoin(current_url, location), allowed_hosts
            )
        if response is None:
            raise ToolRuntimeError(
                "tool_failed", "Browser Navigate returned no response"
            )
        content = response.content
        if len(content) > _MAX_FILE_BYTES:
            raise ToolRuntimeError(
                "tool_output_too_large", "Browser page exceeds the 1 MiB limit"
            )
        page_text = content.decode(response.encoding or "utf-8", errors="replace")
        document = _browser_document(
            page_text, str(response.url), response.headers.get("content-type", "")
        )
        output = {
            "url": str(response.url),
            "status": response.status_code,
            "title": document["title"],
            "text": document["text"],
            "links": document["links"],
            "redirects": redirects,
            "truncated": document["truncated"],
        }
        encoded = json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
        if len(encoded) > _MAX_FILE_BYTES:
            raise ToolRuntimeError(
                "tool_output_too_large",
                "Browser page extraction exceeds the 1 MiB limit",
            )
        host = response.url.host or ""
        return self._receipt_execution(
            authorization, output, len(content), host.lower()
        )

    def _execute_web_search(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del project_root, source, node, approved
        raw_query = values.get("query")
        if (
            not isinstance(raw_query, str)
            or not raw_query.strip()
            or len(raw_query.encode("utf-8")) > _SEARCH_MAX_QUERY_BYTES
        ):
            raise ToolRuntimeError(
                "tool_input_invalid", "Web Search query is required and must be short"
            )
        raw_count = values.get("count", 5)
        if (
            isinstance(raw_count, bool)
            or not isinstance(raw_count, int)
            or not 1 <= raw_count <= _SEARCH_MAX_RESULTS
        ):
            raise ToolRuntimeError(
                "tool_input_invalid",
                f"Web Search count must be between 1 and {_SEARCH_MAX_RESULTS}",
            )
        query = raw_query.strip()
        search_url = "https://html.duckduckgo.com/html/?" + urlencode({"q": query})
        try:
            response = self._http_client.get(
                search_url,
                headers={
                    "Accept": "text/html",
                    "User-Agent": _BROWSER_USER_AGENT,
                },
                follow_redirects=False,
            )
            content = response.content
        except httpx.TimeoutException as exc:
            raise ToolRuntimeError(
                "tool_timeout", "Web Search request timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise ToolRuntimeError("tool_failed", "Web Search request failed") from exc
        if len(content) > _MAX_FILE_BYTES:
            raise ToolRuntimeError(
                "tool_output_too_large", "Web Search response exceeds the 1 MiB limit"
            )
        if response.status_code >= 400:
            raise ToolRuntimeError(
                "tool_failed", "Web Search provider returned an error"
            )
        parser = _SearchResultParser()
        parser.feed(content.decode(response.encoding or "utf-8", errors="replace"))
        parser.close()
        results = parser.results[:raw_count]
        output = {
            "provider": "duckduckgo",
            "query": query,
            "results": results,
            "status": response.status_code,
        }
        encoded = json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
        if len(encoded) > _MAX_FILE_BYTES:
            raise ToolRuntimeError(
                "tool_output_too_large", "Web Search results exceed the 1 MiB limit"
            )
        return self._receipt_execution(
            authorization, output, len(content), "html.duckduckgo.com"
        )

    @staticmethod
    def _browser_url(raw_url: str, allowed_hosts: set[str]) -> str:
        parsed = urlsplit(raw_url)
        host = parsed.hostname
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or parsed.username
            or parsed.password
        ):
            raise ToolRuntimeError(
                "tool_network_denied",
                "Browser URL is invalid or contains credentials",
            )
        if host.lower() not in allowed_hosts:
            raise ToolRuntimeError(
                "tool_network_denied",
                "Browser host must be explicitly listed on the Tool node",
            )
        return raw_url.strip()

    def _execute_github_read(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del project_root, source, node, approved
        resource = authorization.resource or {}
        spec = resource.get("spec") or {}
        path = values.get("path")
        secret_env = spec.get("secret_env")
        if (
            not isinstance(path, str)
            or not path.startswith("/repos/")
            or ".." in path
            or "//" in path
        ):
            raise ToolRuntimeError(
                "tool_input_invalid", "GitHub path must be a repository API path"
            )
        if not isinstance(secret_env, str):
            raise ToolRuntimeError(
                "secret_not_configured", "GitHub secret environment is missing"
            )
        token = self._secret_value(spec.get("secret_ref"), secret_env)
        if not token:
            raise ToolRuntimeError(
                "secret_not_configured", "GitHub token is not configured"
            )
        try:
            response = self._http_client.get(
                f"https://api.github.com{path}",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            content = response.content
        except httpx.TimeoutException as exc:
            raise ToolRuntimeError("tool_timeout", "GitHub request timed out") from exc
        except httpx.HTTPError as exc:
            raise ToolRuntimeError("tool_failed", "GitHub request failed") from exc
        if len(content) > _MAX_FILE_BYTES:
            raise ToolRuntimeError(
                "tool_output_too_large", "GitHub response exceeds the 1 MiB limit"
            )
        output = {
            "status": response.status_code,
            "body": content.decode("utf-8", errors="replace"),
        }
        return self._receipt_execution(
            authorization, output, len(content), "api.github.com"
        )

    def _execute_github_write(
        self,
        *,
        project_root: Path,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
        authorization: ToolAuthorization,
        approved: bool,
    ) -> ToolExecution:
        del project_root, source, node, approved
        resource = authorization.resource or {}
        spec = resource.get("spec") or {}
        path = values.get("path")
        method = values.get("method", "POST")
        body = values.get("body")
        secret_env = spec.get("secret_env")
        if (
            not isinstance(path, str)
            or not path.startswith("/repos/")
            or ".." in path
            or "//" in path
        ):
            raise ToolRuntimeError(
                "tool_input_invalid", "GitHub path must be a repository API path"
            )
        if not isinstance(method, str) or method.upper() not in {
            "POST",
            "PATCH",
            "PUT",
        }:
            raise ToolRuntimeError(
                "tool_input_invalid", "GitHub write method is not supported"
            )
        if not isinstance(body, str) or not body.strip():
            raise ToolRuntimeError(
                "tool_input_invalid", "GitHub write body is required"
            )
        if not isinstance(secret_env, str):
            raise ToolRuntimeError(
                "secret_not_configured", "GitHub secret environment is missing"
            )
        token = self._secret_value(spec.get("secret_ref"), secret_env)
        if not token:
            raise ToolRuntimeError(
                "secret_not_configured", "GitHub token is not configured"
            )
        try:
            response = self._http_client.request(
                method.upper(),
                f"https://api.github.com{path}",
                content=body,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            content = response.content
        except httpx.TimeoutException as exc:
            raise ToolRuntimeError("tool_timeout", "GitHub request timed out") from exc
        except httpx.HTTPError as exc:
            raise ToolRuntimeError("tool_failed", "GitHub request failed") from exc
        if len(content) > _MAX_FILE_BYTES:
            raise ToolRuntimeError(
                "tool_output_too_large", "GitHub response exceeds the 1 MiB limit"
            )
        output = {
            "status": response.status_code,
            "body": content.decode("utf-8", errors="replace"),
        }
        return self._receipt_execution(
            authorization, output, len(content), "api.github.com"
        )

    def _secret_value(self, secret_ref: Any, env_name: str) -> str:
        return resolve_secret(
            self._secret_store,
            secret_ref if isinstance(secret_ref, str) else "",
            env_name,
        )

    @staticmethod
    def _receipt_execution(
        authorization: ToolAuthorization,
        output: dict[str, Any],
        byte_length: int,
        relative_path: str,
    ) -> ToolExecution:
        receipt = {
            "tool_reference": authorization.tool_reference,
            "adapter": authorization.adapter,
            "permission": "allowed",
            "authorization": "allowed",
            "input_digest": authorization.input_digest,
            "output_digest": sha256_digest(output),
            "byte_length": byte_length,
            "relative_path": relative_path,
        }
        receipt.update(_wrapper_receipt(authorization))
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
        native = (
            resource.get("spec", {}).get("adapter")
            in NATIVE_PROJECT_FILESYSTEM_ADAPTERS
        )
        if not filesystem_roots_satisfied(
            required.get("filesystem_read_roots", []),
            permissions.filesystem_read_roots,
            allow_subscopes=native,
        ):
            raise ToolRuntimeError(
                "tool_permission_denied",
                "Agent permissions do not include required file access",
            )
        if not filesystem_roots_satisfied(
            required.get("filesystem_write_roots", []),
            permissions.filesystem_write_roots,
            allow_subscopes=native,
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

    def _read_project_file(
        self, project_root: Path, raw_path: Any
    ) -> tuple[dict[str, Any], int, str]:
        target, relative_path = self._project_target(
            project_root, raw_path, create_parents=False
        )
        if not target.is_file():
            raise ToolRuntimeError(
                "tool_input_invalid", "Tool path is not a regular file"
            )
        try:
            content, _ = NativeFileSources(
                project_id=self._call_project_id.get() or "",
                project_target=lambda _: (target, relative_path),
                selected_inputs={},
                on_project_read=lambda path, metadata, payload: self._protect_read(
                    project_root, path, metadata, payload
                ),
            ).read({"path": relative_path}, _MAX_FILE_BYTES)
        except FileSourceError as exc:
            raise ToolRuntimeError(exc.code, str(exc)) from None
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

    def _write_project_file(
        self, project_root: Path, raw_path: Any, raw_content: Any
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
        target, relative_path = self._project_target(
            project_root, raw_path, create_parents=True
        )
        if target.exists() and not target.is_file():
            raise ToolRuntimeError(
                "tool_input_invalid", "Tool path is not a regular file"
            )
        try:
            protection_scope = self._call_input_protection.get()
            if protection_scope is not None:
                if self.input_protection is None:
                    raise ToolRuntimeError(
                        "input_protection_unavailable",
                        "Input protection is unavailable",
                    )
                self.input_protection.assert_writable(
                    protection_scope, project_root, target
                )
            # Check the actual opened file before truncating; pathname checks alone
            # cannot reject a hard-link substitution made while opening the file.
            descriptor = os.open(
                target,
                os.O_WRONLY
                | os.O_CREAT
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0),
                0o600,
            )
            with os.fdopen(descriptor, "wb") as stream:
                metadata = os.fstat(stream.fileno())
                if not stat.S_ISREG(metadata.st_mode):
                    raise ToolRuntimeError(
                        "tool_input_invalid", "Tool path is not a regular file"
                    )
                if protection_scope is not None:
                    assert self.input_protection is not None
                    self.input_protection.assert_writable(
                        protection_scope, project_root, target, metadata
                    )
                stream.truncate(0)
                stream.write(encoded)
                stream.flush()
                if protection_scope is not None:
                    assert self.input_protection is not None
                    self.input_protection.record_output_file(
                        protection_scope, project_root, target, metadata
                    )
        except OSError as exc:
            raise ToolRuntimeError(
                "tool_failed", "Tool could not write the Project file"
            ) from exc
        return {"written": True}, len(encoded), relative_path

    @classmethod
    def _list_project_directory(
        cls, project_root: Path, raw_path: Any
    ) -> tuple[dict[str, Any], int, str]:
        directory, relative_path = cls._project_directory(project_root, raw_path)
        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name.lower())
        except OSError as exc:
            raise ToolRuntimeError(
                "tool_failed", "Tool could not list the Project directory"
            ) from exc
        entries: list[dict[str, Any]] = []
        for child in children[:1_000]:
            if child.is_symlink() or cls._is_forbidden_path(child.name):
                continue
            try:
                is_directory = child.is_dir()
                entries.append(
                    {
                        "name": child.name,
                        "kind": "directory" if is_directory else "file",
                        "byte_length": 0 if is_directory else child.stat().st_size,
                    }
                )
            except OSError:
                continue
        output = {"entries": entries}
        encoded = json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
        if len(encoded) > _MAX_FILE_BYTES:
            raise ToolRuntimeError(
                "tool_output_too_large", "Directory listing exceeds the 1 MiB limit"
            )
        return output, len(encoded), relative_path

    @classmethod
    def _project_directory(cls, project_root: Path, raw_path: Any) -> tuple[Path, str]:
        if raw_path is None or raw_path == "" or raw_path == ".":
            parts: tuple[str, ...] = ()
            relative_path = "."
        elif isinstance(raw_path, str) and not os.path.isabs(raw_path):
            portable = PurePosixPath(raw_path)
            if portable.is_absolute() or any(
                part in {"", ".", ".."} for part in portable.parts
            ):
                raise ToolRuntimeError(
                    "tool_path_denied",
                    "Tool paths may not escape the Project directory",
                )
            parts = portable.parts
            relative_path = portable.as_posix()
        else:
            raise ToolRuntimeError(
                "tool_path_denied", "Tool paths must be relative to the Project"
            )
        root = project_root.expanduser().absolute()
        if root.is_symlink() or not root.is_dir():
            raise ToolRuntimeError(
                "project_unavailable", "Project directory is unavailable"
            )
        current = root
        for part in parts:
            current = current / part
            if current.is_symlink() or not current.is_dir():
                raise ToolRuntimeError(
                    "tool_path_denied", "Tool directory is unavailable or unsafe"
                )
        return current, relative_path

    def _search_project_files(
        self, project_root: Path, raw_path: Any, raw_query: Any
    ) -> tuple[dict[str, Any], int, str]:
        if not isinstance(raw_query, str) or not raw_query.strip():
            raise ToolRuntimeError(
                "tool_input_invalid", "Filesystem Search requires a query"
            )
        directory, relative_path = self._project_directory(project_root, raw_path)
        query = raw_query.casefold()
        matches: list[dict[str, Any]] = []
        scanned = 0
        try:
            candidates = sorted(
                directory.rglob("*"), key=lambda item: item.as_posix().lower()
            )
        except OSError as exc:
            raise ToolRuntimeError(
                "tool_failed", "Tool could not scan the Project directory"
            ) from exc
        for candidate in candidates:
            if scanned >= 2_000 or len(matches) >= 100:
                break
            if (
                candidate.is_symlink()
                or not candidate.is_file()
                or self._is_forbidden_path(candidate.name)
            ):
                continue
            scanned += 1
            try:
                if candidate.stat().st_size > _MAX_FILE_BYTES:
                    continue
                output, _, _ = self._read_project_file(
                    project_root, candidate.relative_to(project_root).as_posix()
                )
                text = output["content"]
            except (OSError, UnicodeDecodeError, ToolRuntimeError):
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if query not in line.casefold():
                    continue
                matches.append(
                    {
                        "path": candidate.relative_to(project_root).as_posix(),
                        "line": line_number,
                        "snippet": line[:2_000],
                    }
                )
                if len(matches) >= 100:
                    break
        output = {"matches": matches}
        encoded = json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
        if len(encoded) > _MAX_FILE_BYTES:
            raise ToolRuntimeError(
                "tool_output_too_large", "Search results exceed the 1 MiB limit"
            )
        return output, len(encoded), relative_path

    @staticmethod
    def _is_forbidden_path(name: str) -> bool:
        lowered = name.lower()
        return lowered in _FORBIDDEN_NAMES or lowered.endswith(_FORBIDDEN_SUFFIXES)

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


class _BrowserDocumentParser(HTMLParser):
    """Extract bounded, model-friendly text from an HTML response."""

    _SKIPPED_TAGS = frozenset({"script", "style", "noscript", "template"})
    _BREAK_TAGS = frozenset(
        {
            "address",
            "article",
            "br",
            "dd",
            "div",
            "dl",
            "dt",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "main",
            "p",
            "pre",
            "section",
            "tr",
        }
    )

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[dict[str, str]] = []
        self._title_depth = 0
        self._skip_depth = 0
        self._link_href: str | None = None
        self._link_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.casefold()
        if name in self._SKIPPED_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if name in self._BREAK_TAGS:
            self.text_parts.append("\n")
        if name == "title":
            self._title_depth += 1
        elif name == "a" and self._link_href is None:
            href = dict(attrs).get("href")
            if href:
                self._link_href = urljoin(self.base_url, href)
                self._link_parts = []

    def handle_endtag(self, tag: str) -> None:
        name = tag.casefold()
        if name in self._SKIPPED_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if name == "title":
            self._title_depth = max(0, self._title_depth - 1)
        elif name == "a" and self._link_href is not None:
            self._append_link()
        if name in self._BREAK_TAGS:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not data.strip():
            return
        self.text_parts.append(data)
        if self._title_depth:
            self.title_parts.append(data)
        if self._link_href is not None:
            self._link_parts.append(data)

    def _append_link(self) -> None:
        href = self._link_href
        label = " ".join("".join(self._link_parts).split())
        self._link_href = None
        self._link_parts = []
        if href is None or urlsplit(href).scheme not in {"http", "https"}:
            return
        if any(link["href"] == href for link in self.links):
            return
        self.links.append({"text": label[:200], "href": href})


class _SearchResultParser(HTMLParser):
    """Extract result cards from the provider's bounded HTML response."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._field: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if "result__a" in classes:
            self._finish()
            self._current = {
                "title": "",
                "url": _search_result_url(attributes.get("href") or ""),
                "snippet": "",
            }
            self._field = "title"
        elif "result__snippet" in classes and self._current is not None:
            self._field = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._field = None

    def handle_data(self, data: str) -> None:
        if self._current is not None and self._field is not None:
            self._current[self._field] += data

    def close(self) -> None:
        super().close()
        self._finish()

    def _finish(self) -> None:
        if self._current is None:
            return
        title = " ".join(self._current["title"].split())
        url = self._current["url"]
        snippet = " ".join(self._current["snippet"].split())
        if title and url.startswith(("http://", "https://")):
            self.results.append(
                {"title": title[:500], "url": url[:2_000], "snippet": snippet[:2_000]}
            )
        self._current = None
        self._field = None


def _search_result_url(raw_url: str) -> str:
    value = raw_url.strip()
    if value.startswith("//"):
        value = f"https:{value}"
    parsed = urlsplit(value)
    if parsed.hostname == "duckduckgo.com":
        encoded = parse_qs(parsed.query).get("uddg", [""])[0]
        if encoded:
            value = unquote(encoded)
    return value


def _browser_document(
    page_text: str, base_url: str, content_type: str
) -> dict[str, Any]:
    is_html = (
        "html" in content_type.casefold() or "<html" in page_text[:4096].casefold()
    )
    if not is_html:
        text = _normalize_browser_text(page_text)
        return {
            "title": "",
            "text": text[:_BROWSER_MAX_TEXT_CHARS],
            "links": [],
            "truncated": len(text) > _BROWSER_MAX_TEXT_CHARS,
        }
    parser = _BrowserDocumentParser(base_url)
    parser.feed(page_text)
    parser.close()
    text = _normalize_browser_text("".join(parser.text_parts))
    return {
        "title": " ".join("".join(parser.title_parts).split())[:500],
        "text": text[:_BROWSER_MAX_TEXT_CHARS],
        "links": parser.links[:100],
        "truncated": len(text) > _BROWSER_MAX_TEXT_CHARS,
    }


def _normalize_browser_text(value: str) -> str:
    return "\n".join(
        line for line in (" ".join(item.split()) for item in value.splitlines()) if line
    )


def _input_digest(resource: dict[str, Any] | None, values: dict[str, Any]) -> str:
    spec = (resource or {}).get("spec", {})
    if spec.get("adapter") == _MCP_ADAPTER:
        return sha256_digest(values)
    schema = spec.get("input_schema") or {"path": "string"}
    material: dict[str, Any] = {}
    for name in schema:
        value = values.get(name)
        if name == "content" and isinstance(value, str):
            material[name] = sha256_digest(value)
        else:
            material[name] = value
    return sha256_digest(material)


def _shell_environment() -> dict[str, str]:
    """Give workspace commands the host toolchain without host credentials."""
    environment = os.environ.copy()
    sensitive_markers = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "PRIVATE_KEY")
    for name in tuple(environment):
        if any(marker in name.upper() for marker in sensitive_markers):
            environment.pop(name, None)
    return environment


def _wrapper_spec(authorization: ToolAuthorization) -> dict[str, Any]:
    resource = authorization.resource or {}
    spec = resource.get("spec")
    if not isinstance(spec, Mapping) or spec.get("wrapper_kind") != "tool_wrapper":
        return {}
    return dict(spec)


def _http_wrapper_values(
    authorization: ToolAuthorization, values: dict[str, Any]
) -> dict[str, Any]:
    spec = _wrapper_spec(authorization)
    if not spec:
        return values
    if "url" in values or "method" in values:
        raise ToolRuntimeError(
            "tool_network_denied",
            "HTTP wrappers cannot accept unconstrained URL or method arguments",
        )
    hosts = [str(item).lower() for item in (spec.get("allowed_hosts") or []) if item]
    methods = [str(item).upper() for item in (spec.get("methods") or []) if item]
    path_prefix = str(spec.get("path_prefix") or "")
    if not hosts or not methods or not path_prefix:
        raise ToolRuntimeError(
            "tool_network_denied", "HTTP wrapper is missing host or route bounds"
        )
    scheme = str(spec.get("scheme") or "http").strip().lower()
    host = hosts[0]
    port = spec.get("port")
    netloc = f"{host}:{port}" if isinstance(port, int) else host
    query_items = {
        str(key): str(item)
        for key, item in values.items()
        if key not in {"url", "method", "body", "headers"} and item is not None
    }
    query = urlencode(query_items)
    url = f"{scheme}://{netloc}{path_prefix}"
    if query:
        url = f"{url}?{query}"
    body = values.get("body") if methods[0] in {"POST", "PUT", "PATCH"} else None
    return {"url": url, "method": methods[0], "body": body}


def _wrapper_project_path(authorization: ToolAuthorization, raw_path: Any) -> Any:
    spec = _wrapper_spec(authorization)
    prefix = str(spec.get("path_prefix") or "").strip().replace("\\", "/")
    if not prefix:
        return raw_path
    path = str(raw_path or prefix).strip().replace("\\", "/")
    trimmed = prefix.strip("/")
    portable = path.strip("/")
    if portable != trimmed and not portable.startswith(trimmed + "/"):
        raise ToolRuntimeError(
            "tool_path_denied",
            "Filesystem wrapper path is outside the frozen prefix",
        )
    return path


def _wrapper_receipt(authorization: ToolAuthorization) -> dict[str, Any]:
    spec = _wrapper_spec(authorization)
    if not spec:
        return {}
    resource = authorization.resource or {}
    extra: dict[str, Any] = {
        "factory_resource_id": str(resource.get("resource_id") or ""),
        "factory_resource_version": str(resource.get("version") or ""),
        "base_adapter": str(spec.get("base_adapter") or authorization.adapter or ""),
    }
    return {key: value for key, value in extra.items() if value}
