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


def test_workflow_version_usage_retains_pinned_agent_evidence(client: TestClient):
    p, _, _, url, draft = setup_call(client)
    saved = save(client, url, draft)
    committed = client.post(
        f"{url}/commit",
        json={"expected_revision": saved["revision"]},
        headers={"If-Match": saved["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert committed.status_code == 200
    version_id = committed.json()["version_id"]
    repository = client.app.state.library.repository
    original_snapshot = dict(repository.workflow_version(version_id))
    ref = saved["source"]["nodes"][1]["agent_ref"]
    saved["source"]["nodes"].pop(1)
    saved["source"]["transitions"] = [{"from": "start", "port": "next", "to": "output"}]
    saved["source"]["inputs"] = {"result": "string"}
    saved["source"]["lock"] = {}
    saved["source"]["ui"]["positions"].pop("call")
    save(client, url, saved)
    projects = client.app.state.projects
    assert ref not in projects.project_resource_usage(p)
    assert projects.project_resource_usage(p, include_versions=True)[ref] == [
        {
            "kind": "workflow",
            "resource_id": saved["source"]["workflow_id"],
            "name": saved["source"]["name"],
        }
    ]
    assert dict(repository.workflow_version(version_id)) == original_snapshot


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


def test_workflow_runtime_readiness_resolves_pinned_agent_snapshot(
    client: TestClient,
):
    _, _, version, url, draft = setup_call(client)
    save(client, url, draft)

    response = client.get(f"{url}/runtime-readiness")

    assert response.status_code == 200, response.text
    readiness = response.json()
    assert readiness["ready"] is True
    assert readiness["checks"] == [
        {
            "id": "agent_calls",
            "ready": True,
            "code": "ready",
            "detail": "All pinned Agent Runtime preflights passed.",
        },
        {
            "id": "permissions",
            "ready": True,
            "code": "ready",
            "detail": "Workflow permissions cover every pinned Agent.",
        },
        {
            "id": "tools",
            "ready": True,
            "code": "ready",
            "detail": (
                "All Workflow Tools are ready and do not require unsupported approval."
            ),
        },
        {
            "id": "limits",
            "ready": True,
            "code": "ready",
            "detail": "Workflow is within the Project execution limit.",
        },
    ]
    assert readiness["calls"][0]["version_id"] == version["version_id"]
    assert readiness["calls"][0]["source_hash"] == version["source_hash"]
    assert readiness["calls"][0]["ready"] is True


def test_workflow_test_run_snapshot_is_uncommitted_and_app_fails_closed(
    client: TestClient,
):
    _, _, _, url, draft = setup_call(client)
    saved = save(client, url, draft)
    started = client.post(
        f"{url}/run",
        json={"inputs": {"request": "box"}},
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert started.status_code == 200, started.text
    settled = await_workflow(client, url, started.json()["run_id"])

    repository = client.app.state.library.repository
    snapshot = repository.workflow_version(settled["version_id"])
    assert snapshot is not None
    assert snapshot["committed"] == 0
    assert client.get(f"{url}/versions").json()["versions"][0]["committed"] is False

    app_run = client.post(
        f"{url}/run",
        json={"inputs": {"request": "box"}, "source": "committed"},
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert app_run.status_code == 422, app_run.text
    assert app_run.json()["code"] == "workflow_has_no_committed_version"
    assert client.get(f"{url}/runs").json()["runs"] == [settled]
    assert saved["source"]["workflow_id"] == settled["workflow_id"]


def test_workflow_app_pins_committed_snapshot_while_draft_moves_forward(
    client: TestClient,
):
    project_id, agent_id, agent_a, url, draft = setup_call(client)
    saved_workflow = save(client, url, draft)

    studio_run = client.post(
        f"{url}/run",
        json={"inputs": {"request": "box"}},
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert studio_run.status_code == 200, studio_run.text
    draft_run = await_workflow(client, url, studio_run.json()["run_id"])
    assert (
        client.app.state.library.repository.workflow_version(draft_run["version_id"])[
            "committed"
        ]
        == 0
    )

    committed = client.post(
        f"{url}/commit",
        json={"expected_revision": saved_workflow["revision"]},
        headers={
            "If-Match": saved_workflow["etag"],
            "Idempotency-Key": new_uuid7(),
        },
    )
    assert committed.status_code == 200, committed.text
    committed_version_id = committed.json()["version_id"]
    assert committed.json()["committed"] is True
    assert committed_version_id == draft_run["version_id"]
    assert client.get(f"{url}/versions").json()["versions"][0]["committed"] is True

    agent_url = f"/api/v1/projects/{project_id}/agents/{agent_id}"
    agent_draft = client.get(f"{agent_url}/draft").json()
    agent_draft["source"]["nodes"][1]["mapping"]["result"] = "Version B: {{request}}"
    saved_agent = save(client, agent_url, agent_draft)
    committed_agent = client.post(
        f"{agent_url}/commit",
        json={"expected_revision": saved_agent["revision"]},
        headers={
            "If-Match": saved_agent["etag"],
            "Idempotency-Key": new_uuid7(),
        },
    )
    assert committed_agent.status_code == 200, committed_agent.text
    agent_b = committed_agent.json()

    workflow_draft = client.get(f"{url}/draft").json()
    workflow_source = workflow_draft["source"]
    agent_ref_b = f"{agent_id}@{agent_b['version_id']}"
    workflow_source["nodes"][1]["agent_ref"] = agent_ref_b
    workflow_source["lock"] = {agent_ref_b: agent_b["source_hash"]}
    save(client, url, workflow_draft)

    ready = client.get(
        f"{url}/runtime-readiness", params={"version_id": committed_version_id}
    )
    assert ready.status_code == 200, ready.text
    assert ready.json()["source_kind"] == "committed"
    assert ready.json()["version_id"] == committed_version_id
    assert ready.json()["calls"][0]["version_id"] == agent_a["version_id"]

    app_run = client.post(
        f"{url}/run",
        json={
            "inputs": {"request": "box"},
            "source": "committed",
            "version_id": committed_version_id,
        },
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert app_run.status_code == 200, app_run.text
    app_result = await_workflow(client, url, app_run.json()["run_id"])
    assert app_result["version_id"] == committed_version_id
    assert app_result["result"] == {"result": "Version A: box"}

    latest_run = client.post(
        f"{url}/run",
        json={"inputs": {"request": "box"}, "source": "committed"},
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert latest_run.status_code == 200, latest_run.text
    latest_result = await_workflow(client, url, latest_run.json()["run_id"])
    assert latest_result["version_id"] == committed_version_id
    assert latest_result["result"] == {"result": "Version A: box"}

    studio_latest = client.post(
        f"{url}/run",
        json={"inputs": {"request": "box"}},
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert studio_latest.status_code == 200, studio_latest.text
    studio_result = await_workflow(client, url, studio_latest.json()["run_id"])
    assert studio_result["version_id"] != committed_version_id
    assert studio_result["result"] == {"result": "Version B: box"}
    versions = client.get(f"{url}/versions").json()["versions"]
    assert {item["version_id"]: item["committed"] for item in versions} == {
        committed_version_id: True,
        studio_result["version_id"]: False,
    }


def test_workflow_app_rejects_foreign_or_tampered_versions(client: TestClient):
    project_id, _, _, url, draft = setup_call(client)
    saved = save(client, url, draft)
    committed = client.post(
        f"{url}/commit",
        json={"expected_revision": saved["revision"]},
        headers={"If-Match": saved["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert committed.status_code == 200, committed.text
    version_id = committed.json()["version_id"]

    other = client.post(
        f"/api/v1/projects/{project_id}/workflows", json={"name": "Other flow"}
    ).json()
    other_url = f"/api/v1/projects/{project_id}/workflows/{other['workflow_id']}"
    foreign = client.post(
        f"{other_url}/run",
        json={
            "inputs": {"request": "box"},
            "source": "committed",
            "version_id": version_id,
        },
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert foreign.status_code == 422, foreign.text
    assert foreign.json()["code"] == "workflow_version_not_found"

    with client.app.state.library.repository.transaction() as connection:
        connection.execute(
            "UPDATE workflow_versions SET source_hash = ? WHERE version_id = ?",
            ("0" * 64, version_id),
        )
    tampered = client.post(
        f"{url}/run",
        json={
            "inputs": {"request": "box"},
            "source": "committed",
            "version_id": version_id,
        },
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert tampered.status_code == 422, tampered.text
    assert tampered.json()["code"] == "workflow_version_invalid"
    assert client.get(f"{url}/runs").json()["runs"] == []


def test_workflow_tool_approval_requirement_fails_before_creating_run(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    project = client.post("/api/v1/projects", json={"name": "Approval flow"})
    assert project.status_code == 201, project.text
    project_id = project.json()["project_id"]
    workflow = client.post(
        f"/api/v1/projects/{project_id}/workflows", json={"name": "Write flow"}
    ).json()
    url = f"/api/v1/projects/{project_id}/workflows/{workflow['workflow_id']}"
    draft = client.get(f"{url}/draft").json()
    resources = client.get("/api/v1/resources", params={"kind": "tool"}).json()[
        "resources"
    ]
    entity_write = next(
        item for item in resources if item["resource_id"] == "veyra.tool.entity.write"
    )
    source = draft["source"]
    source["inputs"] = {"message": "string"}
    source["outputs"] = {"revision": "integer"}
    source["nodes"] = [
        {"id": "start", "component_type": "Start"},
        {
            "id": "write",
            "component_type": "Tool",
            "uses": entity_write["reference"],
        },
        {"id": "output", "component_type": "Output", "output_name": "revision"},
    ]
    source["transitions"] = [
        {"from": "start", "port": "next", "to": "write"},
        {"from": "write", "port": "next", "to": "output"},
    ]
    source["lock"] = {entity_write["reference"]: entity_write["content_hash"]}
    source["extensions"]["veyra"]["permissions"]["tools"] = ["veyra.tool.entity.write"]
    saved = save(client, url, draft)

    runtime_tools = client.app.state.workflow_runtime.runtime.tools
    actual_authorize = runtime_tools.authorize

    def require_approval(**kwargs):
        authorization = actual_authorize(**kwargs)
        from dataclasses import replace

        return replace(authorization, approval_required=True)

    def forbidden_execute(**kwargs):
        raise AssertionError("approval-required Workflow Tool must not execute")

    monkeypatch.setattr(runtime_tools, "authorize", require_approval)
    monkeypatch.setattr(runtime_tools, "execute", forbidden_execute)

    readiness = client.get(f"{url}/runtime-readiness")
    assert readiness.status_code == 200, readiness.text
    tool_check = next(
        item for item in readiness.json()["checks"] if item["id"] == "tools"
    )
    assert tool_check["ready"] is False
    assert (
        readiness.json()["tools"][0]["code"] == "workflow_tool_approval_not_supported"
    )

    started = client.post(
        f"{url}/run",
        json={"inputs": {"message": "track this"}},
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert started.status_code == 422, started.text
    assert started.json()["code"] == "workflow_tool_approval_not_supported"
    assert client.get(f"{url}/runs").json()["runs"] == []
    with client.app.state.library.repository._connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM entity_records WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0]
            == 0
        )
    assert saved["revision"] == 1


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


def _commit_transform_agent(
    client: TestClient,
    project_id: str,
    source: dict,
) -> dict:
    agent_url = f"/api/v1/projects/{project_id}/agents/{source['agent_id']}"
    draft = client.get(f"{agent_url}/draft").json()
    committed = client.post(
        f"{agent_url}/commit",
        json={"expected_revision": draft["revision"]},
        headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert committed.status_code == 200, committed.text
    return committed.json()


def _transform_agent(
    slug: str, inputs: dict, outputs: dict, mapping: dict[str, str]
) -> dict:
    source = agent_source()
    source.update(slug=slug, name=slug, inputs=inputs, outputs=outputs)
    source["nodes"][1]["mapping"] = mapping
    source["nodes"][2]["output_name"] = next(iter(outputs))
    source["extensions"]["veyra"]["secret_refs"] = []
    return source


def _committed_verifier_workflow(
    client: TestClient,
    project_id: str,
    *,
    inputs: dict,
    outputs: dict,
    calls: list[dict],
    versions: list[dict],
    checks: list[str],
) -> tuple[str, str]:
    response = client.post(
        f"/api/v1/projects/{project_id}/workflows",
        json={"name": "Verified typed outputs"},
    )
    assert response.status_code == 201, response.text
    workflow_id = response.json()["workflow_id"]
    url = f"/api/v1/projects/{project_id}/workflows/{workflow_id}"
    draft = client.get(f"{url}/draft").json()
    nodes = [
        {"id": "start", "component_type": "Start"},
        *calls,
        {"id": "verify", "component_type": "Verifier", "checks": checks},
        {
            "id": "output",
            "component_type": "Output",
            "output_name": next(iter(outputs)),
        },
    ]
    ordered = ["start", *(call["id"] for call in calls), "verify"]
    draft["source"].update(
        inputs=inputs,
        outputs=outputs,
        nodes=nodes,
        transitions=[
            {"from": before, "port": "next", "to": after}
            for before, after in zip(ordered, ordered[1:], strict=False)
        ]
        + [
            {"from": "verify", "port": "passed", "to": "output"},
            {"from": "verify", "port": "failed", "to": "output"},
        ],
        lock={
            call["agent_ref"]: version["source_hash"]
            for call, version in zip(calls, versions, strict=True)
        },
        ui={
            "positions": {
                node["id"]: {"x": index * 180, "y": 0}
                for index, node in enumerate(nodes)
            }
        },
    )
    draft["source"]["extensions"]["veyra"]["verification"] = {
        "required": True,
        "checks": checks,
    }
    saved = save(client, url, draft)
    committed = client.post(
        f"{url}/commit",
        json={"expected_revision": saved["revision"]},
        headers={"If-Match": saved["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert committed.status_code == 200, committed.text
    return url, committed.json()["version_id"]


def test_committed_workflow_verifies_object_and_image_after_two_unverified_agents(
    client: TestClient,
):
    analyzer = _transform_agent(
        "analyzer",
        {"request": "string", "facts": "object"},
        {"analysis": "object"},
        {"analysis": "{{facts}}"},
    )
    renderer = _transform_agent(
        "renderer",
        {"photo": "image", "analysis": "object"},
        {"render": "image", "result": "object"},
        {"render": "{{photo}}", "result": "{{analysis}}"},
    )
    response = client.post(
        "/api/v1/projects",
        json={"name": "Typed output regression", "agents": [analyzer, renderer]},
    )
    assert response.status_code == 201, response.text
    project_id = response.json()["project_id"]
    for source, agent in zip(
        (analyzer, renderer), response.json()["agents"], strict=True
    ):
        source["agent_id"] = agent["agent_id"]
    versions = [
        _commit_transform_agent(client, project_id, source)
        for source in (analyzer, renderer)
    ]
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )
    uploaded = client.post(
        f"/api/v1/projects/{project_id}/artifacts",
        files={"file": ("fixture.png", png, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    photo = {
        "kind": "artifact",
        "artifact_id": uploaded.json()["artifact_id"],
        "media_type": "image/png",
        "filename": "fixture.png",
    }
    calls = [
        {
            "id": "analyze",
            "component_type": "AgentCall",
            "agent_ref": f"{analyzer['agent_id']}@{versions[0]['version_id']}",
            "input_mapping": {"request": "request", "facts": "facts"},
            "output_mapping": {"analysis": "analysis"},
        },
        {
            "id": "render",
            "component_type": "AgentCall",
            "agent_ref": f"{renderer['agent_id']}@{versions[1]['version_id']}",
            "input_mapping": {"photo": "photo", "analysis": "analysis"},
            "output_mapping": {"render": "render", "result": "result"},
        },
    ]
    url, version_id = _committed_verifier_workflow(
        client,
        project_id,
        inputs={"request": "string", "photo": "image", "facts": "object"},
        outputs={"render": "image", "result": "object"},
        calls=calls,
        versions=versions,
        checks=["output.not_empty", "required_fields:result", "schema_valid"],
    )
    facts = {"summary": "A controlled design", "options": ["recyclable"]}
    payload = {
        "inputs": {"request": "prepare a design", "photo": photo, "facts": facts},
        "source": "committed",
        "version_id": version_id,
    }
    key = new_uuid7()
    started = client.post(f"{url}/run", json=payload, headers={"Idempotency-Key": key})
    assert started.status_code == 200, started.text
    settled = await_workflow(client, url, started.json()["run_id"])
    assert settled["status"] == "verified", settled
    assert settled["result"] == {"render": photo, "result": facts}
    assert settled["version_id"] == version_id
    assert len(settled["children"]) == 2
    assert [child["status"] for child in settled["children"]] == [
        "unverified",
        "unverified",
    ]
    assert [child["version_id"] for child in settled["children"]] == [
        version["version_id"] for version in versions
    ]
    events = client.get(f"{url}/runs/{settled['run_id']}/events").text
    assert '"kind":"verifier.result"' in events
    assert '"passed":true' in events
    assert (
        client.get(
            f"/api/v1/projects/{project_id}/artifacts/{photo['artifact_id']}/content"
        ).content
        == png
    )
    replay = client.post(f"{url}/run", json=payload, headers={"Idempotency-Key": key})
    assert replay.status_code == 200, replay.text
    assert replay.json()["run_id"] == settled["run_id"]
    assert len(client.get(f"{url}/runs").json()["runs"]) == 1
    for source in (analyzer, renderer):
        children = client.get(
            f"/api/v1/projects/{project_id}/agents/{source['agent_id']}/runs"
        ).json()["runs"]
        assert len(children) == 1


@pytest.mark.parametrize(
    "value,field,check,expected_status",
    [
        ("", "string", "output.not_empty", "unverified"),
        (0, "integer", "required_fields:result", "verified"),
        (False, "boolean", "required_fields:result", "verified"),
    ],
)
def test_workflow_verifier_checks_only_declared_output_and_preserves_scalars(
    client: TestClient, value: object, field: str, check: str, expected_status: str
):
    source = _transform_agent(
        "scalar-output",
        {"request": "string", "value": field},
        {"result": field},
        {"result": "{{value}}"},
    )
    response = client.post(
        "/api/v1/projects", json={"name": "Output checks", "agents": [source]}
    )
    assert response.status_code == 201, response.text
    project_id = response.json()["project_id"]
    source["agent_id"] = response.json()["agents"][0]["agent_id"]
    version = _commit_transform_agent(client, project_id, source)
    url, version_id = _committed_verifier_workflow(
        client,
        project_id,
        inputs={"request": "string", "value": field},
        outputs={"result": field},
        calls=[
            {
                "id": "call",
                "component_type": "AgentCall",
                "agent_ref": f"{source['agent_id']}@{version['version_id']}",
                "input_mapping": {"request": "request", "value": "value"},
                "output_mapping": {"result": "result"},
            }
        ],
        versions=[version],
        checks=[check],
    )
    started = client.post(
        f"{url}/run",
        json={
            "inputs": {"request": "non-empty input is not output", "value": value},
            "source": "committed",
            "version_id": version_id,
        },
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert started.status_code == 200, started.text
    settled = await_workflow(client, url, started.json()["run_id"])
    assert settled["status"] == expected_status, settled
    assert settled["result"] == {"result": value}
    assert type(settled["result"]["result"]) is type(value)
    events = client.get(f"{url}/runs/{settled['run_id']}/events").text
    assert '"kind":"verifier.result"' in events
    expected_pass = "true" if expected_status == "verified" else "false"
    assert f'"passed":{expected_pass}' in events
