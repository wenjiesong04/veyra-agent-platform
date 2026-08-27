from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings

ROOT = Path(__file__).resolve().parents[3]


def test_project_routes_create_open_list_and_get_empty_project(tmp_path: Path) -> None:
    settings = LocalSettings(database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}")
    root = tmp_path / "empty-project"
    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/v1/projects",
            json={"root_path": str(root), "name": "Empty"},
        )
        assert created.status_code == 201
        project = created.json()
        assert project["agents"] == []
        assert project["agent_count"] == 0
        assert project["indexed_at"]

        reopened = client.post("/api/v1/projects/open", json={"root_path": str(root)})
        assert reopened.status_code == 200
        assert reopened.json()["project_id"] == project["project_id"]
        listed = client.get("/api/v1/projects")
        assert listed.status_code == 200
        assert listed.json()["projects"] == [reopened.json()]
        fetched = client.get(f"/api/v1/projects/{project['project_id']}")
        assert fetched.status_code == 200
        assert fetched.json() == reopened.json()


def test_project_metadata_description_pinning_and_closed_patch_body(
    tmp_path: Path,
) -> None:
    settings = LocalSettings(database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}")
    first_root = tmp_path / "first"
    with TestClient(create_app(settings)) as client:
        first = client.post(
            "/api/v1/projects",
            json={
                "root_path": str(first_root),
                "name": "First",
                "description": "  Cafe\u0301 Project  ",
            },
        )
        assert first.status_code == 201
        first_project = first.json()
        assert first_project["description"] == "Café Project"
        assert first_project["pinned"] is False
        assert first_project["pinned_at"] is None
        manifest = json.loads((first_root / "project.vproject.yaml").read_text())
        assert manifest["description"] == "Café Project"

        second = client.post(
            "/api/v1/projects",
            json={"root_path": str(tmp_path / "second"), "name": "Second"},
        )
        assert second.status_code == 201
        pinned = client.patch(
            f"/api/v1/projects/{first_project['project_id']}", json={"pinned": True}
        )
        assert pinned.status_code == 200
        assert pinned.json()["pinned"] is True
        assert pinned.json()["pinned_at"]
        listed = client.get("/api/v1/projects").json()["projects"]
        assert [item["project_id"] for item in listed] == [
            first_project["project_id"],
            second.json()["project_id"],
        ]
        unpinned = client.patch(
            f"/api/v1/projects/{first_project['project_id']}", json={"pinned": False}
        )
        assert unpinned.status_code == 200
        assert unpinned.json()["pinned_at"] is None
        invalid = client.patch(
            f"/api/v1/projects/{first_project['project_id']}",
            json={"pinned": True, "other": True},
        )
        assert invalid.status_code == 422
        repinned = client.patch(
            f"/api/v1/projects/{first_project['project_id']}", json={"pinned": True}
        )
        assert repinned.status_code == 200
        assert "pinned_at" not in json.loads(
            (first_root / "project.vproject.yaml").read_text()
        )

    with TestClient(create_app(settings)) as restarted_client:
        restarted = restarted_client.get(
            f"/api/v1/projects/{first_project['project_id']}"
        )
    assert restarted.status_code == 200
    assert restarted.json()["pinned"] is True
    assert restarted.json()["pinned_at"] == repinned.json()["pinned_at"]


def test_project_description_length_returns_typed_contract_error(
    tmp_path: Path,
) -> None:
    settings = LocalSettings(database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}")
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/projects",
            json={
                "root_path": str(tmp_path / "too-long"),
                "name": "Too long",
                "description": "x" * 501,
            },
        )
    assert response.status_code == 422
    assert response.json()["code"] == "contract_invalid"


def test_nested_project_agent_routes_create_draft_validate_commit_and_export(
    tmp_path: Path,
) -> None:
    fixture_root = ROOT / "contracts" / "fixtures" / "project" / "agents"
    agents = [
        json.loads((fixture_root / slug / "agent.vagent.yaml").read_text())
        for slug in ("github-triage", "release-summary")
    ]
    settings = LocalSettings(database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}")
    with TestClient(create_app(settings)) as client:
        health = client.get("/api/v1/health")
        assert health.json()["database_ready"] is True
        assert health.json()["database_revision"] == "local_0004_project_metadata"
        created = client.post(
            "/api/v1/projects",
            json={
                "root_path": str(tmp_path / "project"),
                "name": "Example",
                "agents": agents,
            },
        )
        assert created.status_code == 201
        project = created.json()
        agent_id = project["agents"][0]["agent_id"]
        draft = client.get(
            f"/api/v1/projects/{project['project_id']}/agents/{agent_id}/draft"
        )
        assert draft.status_code == 200
        assert draft.headers["etag"] == draft.json()["etag"]
        assert (
            client.post(
                f"/api/v1/projects/{project['project_id']}/agents/{agent_id}/validate"
            ).json()["valid"]
            is True
        )
        committed = client.post(
            f"/api/v1/projects/{project['project_id']}/agents/{agent_id}/commit",
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert committed.status_code == 200
        exported = client.get(
            f"/api/v1/projects/{project['project_id']}/agents/{agent_id}/export"
        )
        assert exported.json()["source"]["agent_id"] == agent_id
