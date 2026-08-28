from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.wire import RunEvent
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings

ROOT = Path(__file__).resolve().parents[3]


def _source(
    nodes: list[dict[str, object]],
    transitions: list[dict[str, str]],
    inputs: dict[str, str],
) -> dict[str, object]:
    base = json.loads(
        (
            ROOT / "contracts/fixtures/project/agents/github-triage/agent.vagent.yaml"
        ).read_text()
    )
    base["agent_id"] = new_uuid7()
    base["slug"] = "runner"
    base["name"] = "Runner"
    base["nodes"] = nodes
    base["transitions"] = transitions
    base["inputs"] = inputs
    if any(node["component_type"] == "Verifier" for node in nodes):
        base["extensions"]["veyra"]["verification"] = {
            "required": True,
            "checks": ["output.not_empty"],
        }
    base["ui"] = {
        "positions": {
            node["id"]: {"x": index * 20, "y": 0} for index, node in enumerate(nodes)
        }
    }
    return base


def test_runtime_executes_persists_and_replays(tmp_path: Path) -> None:
    source = _source(
        [
            {"id": "start", "component_type": "Start"},
            {
                "id": "transform",
                "component_type": "Transform",
                "mapping": {"result": "Hello {{name}}"},
            },
            {"id": "output", "component_type": "Output", "output_name": "result"},
        ],
        [
            {"from": "start", "port": "next", "to": "transform"},
            {"from": "transform", "port": "next", "to": "output"},
        ],
        {"name": "string"},
    )
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        assert len(client.get("/api/v1/components").json()["components"]) == 8
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        key = new_uuid7()
        first = client.post(
            url, json={"inputs": {"name": "Ada"}}, headers={"Idempotency-Key": key}
        )
        assert first.status_code == 200
        assert first.json()["status"] == "unverified"
        assert first.json()["result"] == {"result": "Hello Ada"}
        replay = client.post(
            url, json={"inputs": {"name": "Ada"}}, headers={"Idempotency-Key": key}
        )
        assert replay.json()["run_id"] == first.json()["run_id"]
        detail = client.get(url + "s/" + first.json()["run_id"]).json()
        assert [event["kind"] for event in detail["events"]] == [
            "run.created",
            "run.started",
            "node.started",
            "node.completed",
            "node.started",
            "node.completed",
            "node.started",
            "node.completed",
            "run.completed",
        ]
        assert all(RunEvent.from_dict(event) for event in detail["events"])
    with TestClient(create_app(settings)) as restarted:
        assert len(restarted.get(url + "s").json()["runs"]) == 1


def test_runtime_condition_verifier_and_unsupported_nodes(tmp_path: Path) -> None:
    nodes = [
        {"id": "start", "component_type": "Start"},
        {
            "id": "condition",
            "component_type": "Condition",
            "expression": "flag == true",
        },
        {"id": "pass", "component_type": "Transform", "mapping": {"result": "ok"}},
        {"id": "fail", "component_type": "Transform", "mapping": {"result": "no"}},
        {"id": "verify", "component_type": "Verifier", "checks": ["output.not_empty"]},
        {"id": "output", "component_type": "Output", "output_name": "result"},
    ]
    transitions = [
        {"from": "start", "port": "next", "to": "condition"},
        {"from": "condition", "port": "true", "to": "pass"},
        {"from": "condition", "port": "false", "to": "fail"},
        {"from": "pass", "port": "next", "to": "verify"},
        {"from": "fail", "port": "next", "to": "verify"},
        {"from": "verify", "port": "passed", "to": "output"},
        {"from": "verify", "port": "failed", "to": "output"},
    ]
    source = _source(nodes, transitions, {"flag": "boolean"})
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        response = client.post(
            url,
            json={"inputs": {"flag": True}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert response.json()["status"] == "verified"
        assert response.json()["result"] == {"result": "ok"}


def test_runtime_rejects_tool_and_approval(tmp_path: Path) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    for component_type, extra in (
        ("Tool", {"uses": "demo.tool@1.0.0"}),
        ("HumanApproval", {"prompt": "Approve?"}),
    ):
        node = {"id": "blocked", "component_type": component_type, **extra}
        port = "next" if component_type == "Tool" else "approved"
        source = _source(
            [
                {"id": "start", "component_type": "Start"},
                node,
                {"id": "output", "component_type": "Output", "output_name": "result"},
            ],
            [
                {"from": "start", "port": "next", "to": "blocked"},
                {"from": "blocked", "port": port, "to": "output"},
            ]
            + (
                [{"from": "blocked", "port": "rejected", "to": "output"}]
                if component_type == "HumanApproval"
                else []
            ),
            {"issue": "string"},
        )
        if component_type == "Tool":
            source["extensions"]["veyra"]["permissions"]["tools"] = ["demo.tool"]
            source["lock"]["demo.tool@1.0.0"] = "b" * 64
        with TestClient(create_app(settings)) as client:
            project = client.post("/api/v1/projects", json={"agents": [source]}).json()
            agent = project["agents"][0]
            response = client.post(
                f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run",
                json={"inputs": {"issue": "one"}},
                headers={"Idempotency-Key": new_uuid7()},
            )
            assert response.json()["status"] == "failed"
            assert response.json()["error"]["code"] == "runtime_not_supported"
            detail = client.get(
                f"/api/v1/projects/{project['project_id']}/agents/"
                f"{agent['agent_id']}/runs/{response.json()['run_id']}"
            ).json()
            assert [event["kind"] for event in detail["events"]][-2:] == [
                "node.failed",
                "run.failed",
            ]
            assert all(RunEvent.from_dict(event) for event in detail["events"])
