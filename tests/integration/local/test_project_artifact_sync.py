from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings


def _settings(tmp_path: Path) -> LocalSettings:
    return LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )


def test_local_artifact_manifest_is_portable_and_metadata_only(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        project = client.post("/api/v1/projects", json={"name": "Artifact Sync"}).json()
        project_id = project["project_id"]
        agent = client.post(
            f"/api/v1/projects/{project_id}/agents",
            json={"mode": "blank", "name": "Portable Agent"},
        )
        assert agent.status_code == 201
        workflow = client.post(f"/api/v1/projects/{project_id}/workflows", json={})
        assert workflow.status_code == 201
        knowledge = client.post(
            f"/api/v1/projects/{project_id}/knowledge",
            json={"name": "Metadata Only", "text": "private source text"},
        )
        assert knowledge.status_code == 201

        manifest = client.get(f"/api/v1/projects/{project_id}/artifact-sync/manifest")
        assert manifest.status_code == 200
        kinds = {item["artifact_kind"] for item in manifest.json()["artifacts"]}
        assert {"agent", "workflow", "knowledge_metadata"} <= kinds
        assert "private source text" not in manifest.text
        assert str(tmp_path) not in manifest.text

        agent_id = agent.json()["agent_id"]
        payload = client.get(
            f"/api/v1/projects/{project_id}/artifact-sync/agent/{agent_id}"
        )
        assert payload.status_code == 200
        body = payload.json()["artifact"]
        assert body["artifact_kind"] == "agent"
        assert "source_path" not in json.dumps(body)
        assert str(tmp_path) not in json.dumps(body)


def test_local_artifact_materialization_rejects_forbidden_payload(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        project = client.post(
            "/api/v1/projects", json={"name": "Artifact Reject"}
        ).json()
        project_id = project["project_id"]
        response = client.post(
            f"/api/v1/projects/{project_id}/artifact-sync/materialize",
            json={
                "envelope": {
                    "project_id": project_id,
                    "artifact_kind": "agent",
                    "artifact_id": "018f4b7e-1c2d-7abc-8def-1234567890ab",
                    "schema_version": "project.artifact.v1",
                    "content_hash": "0" * 64,
                    "revision": 1,
                    "deleted": False,
                    "immutable": False,
                    "payload": {"source": {"local_path": "/Users/private"}},
                }
            },
        )
        assert response.status_code == 422


def test_local_second_device_materializes_agent_workflow_and_knowledge_metadata(
    tmp_path: Path,
) -> None:
    source_settings = _settings(tmp_path / "source")
    receiver_settings = _settings(tmp_path / "receiver")
    with TestClient(create_app(source_settings)) as source_client:
        source_project = source_client.post(
            "/api/v1/projects", json={"name": "Artifact Source"}
        ).json()
        project_id = source_project["project_id"]
        agent = source_client.post(
            f"/api/v1/projects/{project_id}/agents",
            json={"mode": "blank", "name": "Portable Agent"},
        ).json()
        workflow = source_client.post(
            f"/api/v1/projects/{project_id}/workflows", json={}
        ).json()
        knowledge = source_client.post(
            f"/api/v1/projects/{project_id}/knowledge",
            json={"name": "Portable Knowledge", "text": "source stays local"},
        ).json()
        manifest = source_client.get(
            f"/api/v1/projects/{project_id}/artifact-sync/manifest"
        ).json()["artifacts"]
        envelopes = [
            source_client.get(
                f"/api/v1/projects/{project_id}/artifact-sync/"
                f"{item['artifact_kind']}/{item['artifact_id']}"
            ).json()["artifact"]
            for item in manifest
        ]

    with TestClient(create_app(receiver_settings)) as receiver_client:
        receiver = receiver_client.post(
            "/api/v1/projects", json={"name": "Receiver"}
        ).json()
        receiver_root = Path(receiver["root_path"])
    manifest_path = receiver_root / "project.vproject.yaml"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_data["project_id"] = project_id
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")
    database_path = tmp_path / "receiver" / "app.sqlite3"
    for suffix in ("", "-wal", "-shm"):
        Path(f"{database_path}{suffix}").unlink(missing_ok=True)

    with TestClient(create_app(receiver_settings)) as receiver_client:
        opened = receiver_client.post(
            "/api/v1/projects/open", json={"root_path": str(receiver_root)}
        )
        assert opened.status_code == 200
        assert opened.json()["project_id"] == project_id

        order = {
            "agent": 1,
            "agent_version": 2,
            "workflow": 3,
            "knowledge_metadata": 4,
        }
        for envelope in sorted(
            envelopes, key=lambda item: order[item["artifact_kind"]]
        ):
            materialized = receiver_client.post(
                f"/api/v1/projects/{project_id}/artifact-sync/materialize",
                json={"envelope": envelope},
            )
            assert materialized.status_code == 200, materialized.text

        summary = receiver_client.get(f"/api/v1/projects/{project_id}").json()
        assert summary["agents"][0]["agent_id"] == agent["agent_id"]
        assert summary["workflows"][0]["workflow_id"] == workflow["workflow_id"]
        assert summary["knowledge"][0]["knowledge_id"] == knowledge["knowledge_id"]
        knowledge_path = receiver_root / "knowledge" / "new-knowledge" / "document.md"
        assert (
            knowledge_path.read_text(encoding="utf-8").strip() != "source stays local"
        )
