from __future__ import annotations

import json

import httpx

from veyra_agent_platform.local.mcp.transport import StreamableHttpMcpTransport


def test_streamable_http_transport_negotiates_and_supports_json_and_sse() -> None:
    requests: list[tuple[dict[str, object], httpx.Headers]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append((payload, request.headers))
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-11-25"},
                },
                headers={"MCP-Session-Id": "session-1"},
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            body = (
                "event: message\ndata: "
                + json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": payload["id"],
                        "result": {"tools": [{"name": "echo"}]},
                    }
                )
                + "\n\n"
            )
            return httpx.Response(
                200,
                content=body,
                headers={"content-type": "text/event-stream"},
            )
        if method == "tools/call":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"content": [{"type": "text", "text": "ok"}]},
                },
            )
        raise AssertionError(f"unexpected MCP method: {method}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        transport = StreamableHttpMcpTransport(
            "https://example.com/mcp",
            {"Authorization": "Bearer test-token"},
            http_client=client,
        )

        assert transport.list_tools() == [{"name": "echo"}]
        assert transport.call_tool("echo", {"text": "hello"}) == {
            "content": [{"type": "text", "text": "ok"}]
        }
    finally:
        client.close()

    assert requests[0][0]["method"] == "initialize"
    assert "mcp-protocol-version" not in requests[0][1]
    assert requests[2][1]["mcp-protocol-version"] == "2025-11-25"
    assert requests[2][1]["mcp-session-id"] == "session-1"
    assert requests[3][0]["method"] == "initialize"
