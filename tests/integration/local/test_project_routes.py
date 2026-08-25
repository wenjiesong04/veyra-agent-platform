from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings

ROOT = Path(__file__).resolve().parents[3]


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
        assert health.json()["database_revision"] == "local_0003_project_integrity"
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
