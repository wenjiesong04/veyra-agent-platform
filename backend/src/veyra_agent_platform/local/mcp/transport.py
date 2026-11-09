"""JSON-RPC MCP client transports. Credentials never enter Project source."""

from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from typing import Any, Protocol, TypeVar

import httpx

_MAX_MESSAGE_BYTES = 1_048_576
_MCP_PROTOCOL_VERSION = "2025-11-25"
_TransportResult = TypeVar("_TransportResult")


class McpTransportError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class McpTransport(Protocol):
    def list_tools(self) -> list[dict[str, Any]]: ...

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]: ...


class ScriptedMcpTransport:
    """In-process transport used by tests; never spawns a subprocess."""

    def __init__(
        self,
        tools: list[dict[str, Any]] | None = None,
        calls: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.tools = list(tools or [])
        self.calls = dict(calls or {})

    def list_tools(self) -> list[dict[str, Any]]:
        return list(self.tools)

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name not in self.calls:
            raise McpTransportError(
                "mcp_tool_missing", f"MCP tool {name} is not scripted"
            )
        _ = arguments
        return dict(self.calls[name])


class StdioMcpTransport:
    """Spawn a configured MCP server over newline-delimited JSON-RPC stdio."""

    def __init__(
        self,
        command: str,
        args: list[str],
        env: Mapping[str, str] | None = None,
        *,
        timeout: float = 20.0,
    ) -> None:
        self.command = command
        self.args = list(args)
        self.env = dict(env or {})
        self.timeout = timeout

    def list_tools(self) -> list[dict[str, Any]]:
        with _StdioSession(self.command, self.args, self.env, self.timeout) as session:
            session.initialize()
            result = session.request("tools/list", {})
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise McpTransportError(
                "mcp_discovery_invalid", "MCP tools/list was invalid"
            )
        return [tool for tool in tools if isinstance(tool, dict)]

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        with _StdioSession(self.command, self.args, self.env, self.timeout) as session:
            session.initialize()
            result = session.request(
                "tools/call", {"name": name, "arguments": dict(arguments)}
            )
        if not isinstance(result, dict):
            raise McpTransportError("mcp_call_invalid", "MCP tools/call was invalid")
        return result


class _StdioSession:
    def __init__(
        self,
        command: str,
        args: list[str],
        env: Mapping[str, str],
        timeout: float,
    ) -> None:
        self.command = command
        self.args = args
        self.env = env
        self.timeout = timeout
        self._process: subprocess.Popen[bytes] | None = None
        self._next_id = 1
        self._stdout_buffer = b""

    def __enter__(self) -> _StdioSession:
        merged = {
            name: os.environ[name]
            for name in ("PATH", "HOME", "SYSTEMROOT")
            if name in os.environ
        }
        merged.update(self.env)
        try:
            self._process = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=merged,
                start_new_session=os.name != "nt",
            )
        except OSError as exc:
            raise McpTransportError(
                "mcp_spawn_failed", "MCP server command could not be started"
            ) from exc
        return self

    def __exit__(self, *_exc: object) -> None:
        process = self._process
        if process is None:
            return
        try:
            if process.stdin:
                with suppress(OSError):
                    process.stdin.close()
            if process.poll() is None:
                if os.name == "nt":
                    process.kill()
                else:
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)
            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=2)
        finally:
            self._process = None

    def initialize(self) -> None:
        self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "veyra-local", "version": "1.0"},
            },
        )
        self.notify("notifications/initialized", {})

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._write(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        deadline = time.monotonic() + self.timeout
        while True:
            payload = self._read(deadline)
            if payload.get("id") != request_id:
                # Servers may emit notifications while a request is in flight.
                if "id" not in payload and isinstance(payload.get("method"), str):
                    continue
                raise McpTransportError(
                    "mcp_protocol_invalid", "MCP response id did not match"
                )
            if "error" in payload:
                raise McpTransportError(
                    "mcp_remote_error", "MCP server returned an error"
                )
            result = payload.get("result")
            if not isinstance(result, dict):
                raise McpTransportError(
                    "mcp_protocol_invalid", "MCP result must be an object"
                )
            return result

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _write(self, payload: dict[str, Any]) -> None:
        process = self._require_process()
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        assert process.stdin is not None
        try:
            process.stdin.write(body + b"\n")
            process.stdin.flush()
        except OSError as exc:
            raise McpTransportError("mcp_io_failed", "MCP stdin write failed") from exc

    def _read(self, deadline: float) -> dict[str, Any]:
        process = self._require_process()
        assert process.stdout is not None
        while True:
            if b"\n" in self._stdout_buffer:
                line, self._stdout_buffer = self._stdout_buffer.split(b"\n", 1)
                line = line.rstrip(b"\r")
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise McpTransportError(
                    "mcp_timeout", "MCP server did not respond before the timeout"
                )
            selector = selectors.DefaultSelector()
            try:
                selector.register(process.stdout, selectors.EVENT_READ)
                if not selector.select(remaining):
                    raise McpTransportError(
                        "mcp_timeout", "MCP server did not respond before the timeout"
                    )
            finally:
                selector.close()
            try:
                chunk = os.read(process.stdout.fileno(), 65_536)
            except OSError as exc:
                raise McpTransportError(
                    "mcp_io_failed", "MCP stdout read failed"
                ) from exc
            if not chunk:
                raise McpTransportError("mcp_io_failed", "MCP server closed stdout")
            self._stdout_buffer += chunk
            if len(self._stdout_buffer) > _MAX_MESSAGE_BYTES:
                raise McpTransportError(
                    "mcp_message_too_large", "MCP message exceeds the 1 MiB limit"
                )
        if not line:
            raise McpTransportError("mcp_protocol_invalid", "MCP message is empty")
        try:
            payload = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise McpTransportError(
                "mcp_protocol_invalid", "MCP response is not newline-delimited JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise McpTransportError(
                "mcp_protocol_invalid", "MCP response must be an object"
            )
        return payload

    def _require_process(self) -> subprocess.Popen[bytes]:
        if self._process is None or self._process.poll() is not None:
            raise McpTransportError("mcp_io_failed", "MCP server is not running")
        return self._process


class StreamableHttpMcpTransport:
    """Call an MCP endpoint over the 2025-11-25 Streamable HTTP binding."""

    def __init__(
        self,
        url: str,
        headers: Mapping[str, str] | None = None,
        *,
        http_client: httpx.Client | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.url = url
        self.headers = dict(headers or {})
        self.http_client = http_client
        self.timeout = timeout

    def list_tools(self) -> list[dict[str, Any]]:
        def operation(client: httpx.Client) -> list[dict[str, Any]]:
            session = _HttpMcpSession(client, self.url, self.headers)
            session.initialize()
            result = session.request("tools/list", {})
            tools = result.get("tools")
            if not isinstance(tools, list):
                raise McpTransportError(
                    "mcp_discovery_invalid", "MCP tools/list was invalid"
                )
            return [tool for tool in tools if isinstance(tool, dict)]

        return self._with_client(operation)

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        def operation(client: httpx.Client) -> dict[str, Any]:
            session = _HttpMcpSession(client, self.url, self.headers)
            session.initialize()
            result = session.request(
                "tools/call", {"name": name, "arguments": dict(arguments)}
            )
            if not isinstance(result, dict):
                raise McpTransportError(
                    "mcp_call_invalid", "MCP tools/call was invalid"
                )
            return result

        return self._with_client(operation)

    def _with_client(
        self, operation: Callable[[httpx.Client], _TransportResult]
    ) -> _TransportResult:
        if self.http_client is not None:
            return operation(self.http_client)
        with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
            return operation(client)


class _HttpMcpSession:
    def __init__(
        self, client: httpx.Client, url: str, headers: Mapping[str, str]
    ) -> None:
        self.client = client
        self.url = url
        self.headers = dict(headers)
        self.session_id: str | None = None
        self.protocol_version = _MCP_PROTOCOL_VERSION
        self._next_id = 1

    def initialize(self) -> None:
        result, response_headers = self._request(
            "initialize",
            {
                "protocolVersion": _MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "veyra-local", "version": "1.0"},
            },
            include_protocol=False,
        )
        session_id = response_headers.get("MCP-Session-Id")
        if session_id:
            self.session_id = session_id
        negotiated = result.get("protocolVersion")
        if isinstance(negotiated, str) and negotiated:
            self.protocol_version = negotiated
        self._notify("notifications/initialized", {})

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        result, _ = self._request(method, params)
        return result

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        headers = self._headers(include_protocol=True)
        try:
            response = self.client.post(self.url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise McpTransportError(
                "mcp_timeout", "MCP server did not respond before the timeout"
            ) from exc
        except httpx.HTTPError as exc:
            raise McpTransportError(
                "mcp_unavailable", "MCP server is unavailable"
            ) from exc
        if response.status_code not in {200, 202}:
            raise _http_error(response.status_code)

    def _request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        include_protocol: bool = True,
    ) -> tuple[dict[str, Any], httpx.Headers]:
        request_id = self._next_id
        self._next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        try:
            response = self.client.post(
                self.url,
                json=payload,
                headers=self._headers(include_protocol=include_protocol),
            )
        except httpx.TimeoutException as exc:
            raise McpTransportError(
                "mcp_timeout", "MCP server did not respond before the timeout"
            ) from exc
        except httpx.HTTPError as exc:
            raise McpTransportError(
                "mcp_unavailable", "MCP server is unavailable"
            ) from exc
        if not response.is_success:
            raise _http_error(response.status_code)
        messages = _response_messages(response)
        if not messages:
            raise McpTransportError(
                "mcp_protocol_invalid", "MCP response did not contain a message"
            )
        for message in messages:
            if message.get("id") != request_id:
                if "id" not in message and isinstance(message.get("method"), str):
                    continue
                raise McpTransportError(
                    "mcp_protocol_invalid", "MCP response id did not match"
                )
            if "error" in message:
                raise McpTransportError(
                    "mcp_remote_error", "MCP server returned an error"
                )
            result = message.get("result")
            if not isinstance(result, dict):
                raise McpTransportError(
                    "mcp_protocol_invalid", "MCP result must be an object"
                )
            return result, response.headers
        raise McpTransportError(
            "mcp_protocol_invalid", "MCP response did not contain the request result"
        )

    def _headers(self, *, include_protocol: bool) -> dict[str, str]:
        headers = {
            **self.headers,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if include_protocol:
            headers["MCP-Protocol-Version"] = self.protocol_version
        if self.session_id:
            headers["MCP-Session-Id"] = self.session_id
        return headers


def _response_messages(response: httpx.Response) -> list[dict[str, Any]]:
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
    if content_type == "text/event-stream":
        return _sse_messages(response.text)
    try:
        payload = response.json()
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise McpTransportError(
            "mcp_protocol_invalid", "MCP response is not valid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise McpTransportError(
            "mcp_protocol_invalid", "MCP response must be an object"
        )
    return [payload]


def _sse_messages(body: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    data: list[str] = []
    for line in body.splitlines():
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif not line and data:
            _append_sse_message(messages, "\n".join(data))
            data = []
    if data:
        _append_sse_message(messages, "\n".join(data))
    return messages


def _append_sse_message(messages: list[dict[str, Any]], value: str) -> None:
    try:
        payload = json.loads(value)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise McpTransportError(
            "mcp_protocol_invalid", "MCP SSE data is not valid JSON"
        ) from exc
    if isinstance(payload, dict):
        messages.append(payload)


def _http_error(status_code: int) -> McpTransportError:
    if status_code in {401, 403}:
        return McpTransportError(
            "mcp_unauthorized", "MCP server rejected the configured credentials"
        )
    if status_code == 404:
        return McpTransportError("mcp_endpoint_not_found", "MCP endpoint was not found")
    if status_code == 429:
        return McpTransportError("mcp_rate_limited", "MCP server is rate limited")
    if status_code >= 500:
        return McpTransportError("mcp_remote_error", "MCP server failed")
    return McpTransportError("mcp_request_invalid", "MCP server rejected the request")


TransportFactory = Callable[[str, list[str], Mapping[str, str]], McpTransport]
