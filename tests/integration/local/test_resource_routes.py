from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.mcp import ScriptedMcpTransport
from veyra_agent_platform.local.runtime.config import RuntimeSettings
from veyra_agent_platform.local.secrets import MacOSKeychainSecretStore


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MacOSKeychainSecretStore, "get", lambda self, ref: None)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            LocalSettings(
                database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
                project_storage_root=tmp_path / "projects",
            ),
            runtime_settings=RuntimeSettings(allow_process_environment_key=False),
        )
    )


def test_resource_routes_filter_and_return_immutable_detail(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/resources", params={"kind": "skill"})
        assert response.status_code == 200
        payload = response.json()
        assert {resource["name"] for resource in payload["resources"]} == {
            "Research Brief",
            "Document Analyzer",
            "Content Planner",
            "Need Extractor",
            "Evidence Ledger",
            "File Taxonomy",
        }
        assert {item["kind"]: item["count"] for item in payload["kinds"]} == {
            "component": 0,
            "tool": 0,
            "mcp_tool": 0,
            "skill": 6,
            "policy": 0,
            "template": 0,
        }
        detail = client.get(
            "/api/v1/resources/veyra.skill.research-brief/versions/1.0.0"
        )
        assert detail.status_code == 200
        assert detail.json()["reference"] == "veyra.skill.research-brief@1.0.0"
        tool = client.get("/api/v1/resources/veyra.tool.filesystem.read/versions/1.0.0")
        assert tool.status_code == 200
        assert tool.json()["runtime_status"] == "supported"


def test_resource_routes_use_typed_errors_and_preserve_components(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        invalid = client.get("/api/v1/resources", params={"kind": "unknown"})
        assert invalid.status_code == 400
        assert invalid.json()["code"] == "invalid_resource_kind"
        missing = client.get("/api/v1/resources/nope/versions/1.0.0")
        assert missing.status_code == 404
        assert missing.json()["code"] == "resource_not_found"
        components = client.get("/api/v1/components")
        assert components.status_code == 200
        assert [component["type"] for component in components.json()["components"]] == [
            "Start",
            "Agent",
            "Model",
            "Tool",
            "Condition",
            "Transform",
            "HumanApproval",
            "Verifier",
            "Output",
            "Stop",
            "CustomComponent",
            "AgentCall",
        ]


def test_readiness_is_live_consistent_and_does_not_change_identity(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        catalog = client.app.state.resource_catalog
        raw = catalog.resources()
        resources = client.get("/api/v1/resources").json()["resources"]
        by_id = {item["resource_id"]: item for item in resources}
        assert by_id["veyra.tool.filesystem.read"]["availability"] == "ready"
        for name in ("read", "write"):
            item = by_id[f"veyra.tool.github.{name}"]
            assert item["availability"] == "requires_configuration"
            assert item["blocking_reasons"][0]["code"] == "secret_not_configured"
        assert all(
            item["availability"] == "requires_configuration"
            for item in resources
            if item["kind"] == "skill"
        )
        assert all(
            item["availability"] == "design_only"
            for item in resources
            if item["kind"] == "template"
        )
        assert by_id["veyra.mcp.call"]["availability"] == "requires_configuration"
        for item in resources:
            detail = client.get(
                f"/api/v1/resources/{item['resource_id']}/versions/{item['version']}"
            ).json()
            assert detail == item
            assert (
                item["content_hash"]
                == catalog.by_reference(item["reference"])["content_hash"]
            )
            assert not (
                item["availability"] == "ready"
                and item["runtime_status"] != "supported"
            )
        assert catalog.resources() == raw
        filtered = client.get("/api/v1/resources?availability=ready").json()
        assert all(item["availability"] == "ready" for item in filtered["resources"])


def test_projection_checks_adapter_and_overlays(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        projection = client.app.state.resource_readiness
        raw = projection.catalog.by_reference("veyra.tool.filesystem.read@1.0.0")
        absent = {**raw, "spec": {**raw["spec"], "adapter": "missing"}}
        assert projection.project(absent)["availability"] == "unavailable"
        for state in ("disabled", "quarantined", "unavailable", "design_only"):
            item = projection.project({**raw, "availability": state})
            assert item["availability"] == state
            assert item["blocking_reasons"]
        configured = projection.catalog.by_reference("veyra.skill.research-brief@1.0.0")
        projection.model.transport = object()
        assert projection.project(configured)["availability"] == "ready"


def test_host_credential_changes_projection_not_project_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _client(tmp_path) as client:
        project = client.post("/api/v1/projects", json={}).json()
        url = f"/api/v1/projects/{project['project_id']}/resources"
        detail_url = "/api/v1/resources/veyra.tool.github.read/versions/1.0.0"
        before = client.get(detail_url).json()
        bound = client.post(url, json={"reference": before["reference"]}).json()
        selected = next(
            item for item in bound["resources"] if item["scope"] == "project"
        )
        assert selected["availability"] == before["availability"]
        manifest = Path(project["root_path"]) / "project.vproject.yaml"
        original = manifest.read_bytes()
        monkeypatch.setattr(
            MacOSKeychainSecretStore, "get", lambda self, ref: "test-value"
        )
        after = client.get(detail_url).json()
        assert after["availability"] == "ready"
        assert after["runtime_status"] == "supported"
        assert after["content_hash"] == before["content_hash"]
        assert "test-value" not in str(after)
        selected = next(
            item
            for item in client.get(url).json()["resources"]
            if item["scope"] == "project"
        )
        assert selected["availability"] == "ready"
        assert selected["binding_status"] == "current"
        assert selected["bound_content_hash"] == before["content_hash"]
        assert manifest.read_bytes() == original


def test_mcp_projection_requires_review_command_and_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = ScriptedMcpTransport(
        tools=[{"name": "echo", "inputSchema": {"type": "object", "properties": {}}}],
        calls={},
    )
    app = create_app(
        LocalSettings(
            database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
            project_storage_root=tmp_path / "projects",
        ),
        mcp_transport_factory=lambda *_args: transport,
    )
    with TestClient(app) as client:
        server = client.post(
            "/api/v1/mcp/servers",
            json={"name": "test", "command": "missing-veyra-command"},
        ).json()["server"]
        prefix = f"/api/v1/mcp/servers/{server['server_id']}"
        tool = client.post(prefix + "/discover").json()["tools"][0]
        assert tool["availability"] == "unavailable"
        approved = client.post(
            prefix + f"/tools/{tool['resource_id']}/versions/1.0.0/approve"
        ).json()["resource"]
        assert approved["availability"] == "requires_configuration"
        assert approved["blocking_reasons"][0]["code"] == "mcp_command_missing"
        monkeypatch.setattr(
            "veyra_agent_platform.local.resources.readiness.shutil.which",
            lambda _command: "/test/command",
        )
        url = f"/api/v1/resources/{tool['resource_id']}/versions/1.0.0"
        assert client.get(url).json()["availability"] == "ready"
        assert client.get(url).json()["content_hash"] == approved["content_hash"]
        client.patch(prefix, json={"enabled": False})
        assert client.get(url).json()["availability"] == "disabled"
