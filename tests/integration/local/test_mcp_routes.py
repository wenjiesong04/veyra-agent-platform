from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.mcp import ScriptedMcpTransport


def _factory(
    _command: str, _args: list[str], _env: dict[str, str]
) -> ScriptedMcpTransport:
    return ScriptedMcpTransport(
        tools=[
            {
                "name": "echo",
                "description": "Echo text",
                "inputSchema": {"properties": {"text": {"type": "string"}}},
            }
        ],
        calls={"echo": {"content": [{"type": "text", "text": "ok"}]}},
    )


def _http_mcp_handler(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    method = payload.get("method")
    if method == "initialize":
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"protocolVersion": "2025-11-25"},
            },
            headers={"MCP-Session-Id": "route-session"},
        )
    if method == "notifications/initialized":
        return httpx.Response(202)
    if method == "tools/list":
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "tools": [
                        {
                            "name": "remote_echo",
                            "description": "Remote echo",
                            "inputSchema": {"properties": {"text": {"type": "string"}}},
                        }
                    ]
                },
            },
        )
    raise AssertionError(f"unexpected MCP method: {method}")


def test_mcp_configure_and_discover_writes_overlay_catalog(tmp_path: Path) -> None:
    with TestClient(
        create_app(
            LocalSettings(
                database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
                project_storage_root=tmp_path / "projects",
            ),
            mcp_transport_factory=_factory,
        )
    ) as client:
        created = client.post(
            "/api/v1/mcp/servers",
            json={"name": "demo", "command": "npx", "args": ["-y", "demo"]},
        )
        assert created.status_code == 201
        server_id = created.json()["server"]["server_id"]
        readiness = client.get(f"/api/v1/mcp/servers/{server_id}/readiness")
        assert readiness.status_code == 200
        assert readiness.json()["server_id"] == server_id
        assert readiness.json()["ready"] is True
        discovered = client.post(f"/api/v1/mcp/servers/{server_id}/discover")
        assert discovered.status_code == 200
        tools = discovered.json()["tools"]
        assert tools[0]["origin"] == "discovered"
        assert tools[0]["availability"] == "ready"
        assert tools[0]["factory_selectable"] is False
        assert tools[0]["spec"]["approval_required"] is True
        assert tools[0]["spec"]["review_required"] is True
        assert tools[0]["spec"]["adapter"] == "veyra.runtime.mcp.call"
        approved = client.post(
            f"/api/v1/mcp/servers/{server_id}/tools/"
            f"{tools[0]['resource_id']}/versions/{tools[0]['version']}/approve"
        )
        assert approved.status_code == 200
        assert approved.json()["resource"]["factory_selectable"] is True
        assert approved.json()["resource"]["spec"]["review_required"] is False
        listed = client.get("/api/v1/resources", params={"kind": "tool"})
        assert any(
            item["resource_id"] == tools[0]["resource_id"]
            and item["factory_selectable"] is True
            for item in listed.json()["resources"]
        )
        rejected = client.post(
            "/api/v1/mcp/servers",
            json={"name": "bad", "command": "python; rm -rf /"},
        )
        assert rejected.status_code == 422


def test_mcp_config_import_is_atomic_and_keeps_only_bindings(tmp_path: Path) -> None:
    with TestClient(
        create_app(
            LocalSettings(
                database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
                project_storage_root=tmp_path / "projects",
            )
        )
    ) as client:
        imported = client.post(
            "/api/v1/mcp/servers/import",
            json={
                "servers": [
                    {
                        "name": "docs",
                        "command": "npx",
                        "args": ["-y", "@example/docs"],
                        "env_names": {"API_KEY": "DOCS_API_KEY"},
                    },
                    {"name": "local", "command": "node", "args": []},
                ]
            },
        )
        assert imported.status_code == 200, imported.text
        assert [item["name"] for item in imported.json()["servers"]] == [
            "docs",
            "local",
        ]
        assert imported.json()["servers"][0]["env_names"] == {"API_KEY": "DOCS_API_KEY"}

        rejected = client.post(
            "/api/v1/mcp/servers/import",
            json={
                "servers": [
                    {"name": "valid", "command": "node"},
                    {"name": "invalid", "command": "node;rm"},
                ]
            },
        )
        assert rejected.status_code == 422
        plaintext = client.post(
            "/api/v1/mcp/servers/import",
            json={
                "servers": [
                    {
                        "name": "secret",
                        "command": "node",
                        "env_names": {"TOKEN": "sk-live-secret"},
                    }
                ]
            },
        )
        assert plaintext.status_code == 422
        assert sorted(
            item["name"] for item in client.get("/api/v1/mcp/servers").json()["servers"]
        ) == ["docs", "local"]


def test_mcp_server_lifecycle_updates_discovered_tool_availability(
    tmp_path: Path,
) -> None:
    with TestClient(
        create_app(
            LocalSettings(
                database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
                project_storage_root=tmp_path / "projects",
            ),
            mcp_transport_factory=_factory,
        )
    ) as client:
        created = client.post(
            "/api/v1/mcp/servers",
            json={"name": "demo", "command": "npx", "args": ["-y", "demo"]},
        )
        assert created.status_code == 201, created.text
        server_id = created.json()["server"]["server_id"]
        discovered = client.post(f"/api/v1/mcp/servers/{server_id}/discover")
        assert discovered.status_code == 200, discovered.text
        tool = discovered.json()["tools"][0]
        approved = client.post(
            f"/api/v1/mcp/servers/{server_id}/tools/"
            f"{tool['resource_id']}/versions/{tool['version']}/approve"
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["resource"]["factory_selectable"] is True

        disabled = client.patch(
            f"/api/v1/mcp/servers/{server_id}", json={"enabled": False}
        )
        assert disabled.status_code == 200, disabled.text
        paused_tool = client.get(
            f"/api/v1/resources/{tool['resource_id']}/versions/{tool['version']}"
        )
        assert paused_tool.status_code == 200, paused_tool.text
        assert paused_tool.json()["availability"] == "disabled"
        assert paused_tool.json()["factory_selectable"] is False

        enabled = client.patch(
            f"/api/v1/mcp/servers/{server_id}", json={"enabled": True}
        )
        assert enabled.status_code == 200, enabled.text
        restored_tool = client.get(
            f"/api/v1/resources/{tool['resource_id']}/versions/{tool['version']}"
        )
        assert restored_tool.status_code == 200, restored_tool.text
        assert restored_tool.json()["availability"] == "ready"
        assert restored_tool.json()["factory_selectable"] is True


def test_streamable_http_mcp_server_can_be_checked_and_discovered(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MCP_TOKEN", "test-token")
    http_client = httpx.Client(transport=httpx.MockTransport(_http_mcp_handler))
    try:
        with TestClient(
            create_app(
                LocalSettings(
                    database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
                    project_storage_root=tmp_path / "projects",
                ),
                mcp_http_client=http_client,
            )
        ) as client:
            created = client.post(
                "/api/v1/mcp/servers",
                json={
                    "name": "remote",
                    "transport": "streamable_http",
                    "url": "https://example.com/mcp",
                    "headers": {"Authorization": "Bearer ${MCP_TOKEN}"},
                },
            )
            assert created.status_code == 201, created.text
            server = created.json()["server"]
            assert server["transport"] == "streamable_http"
            assert server["command"] == ""
            assert server["headers"] == {"Authorization": "Bearer ${MCP_TOKEN}"}
            readiness = client.get(
                f"/api/v1/mcp/servers/{server['server_id']}/readiness"
            )
            assert readiness.status_code == 200, readiness.text
            assert readiness.json()["ready"] is True
            switched = client.patch(
                f"/api/v1/mcp/servers/{server['server_id']}",
                json={"transport": "stdio", "command": "node"},
            )
            assert switched.status_code == 200, switched.text
            assert switched.json()["server"]["transport"] == "stdio"
            switched_back = client.patch(
                f"/api/v1/mcp/servers/{server['server_id']}",
                json={
                    "transport": "streamable_http",
                    "url": "https://example.com/mcp",
                    "headers": {"Authorization": "Bearer ${MCP_TOKEN}"},
                },
            )
            assert switched_back.status_code == 200, switched_back.text
            assert switched_back.json()["server"]["transport"] == "streamable_http"
            discovered = client.post(
                f"/api/v1/mcp/servers/{server['server_id']}/discover"
            )
            assert discovered.status_code == 200, discovered.text
            assert discovered.json()["tools"][0]["name"] == "remote_echo"
            assert discovered.json()["tools"][0]["required_permissions"][
                "network_hosts"
            ] == ["example.com"]
    finally:
        http_client.close()
