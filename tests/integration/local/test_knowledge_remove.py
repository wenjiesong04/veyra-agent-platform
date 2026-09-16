from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings


@pytest.mark.parametrize(
    "usage",
    [
        "unused",
        "draft",
        "source",
        "divergent_draft",
        "unbound",
        "version",
        "removed_version",
        "other_project",
    ],
)
def test_knowledge_remove_usage_protection(tmp_path: Path, usage: str) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'state' / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        project = client.post("/api/v1/projects", json={}).json()
        p = project["project_id"]
        base = f"/api/v1/projects/{p}"
        knowledge = client.post(
            f"{base}/knowledge", json={"name": "Brief", "text": "ORBIT-731"}
        ).json()
        k = knowledge["knowledge_id"]
        ref = f"{k}@{knowledge['version']}"
        url = f"{base}/knowledge/{k}"
        document = Path(project["root_path"]) / knowledge["source_path"]
        manifest = Path(project["root_path"]) / "project.vproject.yaml"
        version_id = None
        snapshot = None
        agent = None
        if usage != "unused":
            agent = client.post(f"{base}/agents", json={"mode": "blank"}).json()
            a = agent["agent_id"]
            agent_url = f"{base}/agents/{a}"
            draft = client.get(f"{agent_url}/draft").json()
            unbound = deepcopy(draft["source"])
            bound = deepcopy(unbound)
            bound["extensions"]["veyra"]["knowledge_refs"] = [ref]
            bound["lock"][ref] = knowledge["source_file_hash"]
            source_path = Path(project["root_path"]) / agent["source_path"]
            if usage == "source":
                source_path.write_text(json.dumps(bound), encoding="utf-8")
            else:
                saved = client.patch(
                    f"{agent_url}/draft",
                    json={"source": bound, "expected_revision": draft["revision"]},
                    headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
                )
                assert saved.status_code == 200, saved.text
                draft = saved.json()
                if usage in {"version", "removed_version", "other_project"}:
                    committed = client.post(
                        f"{agent_url}/commit",
                        json={"expected_revision": draft["revision"]},
                        headers={
                            "If-Match": draft["etag"],
                            "Idempotency-Key": new_uuid7(),
                        },
                    )
                    assert committed.status_code == 200, committed.text
                    version_id = committed.json()["version_id"]
                    snapshot = dict(app.state.repository.version(version_id))
                if usage == "divergent_draft":
                    source_path.write_text(json.dumps(unbound), encoding="utf-8")
                if usage in {"version", "unbound"}:
                    saved = client.patch(
                        f"{agent_url}/draft",
                        json={
                            "source": unbound,
                            "expected_revision": draft["revision"],
                        },
                        headers={
                            "If-Match": draft["etag"],
                            "Idempotency-Key": new_uuid7(),
                        },
                    )
                    assert saved.status_code == 200, saved.text
                if usage == "removed_version":
                    assert client.delete(agent_url).status_code == 200
                    assert app.state.repository.agents(p) == []
                if usage == "other_project":
                    # Imported legacy references can share an ID across Projects.
                    other = client.post("/api/v1/projects", json={}).json()
                    other_id = other["project_id"]
                    root = Path(other["root_path"])
                    other_manifest = root / "project.vproject.yaml"
                    data = app.state.projects._parse_yaml(
                        other_manifest.read_text(), "Project"
                    )
                    original = app.state.projects._parse_yaml(
                        manifest.read_text(), "Project"
                    )
                    data["knowledge"] = original["knowledge"]
                    entry = data["knowledge"][0]
                    target = root / entry["path"]
                    target.mkdir()
                    for name in ("resource.yaml", "document.md"):
                        (target / name).write_bytes(
                            (document.parent / name).read_bytes()
                        )
                    other_manifest.write_text(json.dumps(data), encoding="utf-8")
                    app.state.projects.index(root)
                    assert app.state.repository.project_agent_versions(other_id) == []
                    p, base = other_id, f"/api/v1/projects/{other_id}"
                    url = f"{base}/knowledge/{k}"
                    document, manifest = target / "document.md", other_manifest
        previous_manifest = manifest.read_bytes()
        previous_files = {
            f.name: f.read_bytes() for f in document.parent.iterdir() if f.is_file()
        }
        previous_draft = (
            dict(app.state.repository.draft(agent["agent_id"])) if agent else None
        )
        previous_source = (
            source_path.read_bytes() if agent and source_path.exists() else None
        )
        response = client.delete(url)
        blocked = usage in {
            "draft",
            "source",
            "divergent_draft",
            "version",
            "removed_version",
        }
        assert response.status_code == (409 if blocked else 200), response.text
        if blocked:
            error = response.json()
            assert error["code"] == "knowledge_in_use"
            assert error["details"]["knowledge_id"] == k
            assert error["details"]["agent_id"] == agent["agent_id"]
            assert error["details"]["kind"] == (
                "agent_version"
                if version_id
                else "agent_draft"
                if usage == "divergent_draft"
                else "agent_source"
            )
            if version_id:
                assert error["details"]["version_id"] == version_id
            assert manifest.read_bytes() == previous_manifest
            assert {
                f.name: f.read_bytes() for f in document.parent.iterdir() if f.is_file()
            } == previous_files
            assert not (tmp_path / "trash" / "knowledge" / p).exists()
            assert client.get(url).status_code == 200
            assert len(client.get(f"{base}/knowledge").json()["knowledge"]) == 1
        else:
            assert response.json()["disposition"] == "trashed"
            assert response.json()["project"]["knowledge_count"] == 0
            assert not document.parent.exists()
            trash = tmp_path / "trash" / "knowledge" / p / k
            assert {
                f.name: f.read_bytes() for f in trash.iterdir() if f.is_file()
            } == previous_files
            assert client.get(url).status_code == 422
            assert client.get(f"{base}/knowledge").json()["knowledge"] == []
        if agent:
            assert dict(app.state.repository.draft(agent["agent_id"])) == previous_draft
            if previous_source is not None:
                assert source_path.read_bytes() == previous_source
        if version_id:
            assert dict(app.state.repository.version(version_id)) == snapshot
    with TestClient(create_app(settings)) as client:
        assert client.get(url).status_code == (200 if blocked else 422)
        if blocked:
            assert client.delete(url).status_code == 409
        if version_id:
            assert dict(client.app.state.repository.version(version_id)) == snapshot
