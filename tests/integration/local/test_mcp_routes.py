from __future__ import annotations

from pathlib import Path

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
