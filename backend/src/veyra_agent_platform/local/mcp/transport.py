"""JSON-RPC MCP client transports. Credentials never enter Project source."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Mapping
from typing import Any, Protocol


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
    """Spawn a configured MCP server over stdio JSON-RPC with Content-Length framing."""

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

    def __enter__(self) -> _StdioSession:
        merged = os.environ.copy()
        merged.update(self.env)
        try:
            self._process = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=merged,
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
        if process.stdin:
            process.stdin.close()
        process.kill()
        process.wait(timeout=2)
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
        payload = self._read()
        if payload.get("id") != request_id:
            raise McpTransportError(
                "mcp_protocol_invalid", "MCP response id did not match"
            )
        if "error" in payload:
            raise McpTransportError("mcp_remote_error", "MCP server returned an error")
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
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        assert process.stdin is not None
        try:
            process.stdin.write(header + body)
            process.stdin.flush()
        except OSError as exc:
            raise McpTransportError("mcp_io_failed", "MCP stdin write failed") from exc

    def _read(self) -> dict[str, Any]:
        process = self._require_process()
        assert process.stdout is not None
        headers: dict[str, str] = {}
        while True:
            line = process.stdout.readline()
            if not line:
                raise McpTransportError("mcp_io_failed", "MCP server closed stdout")
            if line in {b"\r\n", b"\n"}:
                break
            decoded = line.decode("utf-8", errors="replace")
            key, _, value = decoded.partition(":")
            headers[key.strip().lower()] = value.strip()
        try:
            length = int(headers["content-length"])
        except (KeyError, ValueError) as exc:
            raise McpTransportError(
                "mcp_protocol_invalid", "MCP response is missing Content-Length"
            ) from exc
        body = process.stdout.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise McpTransportError(
                "mcp_protocol_invalid", "MCP response is not JSON"
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


TransportFactory = Callable[[str, list[str], Mapping[str, str]], McpTransport]
