from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings


def _plugin_archive() -> bytes:
    manifest = yaml.safe_dump(
        {
            "schema_version": "1.0",
            "plugin_id": "veyra.plugin.research",
            "name": "Research Pack",
            "description": "A bounded Skill and MCP bundle.",
            "version": "1.0.0",
            "skills": [
                {
                    "path": "skills/research/SKILL.md",
                    "reference": "veyra.skill.research-pack@1.0.0",
                    "name": "Research Pack Skill",
                    "description": "Keeps research evidence structured.",
                }
            ],
            "mcp_config": "mcp.json",
        },
        sort_keys=False,
    )
    mcp = {
        "mcpServers": {
            "docs": {
                "command": "node",
                "args": ["server.js"],
                "env": {"TOKEN": "${DOCS_TOKEN}"},
            }
        }
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plugin.vplugin.yaml", manifest)
        archive.writestr(
            "skills/research/SKILL.md",
            "# Research\n\nAlways separate claims from evidence.\n",
        )
        archive.writestr("mcp.json", json.dumps(mcp))
    return buffer.getvalue()


def test_plugin_pack_import_is_quarantined_then_activates_skill_and_disabled_mcp(
    tmp_path: Path,
) -> None:
    with TestClient(
        create_app(
            LocalSettings(
                database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
                project_storage_root=tmp_path / "projects",
            )
        )
    ) as client:
        imported = client.post(
            "/api/v1/plugins/import",
            files={
                "file": (
                    "research.vplugin.zip",
                    _plugin_archive(),
                    "application/zip",
                )
            },
        )
        assert imported.status_code == 201, imported.text
        plugin = imported.json()["plugin"]
        assert plugin["state"] == "quarantined"
        assert plugin["skills"][0]["instruction"].startswith("# Research")
        assert plugin["mcp_servers"][0]["env_names"] == {"TOKEN": "DOCS_TOKEN"}

        refused = client.post(
            f"/api/v1/plugins/{plugin['plugin_id']}/versions/{plugin['version']}/activate",
            json={"confirm": False},
        )
        assert refused.status_code == 422

        activated = client.post(
            f"/api/v1/plugins/{plugin['plugin_id']}/versions/{plugin['version']}/activate",
            json={"confirm": True},
        )
        assert activated.status_code == 200, activated.text
        active = activated.json()["plugin"]
        assert active["state"] == "active"
        assert len(active["skill_resources"]) == 1
        assert len(active["mcp_server_ids"]) == 1

        skills = client.get("/api/v1/resources", params={"kind": "skill"}).json()[
            "resources"
        ]
        installed = next(item for item in skills if item["origin"] == "workshop")
        assert installed["availability"] == "ready"
        assert installed["factory_selectable"] is True
        assert "Always separate claims" in installed["spec"]["instruction"]

        servers = client.get("/api/v1/mcp/servers").json()["servers"]
        assert len(servers) == 1
        assert servers[0]["enabled"] is False
        assert servers[0]["env_names"] == {"TOKEN": "DOCS_TOKEN"}

        replay = client.post(
            f"/api/v1/plugins/{plugin['plugin_id']}/versions/{plugin['version']}/activate",
            json={"confirm": True},
        )
        assert replay.status_code == 200
        assert replay.json()["plugin"]["skill_resources"] == active["skill_resources"]
        assert replay.json()["plugin"]["mcp_server_ids"] == active["mcp_server_ids"]
