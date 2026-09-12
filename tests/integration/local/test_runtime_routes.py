from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.wire import RunEvent
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.client import RuntimeCompletion

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def isolate_runtime_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("VEYRA_RUNTIME_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("VEYRA_RUNTIME_MODEL_ID", raising=False)


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


def _await_run(
    client: TestClient, run_url: str, run_id: str, *, timeout: float = 8
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    detail: dict[str, object] = {}
    while time.monotonic() < deadline:
        detail = client.get(f"{run_url}s/{run_id}").json()
        if detail["status"] != "running":
            return detail
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} stayed running: {detail}")


def _run_until_settled(
    client: TestClient,
    url: str,
    inputs: dict[str, object],
    *,
    key: str | None = None,
) -> dict[str, object]:
    started = client.post(
        url,
        json={"inputs": inputs},
        headers={"Idempotency-Key": key or new_uuid7()},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "running"
    return _await_run(client, url, started.json()["run_id"])


def _command_until_settled(
    client: TestClient, run_url: str, run_id: str, command: str
) -> dict[str, object]:
    started = client.post(
        f"{run_url}s/{run_id}/commands",
        json={"command": command},
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert started.status_code == 200
    payload = started.json()
    if payload["status"] == "running":
        return _await_run(client, run_url, str(payload["run_id"]))
    return payload


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
        assert {
            item["type"]
            for item in client.get("/api/v1/components").json()["components"]
        } == {
            "Start",
            "Agent",
            "Model",
            "AgentCall",
            "Tool",
            "Condition",
            "Transform",
            "HumanApproval",
            "Verifier",
            "Output",
        }
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        key = new_uuid7()
        first = client.post(
            url, json={"inputs": {"name": "Ada"}}, headers={"Idempotency-Key": key}
        )
        assert first.status_code == 200
        assert first.json()["status"] == "running"
        settled = _await_run(client, url, first.json()["run_id"])
        assert settled["status"] == "unverified"
        assert settled["result"] == {"result": "Hello Ada"}
        replay = client.post(
            url, json={"inputs": {"name": "Ada"}}, headers={"Idempotency-Key": key}
        )
        assert replay.json()["run_id"] == first.json()["run_id"]
        assert replay.json()["status"] == "unverified"
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
        response = _run_until_settled(client, url, {"flag": True})
        assert response["status"] == "verified"
        assert response["result"] == {"result": "ok"}


def test_runtime_rejects_unregistered_tool(tmp_path: Path) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    source = _source(
        [
            {"id": "start", "component_type": "Start"},
            {
                "id": "blocked",
                "component_type": "Tool",
                "uses": "demo.tool@1.0.0",
            },
            {"id": "output", "component_type": "Output", "output_name": "result"},
        ],
        [
            {"from": "start", "port": "next", "to": "blocked"},
            {"from": "blocked", "port": "next", "to": "output"},
        ],
        {"issue": "string"},
    )
    source["extensions"]["veyra"]["permissions"]["tools"] = ["demo.tool"]
    source["lock"]["demo.tool@1.0.0"] = "b" * 64
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        response = _run_until_settled(client, url, {"issue": "one"})
        assert response["status"] == "failed"
        assert response["error"]["code"] == "tool_not_registered"
        detail = client.get(f"{url}s/{response['run_id']}").json()
        requested = next(
            event for event in detail["events"] if event["kind"] == "tool.requested"
        )
        assert requested["payload"]["permission"] == "denied"
        assert [event["kind"] for event in detail["events"]][-2:] == [
            "node.failed",
            "run.failed",
        ]
        assert all(RunEvent.from_dict(event) for event in detail["events"])


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
        failed = _run_until_settled(client, url, {"flag": "yes"})
        assert failed["status"] == "failed"
        assert failed["error"]["code"] == "condition_invalid"
        detail = client.get(url + "s/" + failed["run_id"]).json()
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
        completed = _run_until_settled(client, url, {"name": "Ada"})
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
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        runtime = client.app.state.runtime
        execute_started = threading.Event()
        release_execute = threading.Event()
        request_barrier = threading.Barrier(3)
        original_execute = runtime._execute

        def delayed_execute(*args: object, **kwargs: object) -> object:
            execute_started.set()
            assert release_execute.wait(timeout=5)
            return original_execute(*args, **kwargs)

        runtime._execute = delayed_execute  # type: ignore[method-assign]
        responses: list[dict[str, object]] = []
        errors: list[BaseException] = []
        key = new_uuid7()

        def request_run() -> None:
            try:
                request_barrier.wait(timeout=5)
                responses.append(
                    runtime.run(
                        project["project_id"],
                        agent["agent_id"],
                        {"name": "Ada"},
                        key,
                    )
                )
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=request_run) for _ in range(2)]
        for thread in threads:
            thread.start()
        request_barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=5)
        assert not errors
        assert execute_started.wait(timeout=5)
        assert len(responses) == 2
        assert {item["run_id"] for item in responses} == {responses[0]["run_id"]}
        assert {item["status"] for item in responses} == {"running"}
        release_execute.set()
        settled = _await_run(client, url, str(responses[0]["run_id"]))
        assert settled["status"] == "unverified"
        assert len(client.app.state.repository.runs(agent["agent_id"])) == 1


def test_runtime_http_returns_running_before_execute_finishes(
    tmp_path: Path,
) -> None:
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
        runtime = client.app.state.runtime
        execute_started = threading.Event()
        release_execute = threading.Event()
        original_execute = runtime._execute

        def delayed_execute(*args: object, **kwargs: object) -> object:
            execute_started.set()
            assert release_execute.wait(timeout=5)
            return original_execute(*args, **kwargs)

        runtime._execute = delayed_execute  # type: ignore[method-assign]
        started_at = time.monotonic()
        response = client.post(
            url,
            json={"inputs": {"name": "Ada"}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert time.monotonic() - started_at < 1
        assert response.status_code == 200
        assert response.json()["status"] == "running"
        assert execute_started.wait(timeout=5)
        assert (
            client.get(url + "s/" + response.json()["run_id"]).json()["status"]
            == "running"
        )
        release_execute.set()
        settled = _await_run(client, url, response.json()["run_id"])
        assert settled["status"] == "unverified"
        assert settled["result"] == {"name": "Ada"}


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
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        response = _run_until_settled(client, url, {"name": "Ada"})
        assert response["status"] == "failed"
        assert response["error"]["code"] == "output_invalid"


class ScriptedRuntimeTransport:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[object] = []

    def models(self) -> tuple[str, ...]:
        return ("kimi-k3",)

    def complete(self, messages: object) -> RuntimeCompletion:
        self.calls.append(messages)
        return RuntimeCompletion(content=self.content, finish_reason="stop")


def _agent_source() -> dict[str, object]:
    source = _source(
        [
            {"id": "start", "component_type": "Start"},
            {
                "id": "agent",
                "component_type": "Agent",
                "model_ref": "model.primary",
                "system_prompt": "Reply with one short sentence.",
            },
            {"id": "output", "component_type": "Output", "output_name": "result"},
        ],
        [
            {"from": "start", "port": "next", "to": "agent"},
            {"from": "agent", "port": "next", "to": "output"},
        ],
        {"request": "string"},
    )
    source["outputs"] = {"result": "string"}
    return source


def test_runtime_status_is_unconfigured_without_host_key(tmp_path: Path) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        status = client.get("/api/v1/runtime/status")
        assert status.status_code == 200
        payload = status.json()
        assert payload["configured"] is False
        assert payload["model_id"] == "kimi-k3"
        assert payload["user_provided_only"] is False
        assert payload["allow_process_environment_key"] is True


def test_agent_node_requires_runtime_key(tmp_path: Path) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post(
            "/api/v1/projects", json={"agents": [_agent_source()]}
        ).json()
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        response = _run_until_settled(client, url, {"request": "Summarize this"})
        assert response["status"] == "failed"
        assert response["error"]["code"] == "runtime_not_configured"


def test_agent_node_uses_injected_runtime_model(tmp_path: Path) -> None:
    transport = ScriptedRuntimeTransport("The sky is clear.")
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings, runtime_transport=transport)) as client:
        status = client.get("/api/v1/runtime/status").json()
        assert status["configured"] is True
        project = client.post(
            "/api/v1/projects", json={"agents": [_agent_source()]}
        ).json()
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        response = _run_until_settled(client, url, {"request": "What is the weather?"})
        assert response["status"] == "unverified"
        assert response["result"] == {"result": "The sky is clear."}
        assert transport.calls
        assert response["error"] is None


def test_skill_context_is_locked_injected_and_receipted(
    tmp_path: Path,
) -> None:
    transport = ScriptedRuntimeTransport("Skill-aware response")
    source = _agent_source()
    skill = ResourceCatalog().detail("veyra.skill.research-brief", "1.0.0")
    reference = skill["reference"]
    source["extensions"]["veyra"]["skill_refs"] = [reference]
    source["lock"][reference] = skill["content_hash"]
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings, runtime_transport=transport)) as client:
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        result = _run_until_settled(client, url, {"request": "Make a brief"})
        assert result["status"] == "unverified"
        assert "Research Brief" in json.dumps(transport.calls)
        events = client.get(f"{url}s/{result['run_id']}").json()["events"]
        completed = next(
            event
            for event in events
            if event["kind"] == "tool.completed"
            and event["payload"].get("tool_reference") == "skill.context"
        )
        receipt = completed["payload"]["receipts"][0]
        assert receipt["content_hash"] == skill["content_hash"]
        assert receipt["verified"] is True
        assert "Produce a reviewable plan" not in json.dumps(completed)


def test_runtime_profile_validation_and_agent_readiness_use_effective_model(
    tmp_path: Path,
) -> None:
    transport = ScriptedRuntimeTransport("unused")
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    profile = {
        "provider": "openai_compatible",
        "base_url": "https://api.moonshot.cn/v1",
        "model_id": "kimi-k3",
        "api_key_env": "MOONSHOT_API_KEY",
    }
    with TestClient(create_app(settings, runtime_transport=transport)) as client:
        validated = client.post(
            "/api/v1/runtime/profile/validate", json={"profile": profile}
        )
        assert validated.status_code == 200
        assert validated.json()["valid"] is True
        assert validated.json()["model_available"] is True

        unavailable = client.post(
            "/api/v1/runtime/profile/validate",
            json={"profile": {**profile, "model_id": "missing-model"}},
        )
        assert unavailable.status_code == 200
        assert unavailable.json()["valid"] is False
        assert unavailable.json()["code"] == "runtime_model_unavailable"

        project = client.post(
            "/api/v1/projects", json={"agents": [_agent_source()]}
        ).json()
        agent = project["agents"][0]
        readiness = client.get(
            f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/runtime-readiness"
        )
        assert readiness.status_code == 200
        assert readiness.json()["ready"] is True
        assert readiness.json()["model"]["configured"] is True
        assert readiness.json()["profile_source"] == "default"
        assert transport.calls == []


def test_agent_node_accepts_declared_object_output(tmp_path: Path) -> None:
    transport = ScriptedRuntimeTransport(json.dumps({"summary": "ok"}))
    source = _agent_source()
    source["outputs"] = {"result": "object"}
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings, runtime_transport=transport)) as client:
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        response = _run_until_settled(client, url, {"request": "Summarize"})
        assert response["status"] == "unverified"
        assert response["result"] == {"result": {"summary": "ok"}}


def test_production_mode_does_not_use_host_process_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-not-for-production-agents")
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
        mode="production",
        build_sha="test-build",
    )
    with TestClient(create_app(settings)) as client:
        status = client.get("/api/v1/runtime/status").json()
        assert status["configured"] is False
        assert status["user_provided_only"] is True
        project = client.post(
            "/api/v1/projects", json={"agents": [_agent_source()]}
        ).json()
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        response = _run_until_settled(client, url, {"request": "Hello"})
        assert response["error"]["code"] == "runtime_not_configured"


def test_catalogued_filesystem_read_tool_runs_inside_project_and_records_receipt(
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
            {"id": "output", "component_type": "Output", "output_name": "content"},
        ],
        [
            {"from": "start", "port": "next", "to": "read"},
            {"from": "read", "port": "next", "to": "output"},
        ],
        {"path": "string"},
    )
    source["outputs"] = {"content": "string"}
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
        response = _run_until_settled(client, url, {"path": "resources/note.txt"})
        assert response["status"] == "unverified"
        assert response["result"] == {"content": "hello from the Project"}
        detail = client.get(url + "s/" + response["run_id"]).json()
        assert [
            event["kind"]
            for event in detail["events"]
            if event["kind"].startswith("tool.")
        ] == [
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


def test_filesystem_read_tool_rejects_project_escape(tmp_path: Path) -> None:
    source = _source(
        [
            {"id": "start", "component_type": "Start"},
            {
                "id": "read",
                "component_type": "Tool",
                "uses": "veyra.tool.filesystem.read@1.0.0",
            },
            {"id": "output", "component_type": "Output", "output_name": "content"},
        ],
        [
            {"from": "start", "port": "next", "to": "read"},
            {"from": "read", "port": "next", "to": "output"},
        ],
        {"path": "string"},
    )
    source["outputs"] = {"content": "string"}
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
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        response = _run_until_settled(client, url, {"path": "../outside.txt"})
        assert response["status"] == "failed"
        assert response["error"]["code"] == "tool_path_denied"


def _write_source(client: TestClient) -> dict[str, object]:
    source = _source(
        [
            {"id": "start", "component_type": "Start"},
            {
                "id": "approve",
                "component_type": "HumanApproval",
                "prompt": "Write {{path}}?",
            },
            {
                "id": "write",
                "component_type": "Tool",
                "uses": "veyra.tool.filesystem.write@1.0.0",
            },
            {"id": "output", "component_type": "Output", "output_name": "written"},
        ],
        [
            {"from": "start", "port": "next", "to": "approve"},
            {"from": "approve", "port": "approved", "to": "write"},
            {"from": "approve", "port": "rejected", "to": "output"},
            {"from": "write", "port": "next", "to": "output"},
        ],
        {"path": "string", "content": "string"},
    )
    source["outputs"] = {"written": "boolean"}
    source["extensions"]["veyra"]["permissions"] = {
        "network_hosts": [],
        "tools": ["veyra.tool.filesystem.write"],
        "filesystem_read_roots": [],
        "filesystem_write_roots": ["project"],
        "shell_workspace_only": False,
    }
    write_hash = client.app.state.resource_catalog.detail(
        "veyra.tool.filesystem.write", "1.0.0"
    )["content_hash"]
    source["lock"]["veyra.tool.filesystem.write@1.0.0"] = write_hash
    return source


def test_filesystem_write_pauses_for_approval_then_writes(
    tmp_path: Path,
) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        source = _write_source(client)
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        run_url = (
            f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        )
        waiting = _run_until_settled(
            client,
            run_url,
            {"path": "resources/out.txt", "content": "saved"},
        )
        assert waiting["status"] == "waiting"
        assert waiting["result"] is None
        assert not Path(project["root_path"], "resources", "out.txt").exists()
        detail = client.get(f"{run_url}s/{waiting['run_id']}").json()
        kinds = [event["kind"] for event in detail["events"]]
        assert "approval.requested" in kinds
        assert "checkpoint.created" in kinds
        completed = _command_until_settled(
            client, run_url, str(waiting["run_id"]), "approve"
        )
        assert completed["status"] == "unverified"
        assert completed["result"] == {"written": True}
        assert (
            Path(project["root_path"], "resources", "out.txt").read_text(
                encoding="utf-8"
            )
            == "saved"
        )
        events = client.get(f"{run_url}s/{waiting['run_id']}").json()["events"]
        tool_kinds = [
            event["kind"] for event in events if event["kind"].startswith("tool.")
        ]
        assert tool_kinds == ["tool.requested", "tool.started", "tool.completed"]
        requested = next(event for event in events if event["kind"] == "tool.requested")
        assert requested["payload"]["permission"] == "allowed"


def test_filesystem_write_stop_and_reject_do_not_write(tmp_path: Path) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        source = _write_source(client)
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        run_url = (
            f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        )
        waiting = _run_until_settled(
            client,
            run_url,
            {"path": "resources/out.txt", "content": "saved"},
        )
        resume = client.post(
            f"{run_url}s/{waiting['run_id']}/commands",
            json={"command": "resume"},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert resume.status_code == 422
        assert resume.json()["code"] == "command_not_applicable"
        stopped = _command_until_settled(
            client, run_url, str(waiting["run_id"]), "stop"
        )
        assert stopped["status"] == "cancelled"
        assert not Path(project["root_path"], "resources", "out.txt").exists()
        retried = _command_until_settled(
            client, run_url, str(waiting["run_id"]), "retry"
        )
        assert retried["status"] == "waiting"
        assert retried["run_id"] != waiting["run_id"]

        waiting = _run_until_settled(
            client,
            run_url,
            {"path": "resources/out.txt", "content": "saved"},
        )
        rejected = _command_until_settled(
            client, run_url, str(waiting["run_id"]), "reject"
        )
        assert rejected["status"] == "unverified"
        assert rejected["result"] == {"written": False}
        assert not Path(project["root_path"], "resources", "out.txt").exists()


def test_filesystem_write_without_approval_is_denied(tmp_path: Path) -> None:
    source = _source(
        [
            {"id": "start", "component_type": "Start"},
            {
                "id": "write",
                "component_type": "Tool",
                "uses": "veyra.tool.filesystem.write@1.0.0",
            },
            {"id": "output", "component_type": "Output", "output_name": "written"},
        ],
        [
            {"from": "start", "port": "next", "to": "write"},
            {"from": "write", "port": "next", "to": "output"},
        ],
        {"path": "string", "content": "string"},
    )
    source["outputs"] = {"written": "boolean"}
    source["extensions"]["veyra"]["permissions"] = {
        "network_hosts": [],
        "tools": ["veyra.tool.filesystem.write"],
        "filesystem_read_roots": [],
        "filesystem_write_roots": ["project"],
        "shell_workspace_only": False,
    }
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        source["lock"]["veyra.tool.filesystem.write@1.0.0"] = (
            client.app.state.resource_catalog.detail(
                "veyra.tool.filesystem.write", "1.0.0"
            )["content_hash"]
        )
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        response = _run_until_settled(
            client,
            url,
            {"path": "resources/out.txt", "content": "saved"},
        )
        assert response["status"] == "failed"
        assert response["error"]["code"] == "approval_required"
        assert not Path(project["root_path"], "resources", "out.txt").exists()


def test_runtime_event_stream_replays_a_completed_run(tmp_path: Path) -> None:
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
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        run_url = (
            f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        )
        started = _run_until_settled(client, run_url, {"name": "Ada"})
        stream = client.get(f"{run_url}s/{started['run_id']}/events")
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        assert "event: runtime" in stream.text
        assert '"kind":"run.created"' in stream.text
        assert '"kind":"run.completed"' in stream.text
        assert "event: done" in stream.text
        assert '"status":"unverified"' in stream.text


def test_runtime_event_stream_follows_approval_then_completes(
    tmp_path: Path,
) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        source = _write_source(client)
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        agent = project["agents"][0]
        run_url = (
            f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        )
        waiting = _run_until_settled(
            client,
            run_url,
            {"path": "resources/out.txt", "content": "saved"},
        )
        assert waiting["status"] == "waiting"
        frames: list[str] = []
        runtime = client.app.state.runtime

        def consume() -> None:
            for frame in runtime.follow_events(waiting["run_id"], 0):
                frames.append(frame)
                if "event: done" in frame:
                    break

        watcher = threading.Thread(target=consume, daemon=True)
        watcher.start()
        time.sleep(0.1)
        completed = _command_until_settled(
            client, run_url, str(waiting["run_id"]), "approve"
        )
        assert completed["status"] == "unverified"
        watcher.join(timeout=5)
        assert watcher.is_alive() is False
        body = "".join(frames)
        assert "approval.requested" in body
        assert "tool.completed" in body
        assert "event: done" in body


def test_knowledge_binding_sends_locked_context_and_rejects_changed_document(
    tmp_path: Path,
) -> None:
    transport = ScriptedRuntimeTransport("A recyclable box.")
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings, runtime_transport=transport)) as client:
        project = client.post(
            "/api/v1/projects", json={"agents": [_agent_source()]}
        ).json()
        p, a = project["project_id"], project["agents"][0]["agent_id"]
        knowledge = client.post(
            f"/api/v1/projects/{p}/knowledge",
            json={
                "name": "Brand",
                "text": "BRAND_REFERENCE_742: Use recyclable paper.",
            },
        ).json()
        ref = f"{knowledge['knowledge_id']}@{knowledge['version']}"
        url = f"/api/v1/projects/{p}/agents/{a}"
        draft = client.get(f"{url}/draft").json()
        draft["source"]["extensions"]["veyra"]["knowledge_refs"] = [ref]
        draft["source"]["lock"][ref] = knowledge["source_file_hash"]
        saved = client.patch(
            f"{url}/draft",
            json={"source": draft["source"], "expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert saved.status_code == 200, saved.text
        result = _run_until_settled(
            client, f"{url}/run", {"request": "Design packaging"}
        )
        assert result["status"] == "unverified", result
        assert "BRAND_REFERENCE_742" in json.dumps(transport.calls)
        events = client.get(f"{url}/runs/{result['run_id']}").json()["events"]
        assert "BRAND_REFERENCE_742" not in json.dumps(events)
        assert any(
            event["payload"].get("tool_reference") == "knowledge.context"
            for event in events
        )
        changed = client.patch(
            f"/api/v1/projects/{p}/knowledge/{knowledge['knowledge_id']}",
            json={"text": "Different content"},
        )
        assert changed.status_code == 200, changed.text
        call_count = len(transport.calls)
        failed = _run_until_settled(client, f"{url}/run", {"request": "Design again"})
        assert failed["status"] == "failed", failed
        assert failed["error"]["code"] == "knowledge_lock_mismatch"
        assert len(transport.calls) == call_count
