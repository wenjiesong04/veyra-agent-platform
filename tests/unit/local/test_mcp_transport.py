from __future__ import annotations

import sys

import pytest

from veyra_agent_platform.local.mcp.transport import (
    McpTransportError,
    StdioMcpTransport,
)

_SERVER = """
import json
import sys

for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    method = message.get("method")
    if method == "tools/list":
        result = {"tools": [{"name": "echo"}]}
    elif method == "tools/call":
        result = {
            "content": [
                {"type": "text", "text": message["params"]["arguments"]["text"]}
            ]
        }
    else:
        result = {}
    print(
        json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}),
        flush=True,
    )
"""


def test_stdio_transport_uses_newline_json_rpc_and_calls_tools() -> None:
    transport = StdioMcpTransport(sys.executable, ["-c", _SERVER], timeout=1)

    assert transport.list_tools() == [{"name": "echo"}]
    assert transport.call_tool("echo", {"text": "hello"}) == {
        "content": [{"type": "text", "text": "hello"}]
    }


def test_stdio_transport_times_out_and_cleans_up() -> None:
    transport = StdioMcpTransport(
        sys.executable,
        ["-c", "import time; time.sleep(1)"],
        timeout=0.05,
    )

    with pytest.raises(McpTransportError) as error:
        transport.list_tools()

    assert error.value.code == "mcp_timeout"


def test_stdio_transport_rejects_non_object_json() -> None:
    server = "import sys; next(sys.stdin); print(json.dumps([]), flush=True)"
    transport = StdioMcpTransport(
        sys.executable,
        ["-c", "import json; " + server],
        timeout=1,
    )

    with pytest.raises(McpTransportError) as error:
        transport.list_tools()

    assert error.value.code == "mcp_protocol_invalid"
