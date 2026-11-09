from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings


def _settings(tmp_path: Path) -> LocalSettings:
    return LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )


def test_local_project_sync_state_is_durable_and_does_not_change_project_source(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/v1/projects", json={"name": "Sync Acceptance", "description": "local"}
        )
        assert created.status_code == 201
        project = created.json()
        project_id = project["project_id"]
        root = Path(project["root_path"])

        initial = client.get(f"/api/v1/projects/{project_id}/sync")
        assert initial.status_code == 200
        assert initial.json()["state"] == "local_only"
        assert "root_path" not in initial.text

        pending = client.post(
            f"/api/v1/projects/{project_id}/sync/pending",
            json={"operation": "ensure"},
        )
        assert pending.status_code == 200
        assert pending.json()["state"] == "pending_upload"

        synced = client.post(
            f"/api/v1/projects/{project_id}/sync/record",
            json={
                "state": "synced",
                "cloud_revision": 1,
                "last_synced_hash": initial.json()["local_metadata_hash"],
                "remote_name": "Sync Acceptance",
                "remote_description": "local",
            },
        )
        assert synced.status_code == 200
        assert synced.json()["state"] == "synced"
        assert synced.json()["cloud_revision"] == 1

    with TestClient(create_app(settings)) as client:
        reloaded = client.get(f"/api/v1/projects/{project_id}/sync")
        assert reloaded.status_code == 200
        assert reloaded.json()["state"] == "synced"
        assert reloaded.json()["cloud_revision"] == 1
        local_project = client.get(f"/api/v1/projects/{project_id}")
        assert local_project.status_code == 200
        assert Path(local_project.json()["root_path"]) == root


def test_local_project_sync_conflict_retains_local_and_remote_metadata(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"name": "Local"}).json()
        project_id = project["project_id"]
        local_hash = client.get(f"/api/v1/projects/{project_id}/sync").json()[
            "local_metadata_hash"
        ]
        response = client.post(
            f"/api/v1/projects/{project_id}/sync/record",
            json={
                "state": "conflict",
                "cloud_revision": 2,
                "last_synced_hash": "b" * 64,
                "remote_name": "Remote",
                "remote_description": "Cloud copy",
                "error_code": "sync_conflict",
            },
        )
        assert response.status_code == 200
        assert response.json()["state"] == "conflict"
        assert response.json()["local_metadata_hash"] == local_hash
        assert response.json()["remote_name"] == "Remote"
        assert client.get(f"/api/v1/projects/{project_id}").json()["name"] == "Local"
