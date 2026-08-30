from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.wire import RunEvent
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.runtime.provider import RuntimeCompletion

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
            assert response.json()["error"]["code"] == (
                "tool_not_registered"
                if component_type == "Tool"
                else "runtime_not_supported"
            )
            detail = client.get(
                f"/api/v1/projects/{project['project_id']}/agents/"
                f"{agent['agent_id']}/runs/{response.json()['run_id']}"
            ).json()
            assert [event["kind"] for event in detail["events"]][-2:] == [
                "node.failed",
                "run.failed",
            ]
            assert all(RunEvent.from_dict(event) for event in detail["events"])


def test_runtime_executes_catalogued_project_read_tool_and_records_receipt(
    tmp_path: Path,
) -> None:
    source = _source(
        [
            {"id": "start", "component_type": "Start"},
            {
                "id": "read",
                "component_type": "Tool",
                "uses": "veyra.tool.filesystem.read@1.0.0",
            },
            {"id": "output", "component_type": "Output", "output_name": "result"},
        ],
        [
            {"from": "start", "port": "next", "to": "read"},
            {"from": "read", "port": "next", "to": "output"},
        ],
        {"path": "string"},
    )
    source["extensions"]["veyra"]["permissions"] = {
        "network_hosts": [],
        "tools": ["veyra.tool.filesystem.read"],
        "filesystem_read_roots": ["project"],
        "filesystem_write_roots": [],
        "shell_workspace_only": False,
    }
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        source["lock"]["veyra.tool.filesystem.read@1.0.0"] = (
            client.app.state.resource_catalog.detail(
                "veyra.tool.filesystem.read", "1.0.0"
            )["content_hash"]
        )
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        Path(project["root_path"], "resources", "note.txt").write_text(
            "hello from the Project", encoding="utf-8"
        )
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        response = client.post(
            url,
            json={"inputs": {"path": "resources/note.txt"}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert response.status_code == 200
        assert response.json()["result"] == {"result": "hello from the Project"}
        detail = client.get(url + "s/" + response.json()["run_id"]).json()
        event_kinds = [event["kind"] for event in detail["events"]]
        assert [kind for kind in event_kinds if kind.startswith("tool.")] == [
            "tool.requested",
            "tool.started",
            "tool.completed",
        ]
        receipt = next(
            event["payload"]
            for event in detail["events"]
            if event["kind"] == "tool.completed"
        )
        assert receipt["permission"] == "allowed"
        assert receipt["relative_path"] == "resources/note.txt"
        assert receipt["output_digest"]


def test_runtime_executes_configured_agent_model_node(tmp_path: Path) -> None:
    source = _source(
        [
            {"id": "start", "component_type": "Start"},
            {
                "id": "agent",
                "component_type": "Agent",
                "model_ref": "model.primary",
                "system_prompt": "Return a concise answer.",
            },
            {"id": "output", "component_type": "Output", "output_name": "result"},
        ],
        [
            {"from": "start", "port": "next", "to": "agent"},
            {"from": "agent", "port": "next", "to": "output"},
        ],
        {"request": "string"},
    )

    class _FakeModel:
        def complete(self, **_: object) -> RuntimeCompletion:
            return RuntimeCompletion(content="model answer")

    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        client.app.state.runtime.model = _FakeModel()
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        response = client.post(
            url,
            json={"inputs": {"request": "hello"}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert response.status_code == 200
        assert response.json()["result"] == {"result": "model answer"}


def test_runtime_condition_and_output_failures_are_terminal(tmp_path: Path) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    nodes = [
        {"id": "start", "component_type": "Start"},
        {
            "id": "condition",
            "component_type": "Condition",
            "expression": r'flag == "\x"',
        },
        {"id": "output", "component_type": "Output", "output_name": "result"},
    ]
    source = _source(
        nodes,
        [
            {"from": "start", "port": "next", "to": "condition"},
            {"from": "condition", "port": "true", "to": "output"},
            {"from": "condition", "port": "false", "to": "output"},
        ],
        {"flag": "string"},
    )
    source["outputs"] = {"result": "string"}
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        failed = client.post(
            url,
            json={"inputs": {"flag": "yes"}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert failed.json()["status"] == "failed"
        assert failed.json()["error"]["code"] == "condition_invalid"
        detail = client.get(url + "s/" + failed.json()["run_id"]).json()
        assert detail["events"][-2]["kind"] == "node.failed"
        assert detail["events"][-1]["kind"] == "run.failed"


def test_runtime_startup_interrupts_orphan_run(tmp_path: Path) -> None:
    source = _source(
        [
            {"id": "start", "component_type": "Start"},
            {"id": "output", "component_type": "Output", "output_name": "name"},
        ],
        [{"from": "start", "port": "next", "to": "output"}],
        {"name": "string"},
    )
    source["outputs"] = {"name": "string"}
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        completed = client.post(
            url,
            json={"inputs": {"name": "Ada"}},
            headers={"Idempotency-Key": new_uuid7()},
        ).json()
        orphan_id = new_uuid7()
        with client.app.state.repository.transaction() as connection:
            client.app.state.repository.create_run(
                connection,
                run_id=orphan_id,
                project_id=project["project_id"],
                agent_id=agent["agent_id"],
                version_id=completed["version_id"],
                created_at=completed["created_at"],
            )
            client.app.state.repository.add_run_events(
                connection, orphan_id, [(None, "run.created", {})]
            )
            reserved = dict(completed)
            reserved.update(
                {
                    "run_id": orphan_id,
                    "status": "running",
                    "result": None,
                    "error": None,
                    "finished_at": None,
                }
            )
            client.app.state.repository.remember_response(
                connection, "run:recovery", "recovery-key", "recovery-digest", reserved
            )
    with TestClient(create_app(settings)) as restarted:
        detail = restarted.get(url + "s/" + orphan_id).json()
        assert detail["status"] == "interrupted"
        assert detail["finished_at"] is not None
        assert [event["kind"] for event in detail["events"]] == [
            "run.created",
            "run.interrupted",
        ]
        with restarted.app.state.repository.transaction() as connection:
            replay = restarted.app.state.repository.idempotent_response(
                connection, "run:recovery", "recovery-key", "recovery-digest"
            )
        assert replay is not None
        assert replay["status"] == "interrupted"
        assert replay["error"]["code"] == "run_interrupted"


def test_runtime_same_key_concurrency_reserves_one_run(tmp_path: Path) -> None:
    source = _source(
        [
            {"id": "start", "component_type": "Start"},
            {"id": "output", "component_type": "Output", "output_name": "name"},
        ],
        [{"from": "start", "port": "next", "to": "output"}],
        {"name": "string"},
    )
    source["outputs"] = {"name": "string"}
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        runtime = client.app.state.runtime
        execute_started = threading.Event()
        release_execute = threading.Event()
        request_barrier = threading.Barrier(3)
        original_execute = runtime._execute

        def delayed_execute(*args: object) -> object:
            execute_started.set()
            assert release_execute.wait(timeout=5)
            return original_execute(*args)  # type: ignore[arg-type]

        runtime._execute = delayed_execute  # type: ignore[method-assign]
        responses: list[dict[str, object]] = []
        errors: list[BaseException] = []
        replay_returned = threading.Event()
        key = new_uuid7()

        def request_run() -> None:
            try:
                request_barrier.wait(timeout=5)
                response = runtime.run(
                    project["project_id"],
                    agent["agent_id"],
                    {"name": "Ada"},
                    key,
                )
                responses.append(response)
                replay_returned.set()
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=request_run) for _ in range(2)]
        for thread in threads:
            thread.start()
        request_barrier.wait(timeout=5)
        assert execute_started.wait(timeout=5)
        assert replay_returned.wait(timeout=5)
        assert len(responses) == 1
        assert responses[0]["status"] == "running"
        assert responses[0]["finished_at"] is None
        release_execute.set()
        for thread in threads:
            thread.join(timeout=5)
        assert not errors
        assert len(responses) == 2
        assert {response["status"] for response in responses} == {
            "running",
            "unverified",
        }
        assert len(client.app.state.repository.runs(agent["agent_id"])) == 1


def test_runtime_rejects_wrong_declared_output_type(tmp_path: Path) -> None:
    source = _source(
        [
            {"id": "start", "component_type": "Start"},
            {
                "id": "transform",
                "component_type": "Transform",
                "mapping": {"result": "{{name}}"},
            },
            {"id": "output", "component_type": "Output", "output_name": "result"},
        ],
        [
            {"from": "start", "port": "next", "to": "transform"},
            {"from": "transform", "port": "next", "to": "output"},
        ],
        {"name": "string"},
    )
    source["outputs"] = {"result": "integer"}
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        response = client.post(
            f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run",
            json={"inputs": {"name": "Ada"}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert response.json()["status"] == "failed"
        assert response.json()["error"]["code"] == "output_invalid"
