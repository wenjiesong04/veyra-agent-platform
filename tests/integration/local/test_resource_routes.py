from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            LocalSettings(
                database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
                project_storage_root=tmp_path / "projects",
            )
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
            "AgentCall",
        ]
