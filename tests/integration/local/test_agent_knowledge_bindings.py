from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.library.knowledge_context import read_knowledge_context
from veyra_agent_platform.local.projects.service import ProjectError


@pytest.mark.parametrize("operation", ["save", "commit"])
def test_cross_project_knowledge_binding_rejected_before_write(
    tmp_path: Path, operation: str
) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'state' / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        owner = client.post("/api/v1/projects", json={"name": "Owner"}).json()
        project = client.post("/api/v1/projects", json={"name": "Agent Project"}).json()
        p = project["project_id"]
        knowledge = client.post(
            f"/api/v1/projects/{owner['project_id']}/knowledge/ingest",
            files={"file": ("thesis.txt", b"ORBIT-731")},
        ).json()
        agent = client.post(
            f"/api/v1/projects/{p}/agents", json={"mode": "blank"}
        ).json()
        a = agent["agent_id"]
        url = f"/api/v1/projects/{p}/agents/{a}"
        draft = client.get(f"{url}/draft").json()
        source = draft["source"]
        ref = f"{knowledge['knowledge_id']}@{knowledge['version']}"
        source["extensions"]["veyra"]["knowledge_refs"] = [ref]
        source["lock"][ref] = knowledge["source_file_hash"]
        source_path = Path(project["root_path"]) / agent["source_path"]
        if operation == "commit":
            source_path.write_text(json.dumps(source), encoding="utf-8")
            draft = client.post(f"{url}/draft/reload").json()
        previous_text = source_path.read_bytes()
        previous_draft = dict(app.state.repository.draft(a))
        headers = {"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()}
        response = (
            client.patch(
                f"{url}/draft",
                json={"source": source, "expected_revision": draft["revision"]},
                headers=headers,
            )
            if operation == "save"
            else client.post(
                f"{url}/commit",
                json={"expected_revision": draft["revision"]},
                headers=headers,
            )
        )
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "knowledge_unbound"
        assert source_path.read_bytes() == previous_text
        assert dict(app.state.repository.draft(a)) == previous_draft
        assert app.state.repository.agent_versions(a) == []
        assert app.state.repository.write_intents() == []


def test_owned_binding_save_commit_reload_preserves_pin_and_detects_stale(
    tmp_path: Path,
) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'state' / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        project = client.post("/api/v1/projects", json={"name": "Owned"}).json()
        p = project["project_id"]
        knowledge_url = f"/api/v1/projects/{p}/knowledge"
        knowledge = client.post(
            f"{knowledge_url}/ingest", files={"file": ("thesis.txt", b"ORBIT-731\r\n")}
        ).json()
        agent = client.post(
            f"/api/v1/projects/{p}/agents", json={"mode": "blank"}
        ).json()
        a = agent["agent_id"]
        url = f"/api/v1/projects/{p}/agents/{a}"
        draft = client.get(f"{url}/draft").json()
        ref = f"{knowledge['knowledge_id']}@{knowledge['version']}"
        pin = knowledge["source_file_hash"]
        assert pin != knowledge["processing"]["content_hash"]
        draft["source"]["extensions"]["veyra"]["knowledge_refs"] = [ref]
        draft["source"]["lock"][ref] = pin
        saved = client.patch(
            f"{url}/draft",
            json={"source": draft["source"], "expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert saved.status_code == 200, saved.text
        draft = saved.json()
        committed = client.post(
            f"{url}/commit",
            json={"expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert committed.status_code == 200, committed.text
        version_id = committed.json()["version_id"]
        snapshot = dict(app.state.repository.version(version_id))
        assert (
            client.post(
                f"{knowledge_url}/{knowledge['knowledge_id']}/index"
            ).status_code
            == 200
        )
        context, receipts = read_knowledge_context(
            app.state.projects, p, AgentSource.from_dict(draft["source"]), "ORBIT-731"
        )
        assert "ORBIT-731" in context
        assert receipts[0]["content_hash"] == pin
        assert (
            client.patch(
                f"{knowledge_url}/{knowledge['knowledge_id']}", json={"text": "Changed"}
            ).status_code
            == 200
        )
    app = create_app(settings)
    with TestClient(app) as client:
        reloaded = client.post(f"{url}/draft/reload").json()
        assert reloaded["source"]["extensions"]["veyra"]["knowledge_refs"] == [ref]
        assert reloaded["source"]["lock"][ref] == pin
        reloaded["source"]["description"] = "Keep stale pin while editing"
        saved = client.patch(
            f"{url}/draft",
            json={
                "source": reloaded["source"],
                "expected_revision": reloaded["revision"],
            },
            headers={"If-Match": reloaded["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["source"]["lock"][ref] == pin
        assert dict(app.state.repository.version(version_id)) == snapshot
        with pytest.raises(ProjectError) as error:
            read_knowledge_context(
                app.state.projects, p, AgentSource.from_dict(saved.json()["source"])
            )
        assert error.value.code == "knowledge_lock_mismatch"
