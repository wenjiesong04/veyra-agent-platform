"""Safe, catalog-backed Tool Runtime adapters for local Agent runs."""

from __future__ import annotations

import json
import os
import signal
import subprocess
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlsplit

import httpx

from veyra_agent_platform.contracts.agent import AgentSource, FlowNode
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.local.mcp.execution import McpExecutionError, execute_call
from veyra_agent_platform.local.mcp.schema import McpSchemaError, require_contract
from veyra_agent_platform.local.mcp.service import McpService
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceCatalogError
from veyra_agent_platform.local.secrets import SecretStore, resolve_secret

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
    ) -> None:
        self.catalog = catalog
        self.mcp = mcp
        self._http_client = http_client or httpx.Client(
            timeout=30.0, follow_redirects=False
        )
        self._secret_store = secret_store
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
        if authorization.adapter is None:
            raise ToolRuntimeError(
                "tool_runtime_unavailable", "Tool adapter is not installed"
            )
        adapter = self._adapters.get(authorization.adapter)
        if adapter is None:
            raise ToolRuntimeError(
                "tool_runtime_unavailable", "Tool adapter is not installed"
            )
        return adapter(
            project_root=project_root,
            source=source,
            node=node,
            values=values,
            authorization=authorization,
            approved=approved,
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
        output, byte_length, relative_path = self._read_project_file(
            project_root, values.get("path")
        )
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
        output, byte_length, relative_path = self._list_project_directory(
            project_root, values.get("path")
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
        output, byte_length, relative_path = self._search_project_files(
            project_root, values.get("path"), values.get("query")
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
        method = values.get("method")
        raw_url = values.get("url")
        body = values.get("body")
        if not isinstance(method, str) or method.upper() not in _HTTP_METHODS:
            raise ToolRuntimeError("tool_input_invalid", "HTTP method is not supported")
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
        if host.lower() not in allowed_hosts:
            raise ToolRuntimeError(
                "tool_network_denied",
                "HTTP host must be explicitly listed on the Tool node",
            )
        if body is not None and not isinstance(body, str):
            raise ToolRuntimeError("tool_input_invalid", "HTTP body must be text")
        try:
            response = self._http_client.request(
                method.upper(), raw_url, content=body, follow_redirects=False
            )
            content = response.content
        except httpx.TimeoutException as exc:
            raise ToolRuntimeError("tool_timeout", "HTTP request timed out") from exc
        except httpx.HTTPError as exc:
            raise ToolRuntimeError("tool_failed", "HTTP request failed") from exc
        if len(content) > _MAX_FILE_BYTES:
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

    @classmethod
    def _search_project_files(
        cls, project_root: Path, raw_path: Any, raw_query: Any
    ) -> tuple[dict[str, Any], int, str]:
        if not isinstance(raw_query, str) or not raw_query.strip():
            raise ToolRuntimeError(
                "tool_input_invalid", "Filesystem Search requires a query"
            )
        directory, relative_path = cls._project_directory(project_root, raw_path)
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
                or cls._is_forbidden_path(candidate.name)
            ):
                continue
            scanned += 1
            try:
                if candidate.stat().st_size > _MAX_FILE_BYTES:
                    continue
                text = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
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
