from __future__ import annotations

import hashlib
import io
import json
import zipfile

import yaml

from .conftest import CommunityHarness
from .test_auth_flow import _csrf_headers, _register


def _plugin_archive() -> bytes:
    manifest = yaml.safe_dump(
        {
            "schema_version": "1.0",
            "plugin_id": "veyra.plugin.research",
            "name": "Research Pack",
            "description": "A Community-shared Skill and MCP pack.",
            "version": "1.0.0",
            "license": "MIT",
            "skills": [
                {
                    "path": "skills/research/SKILL.md",
                    "reference": "veyra.skill.research-pack@1.0.0",
                    "name": "Research",
                    "description": "Keep evidence structured.",
                }
            ],
            "mcp_config": "mcp.json",
        },
        sort_keys=False,
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plugin.vplugin.yaml", manifest)
        archive.writestr(
            "skills/research/SKILL.md",
            "# Research\n\nSeparate claims from evidence.\n",
        )
        archive.writestr(
            "mcp.json",
            json.dumps(
                {"mcpServers": {"docs": {"command": "node", "args": ["server.js"]}}}
            ),
        )
    return buffer.getvalue()


def test_plugin_registry_publishes_browses_and_downloads_immutable_pack(
    community: CommunityHarness,
) -> None:
    # The shared auth harness creates mapped tables directly; mark the registry
    # service ready so this test exercises the route rather than migration boot.
    community.app.state.database_ready = True
    _register(community, handle="plugin-maker")
    content = _plugin_archive()
    published = community.client.post(
        "/api/v1/registry/plugins",
        files={"package": ("research.vplugin.zip", content, "application/zip")},
        headers=_csrf_headers(community),
    )
    assert published.status_code == 201, published.text
    entry = published.json()
    assert entry["schema_version"] == "community.plugin.registry.v1"
    assert entry["plugin_id"] == "veyra.plugin.research"
    assert entry["slug"] == "research"
    assert entry["skill_count"] == 1
    assert entry["mcp_count"] == 1
    assert entry["skills"][0]["reference"] == "veyra.skill.research-pack@1.0.0"
    assert entry["license_scan"] == {
        "status": "passed",
        "code": "spdx_identifier",
        "value": "MIT",
    }
    assert "Separate claims" not in json.dumps(entry)

    listed = community.client.get("/api/v1/registry/plugins")
    assert listed.status_code == 200
    assert listed.json()["entries"][0]["version"] == "1.0.0"
    detail = community.client.get("/api/v1/registry/plugins/plugin-maker/research")
    assert detail.status_code == 200
    assert detail.json()["package_hash"] == hashlib.sha256(content).hexdigest()

    downloaded = community.client.get(
        "/api/v1/registry/plugins/plugin-maker/research/versions/1.0.0/download"
    )
    assert downloaded.status_code == 200
    assert downloaded.headers["etag"] == f'"{hashlib.sha256(content).hexdigest()}"'
    assert downloaded.content == content
    registry_root = community.app.state.settings.registry_storage_root
    assert registry_root.is_dir()
    assert "Application Support" not in str(registry_root)
    assert any(path.is_file() for path in registry_root.iterdir())

    duplicate = community.client.post(
        "/api/v1/registry/plugins",
        files={"package": ("research.vplugin.zip", content, "application/zip")},
        headers=_csrf_headers(community),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "plugin_version_exists"
