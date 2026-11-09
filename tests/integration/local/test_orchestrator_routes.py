from __future__ import annotations

import time
from contextlib import AbstractContextManager
from pathlib import Path

from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.config import LocalSettings

from .test_runtime_routes import ScriptedRuntimeTransport
from .verified_runtime_model import verified_client


def _client(tmp_path: Path) -> AbstractContextManager[TestClient]:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    return verified_client(settings, ScriptedRuntimeTransport("Work item done."))


def test_orchestrator_creates_and_dispatches_local_work_items(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project = client.post("/api/v1/projects", json={"name": "Orchestrator"})
        project_id = project.json()["project_id"]
        agent = client.post(
            f"/api/v1/projects/{project_id}/agents",
            json={"mode": "blank", "name": "Queued"},
        )
        agent_id = agent.json()["agent_id"]
        agent_url = f"/api/v1/projects/{project_id}/agents/{agent_id}"
        draft = client.get(f"{agent_url}/draft").json()
        committed = client.post(
            f"{agent_url}/commit",
            json={"expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert committed.status_code == 200, committed.text
        status = client.get("/api/v1/orchestrator/status")
        assert status.status_code == 200
        assert status.json()["execution_plane"] == "local"
        assert status.json()["cloud_execution"] is False

        created = client.post(
            f"/api/v1/projects/{project_id}/work-items",
            json={
                "title": "Run starter",
                "agent_id": agent_id,
                "inputs": {"request": "hello"},
            },
        )
        assert created.status_code == 201
        work_item_id = created.json()["work_item_id"]
        assert created.json()["status"] == "ready"

        blocked = client.post(
            f"/api/v1/projects/{project_id}/work-items",
            json={
                "title": "Depends",
                "agent_id": agent_id,
                "depends_on": [work_item_id],
                "inputs": {"request": "later"},
            },
        )
        assert blocked.json()["status"] == "backlog"
        blocked_dispatch = client.post(
            f"/api/v1/work-items/{blocked.json()['work_item_id']}/dispatch",
            json={"expected_attempt_number": 0},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert blocked_dispatch.status_code == 422

        dispatched = client.post(
            f"/api/v1/work-items/{work_item_id}/dispatch",
            json={"expected_attempt_number": 0},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert dispatched.status_code == 200
        assert dispatched.json()["run_id"]
        assert dispatched.json()["status"] in {"running", "waiting", "failed", "done"}

        deadline = time.monotonic() + 8
        current = dispatched.json()
        while time.monotonic() < deadline and current["status"] in {
            "running",
            "waiting",
        }:
            time.sleep(0.05)
            listed = client.get(f"/api/v1/projects/{project_id}/work-items")
            current = next(
                item
                for item in listed.json()["work_items"]
                if item["work_item_id"] == work_item_id
            )
        assert current["status"] in {"done", "failed"}

        cancelled = client.post(
            f"/api/v1/work-items/{blocked.json()['work_item_id']}/cancel"
        )
        assert cancelled.json()["status"] == "cancelled"
