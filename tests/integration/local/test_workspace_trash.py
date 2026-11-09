from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings


def test_managed_project_and_agent_move_through_veyra_trash(tmp_path: Path) -> None:
    managed_root = tmp_path / "application-data" / "projects"
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=managed_root,
    )
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/v1/projects", json={"name": "Keep"})
        assert created.status_code == 201
        project = created.json()
        project_id = project["project_id"]
        agent = client.post(
            f"/api/v1/projects/{project_id}/agents",
            json={"mode": "blank", "name": "Review helper"},
        )
        assert agent.status_code == 201
        agent_id = agent.json()["agent_id"]

        removed_agent = client.delete(
            f"/api/v1/projects/{project_id}/agents/{agent_id}"
        )
        assert removed_agent.status_code == 200
        assert removed_agent.json()["disposition"] == "trashed"

        listed = client.get("/api/v1/trash")
        assert listed.status_code == 200
        payload = listed.json()
        assert payload["retention_days"] == 30
        agent_item = next(item for item in payload["items"] if item["id"] == agent_id)
        assert agent_item["kind"] == "agent"
        assert agent_item["restorable"] is True
        assert agent_item["project_id"] == project_id

        restored = client.post(
            f"/api/v1/trash/agent/{agent_id}/restore", json={"confirm": True}
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["restored"] is True
        summary = client.get(f"/api/v1/projects/{project_id}").json()
        assert [entry["agent_id"] for entry in summary["agents"]] == [agent_id]

        removed_again = client.delete(
            f"/api/v1/projects/{project_id}/agents/{agent_id}"
        )
        assert removed_again.status_code == 200
        purged = client.post(
            f"/api/v1/trash/agent/{agent_id}/purge", json={"confirm": True}
        )
        assert purged.status_code == 200
        empty = client.get("/api/v1/trash").json()
        assert all(item["id"] != agent_id for item in empty["items"])

        removed_project = client.delete(f"/api/v1/projects/{project_id}")
        assert removed_project.status_code == 200
        assert removed_project.json()["disposition"] == "trashed"
        missing_confirm = client.post(
            f"/api/v1/trash/project/{project_id}/restore", json={"confirm": False}
        )
        assert missing_confirm.status_code == 422
        trashed = client.get("/api/v1/trash").json()
        project_item = next(
            item for item in trashed["items"] if item["id"] == project_id
        )
        assert project_item["kind"] == "project"
        restored_project = client.post(
            f"/api/v1/trash/project/{project_id}/restore", json={"confirm": True}
        )
        assert restored_project.status_code == 200, restored_project.text
        assert client.get(f"/api/v1/projects/{project_id}").status_code == 200


def test_new_default_project_skips_folders_held_by_trashed_projects(
    tmp_path: Path,
) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "application-data" / "projects",
    )
    with TestClient(create_app(settings)) as client:
        first = client.post("/api/v1/projects", json={"description": ""})
        second = client.post("/api/v1/projects", json={"description": ""})
        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text
        trashed_id = second.json()["project_id"]
        trashed_name = second.json()["name"]
        removed = client.delete(f"/api/v1/projects/{trashed_id}")
        assert removed.json()["disposition"] == "trashed"

        replacement = client.post("/api/v1/projects", json={"description": ""})
        assert replacement.status_code == 201, replacement.text
        assert replacement.json()["name"] not in {first.json()["name"], trashed_name}

        restored = client.post(
            f"/api/v1/trash/project/{trashed_id}/restore", json={"confirm": True}
        )
        assert restored.status_code == 200, restored.text
        assert client.get(f"/api/v1/projects/{trashed_id}").json()["name"] == (
            trashed_name
        )
