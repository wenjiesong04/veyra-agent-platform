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


def _profile(model_id: str = "kimi-k3") -> dict[str, str]:
    return {
        "provider": "openai_compatible",
        "base_url": "https://api.moonshot.cn/v1",
        "model_id": model_id,
        "api_key_env": "MOONSHOT_API_KEY",
    }


def test_project_profile_is_saved_and_agent_profile_can_override_it(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        created = client.post(
            "/api/v1/projects",
            json={"name": "Profile Project", "runtime_profile": _profile()},
        )
        assert created.status_code == 201
        project = created.json()
        assert project["runtime_profile"]["model_id"] == "kimi-k3"
        assert project["runtime_profile"]["configured"] is False

        project_id = project["project_id"]
        parent = client.post(
            f"/api/v1/projects/{project_id}/agents",
            json={"mode": "blank", "name": "Parent"},
        )
        assert parent.status_code == 201
        parent_id = parent.json()["agent_id"]
        child = client.post(
            f"/api/v1/projects/{project_id}/agents",
            json={
                "mode": "blank",
                "name": "Child",
                "parent_agent_id": parent_id,
            },
        )
        assert child.status_code == 201
        assert child.json()["parent_agent_id"] == parent_id

        project_profile = client.get(f"/api/v1/projects/{project_id}/runtime-profile")
        assert project_profile.status_code == 200
        assert project_profile.json()["profile"]["model_id"] == "kimi-k3"

        child_profile = client.patch(
            f"/api/v1/projects/{project_id}/agents/{child.json()['agent_id']}/runtime-profile",
            json={"profile": _profile("custom-model")},
        )
        assert child_profile.status_code == 200
        assert child_profile.json()["profile"]["model_id"] == "custom-model"
        refreshed = client.get(f"/api/v1/projects/{project_id}").json()
        child_record = next(
            agent
            for agent in refreshed["agents"]
            if agent["agent_id"] == child.json()["agent_id"]
        )
        assert child_record["parent_agent_id"] == parent_id
        assert child_record["runtime_profile"]["model_id"] == "custom-model"

        cleared = client.patch(
            f"/api/v1/projects/{project_id}/agents/{child.json()['agent_id']}/runtime-profile",
            json={"profile": None},
        )
        assert cleared.status_code == 200
        assert cleared.json()["profile"] is None


def test_runtime_profile_rejects_raw_key_and_invalid_environment_name(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        project = client.post("/api/v1/projects", json={"name": "Profile"}).json()
        response = client.patch(
            f"/api/v1/projects/{project['project_id']}/runtime-profile",
            json={
                "profile": {
                    **_profile(),
                    "api_key_env": "moonshot_api_key",
                    "api_key": "not-accepted",
                }
            },
        )
        assert response.status_code == 422
