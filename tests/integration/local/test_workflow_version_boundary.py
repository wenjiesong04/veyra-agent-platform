from __future__ import annotations

import io
import json
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings

ROOT = Path(__file__).resolve().parents[3]


def agent_source() -> dict:
    source = json.loads(
        (ROOT / "contracts/fixtures/valid/github-triage.vagent.yaml").read_text()
    )
    source.update(
        agent_id=new_uuid7(),
        slug="writer",
        name="Writer",
        inputs={"request": "string"},
        outputs={"result": "string"},
        nodes=[
            {"id": "start", "component_type": "Start"},
            {
                "id": "compose",
                "component_type": "Transform",
                "mapping": {"result": "Version A: {{request}}"},
            },
            {"id": "output", "component_type": "Output", "output_name": "result"},
        ],
        transitions=[
            {"from": "start", "port": "next", "to": "compose"},
            {"from": "compose", "port": "next", "to": "output"},
        ],
        ui={
            "positions": {
                "start": {"x": 0, "y": 0},
                "compose": {"x": 200, "y": 0},
                "output": {"x": 400, "y": 0},
            }
        },
    )
    source["extensions"]["veyra"]["permissions"] = {"network_hosts": [], "tools": []}
    source["extensions"]["veyra"]["verification"] = {"required": False, "checks": []}
    return source


@pytest.fixture
def client(tmp_path: Path):
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'db.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as value:
        yield value


def setup_call(client: TestClient):
    response = client.post(
        "/api/v1/projects", json={"name": "Packaging", "agents": [agent_source()]}
    )
    assert response.status_code == 201, response.text
    project = response.json()
    p, a = project["project_id"], project["agents"][0]["agent_id"]
    agent_url = f"/api/v1/projects/{p}/agents/{a}"
    draft = client.get(f"{agent_url}/draft").json()
    version = client.post(
        f"{agent_url}/commit",
        json={"expected_revision": draft["revision"]},
        headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
    ).json()
    workflow = client.post(
        f"/api/v1/projects/{p}/workflows", json={"name": "Packaging flow"}
    ).json()
    url = f"/api/v1/projects/{p}/workflows/{workflow['workflow_id']}"
    draft = client.get(f"{url}/draft").json()
    source = draft["source"]
    ref = f"{a}@{version['version_id']}"
    source.update(
        inputs={"request": "string"},
        nodes=[
            {"id": "start", "component_type": "Start"},
            {
                "id": "call",
                "component_type": "AgentCall",
                "agent_ref": ref,
                "input_mapping": {"request": "request"},
                "output_mapping": {"result": "result"},
            },
            {"id": "output", "component_type": "Output", "output_name": "result"},
        ],
        transitions=[
            {"from": "start", "port": "next", "to": "call"},
            {"from": "call", "port": "next", "to": "output"},
        ],
        lock={ref: version["source_hash"]},
        ui={
            "positions": {
                "start": {"x": 0, "y": 0},
                "call": {"x": 200, "y": 0},
                "output": {"x": 400, "y": 0},
            }
        },
    )
    return p, a, version, url, draft


def save(client: TestClient, url: str, draft: dict) -> dict:
    response = client.patch(
        f"{url}/draft",
        json={"source": draft["source"], "expected_revision": draft["revision"]},
        headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_workflow_rejects_missing_version_wrong_digest_and_invalid_mapping(
    client: TestClient,
):
    p, a, version, url, draft = setup_call(client)
    initial = deepcopy(draft["source"])
    for variant, code in (
        ("missing", "workflow_version_not_found"),
        ("hash", "workflow_lock_mismatch"),
        ("mapping", "workflow_input_mapping_invalid"),
    ):
        source = deepcopy(initial)
        if variant == "missing":
            ref = f"{a}@{new_uuid7()}"
            source["nodes"][1]["agent_ref"] = ref
            source["lock"] = {ref: version["source_hash"]}
        elif variant == "hash":
            source["lock"] = {source["nodes"][1]["agent_ref"]: "0" * 64}
        else:
            source["nodes"][1]["input_mapping"] = {"request": "not_available"}
        draft["source"] = source
        draft = save(client, url, draft)
        validation = client.post(f"{url}/validate")
        assert validation.status_code >= 400, validation.text
        assert validation.json()["code"] == code
        committed = client.post(
            f"{url}/commit",
            json={"expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert committed.status_code >= 400
        assert client.get(f"{url}/versions").json()["versions"] == []


def test_package_retains_resources_and_remaps_pinned_agent_version(client: TestClient):
    p, a, version, url, draft = setup_call(client)
    save(client, url, draft)
    knowledge = client.post(
        f"/api/v1/projects/{p}/knowledge",
        json={"name": "Brand", "text": "# Brand\nUse recyclable packaging."},
    )
    assert knowledge.status_code == 201, knowledge.text
    exported = client.get(f"/api/v1/projects/{p}/export")
    assert exported.status_code == 200, exported.text
    imported = client.post(
        "/api/v1/projects/import",
        files={"file": ("pack.vproject.zip", exported.content, "application/zip")},
    )
    assert imported.status_code == 201, imported.text
    project = imported.json()
    assert len(project["workflows"]) == len(project["knowledge"]) == 1
    assert project["project_id"] != p
    assert project["agents"][0]["agent_id"] != a
    new_url = (
        f"/api/v1/projects/{project['project_id']}/workflows/"
        f"{project['workflows'][0]['workflow_id']}"
    )
    reloaded = client.get(f"{new_url}/draft").json()["source"]
    ref = reloaded["nodes"][1]["agent_ref"]
    assert a not in ref and version["version_id"] not in ref
    assert client.post(f"{new_url}/validate").status_code == 200
    docs = client.get(
        f"/api/v1/projects/{project['project_id']}/knowledge/{project['knowledge'][0]['knowledge_id']}"
    ).json()
    assert "recyclable" in docs["text"]
    reexported = client.get(f"/api/v1/projects/{project['project_id']}/export")
    assert reexported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(reexported.content)) as archive:
        assert any("/versions/" in name for name in archive.namelist())


def await_workflow(client: TestClient, url: str, run_id: str) -> dict:
    import time

    for _ in range(160):
        result = client.get(f"{url}/runs/{run_id}").json()
        if result["status"] != "running":
            return result
        time.sleep(0.025)
    raise AssertionError("Workflow did not settle")


def test_workflow_executes_pinned_version_after_agent_draft_changes(client: TestClient):
    p, a, version, url, draft = setup_call(client)
    save(client, url, draft)
    agent_url = f"/api/v1/projects/{p}/agents/{a}"
    current = client.get(f"{agent_url}/draft").json()
    current["source"]["nodes"][1]["mapping"]["result"] = "Version B: {{request}}"
    save(client, agent_url, current)
    key = new_uuid7()
    started = client.post(
        f"{url}/run",
        json={"inputs": {"request": "box"}},
        headers={"Idempotency-Key": key},
    )
    assert started.status_code == 200, started.text
    settled = await_workflow(client, url, started.json()["run_id"])
    assert settled["status"] == "unverified", settled
    assert settled["result"] == {"result": "Version A: box"}
    assert settled["children"][0]["version_id"] == version["version_id"]
    replay = client.post(
        f"{url}/run",
        json={"inputs": {"request": "box"}},
        headers={"Idempotency-Key": key},
    ).json()
    assert replay["run_id"] == settled["run_id"]
    assert len(client.get(f"{agent_url}/runs").json()["runs"]) == 1
    events = client.get(
        f"{url}/runs/{settled['run_id']}/events", headers={"Last-Event-ID": "2"}
    ).text
    assert "event: done" in events and "node.completed" in events
    assert "id: 1\n" not in events


@pytest.mark.parametrize(
    "decision,expected", [("approve", "Version A: box"), ("reject", "Declined")]
)
def test_workflow_approval_checkpoint_controls_next_agent(
    client: TestClient, decision: str, expected: str
):
    _, _, _, url, draft = setup_call(client)
    source = draft["source"]
    source["nodes"].extend(
        [
            {
                "id": "approval",
                "component_type": "HumanApproval",
                "prompt": "Run the design Agent?",
            },
            {
                "id": "decline",
                "component_type": "Transform",
                "mapping": {"result": "Declined"},
            },
        ]
    )
    source["ui"]["positions"].update(
        approval={"x": 100, "y": 0}, decline={"x": 200, "y": 100}
    )
    source["transitions"] = [
        {"from": "start", "port": "next", "to": "approval"},
        {"from": "approval", "port": "approved", "to": "call"},
        {"from": "approval", "port": "rejected", "to": "decline"},
        {"from": "call", "port": "next", "to": "output"},
        {"from": "decline", "port": "next", "to": "output"},
    ]
    save(client, url, draft)
    started = client.post(
        f"{url}/run",
        json={"inputs": {"request": "box"}},
        headers={"Idempotency-Key": new_uuid7()},
    ).json()
    waiting = await_workflow(client, url, started["run_id"])
    assert waiting["status"] == "waiting", waiting
    assert waiting["children"] == []
    key = new_uuid7()
    command_url = f"{url}/runs/{started['run_id']}/commands"
    command = client.post(
        command_url, json={"command": decision}, headers={"Idempotency-Key": key}
    )
    assert command.status_code == 200, command.text
    settled = await_workflow(client, url, started["run_id"])
    assert settled["result"] == {"result": expected}, settled
    assert len(settled["children"]) == (1 if decision == "approve" else 0)
    assert (
        client.post(
            command_url, json={"command": decision}, headers={"Idempotency-Key": key}
        ).status_code
        == 200
    )
