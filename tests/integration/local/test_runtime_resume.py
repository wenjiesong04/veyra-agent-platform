from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.wire import RunEvent
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.runtime.service import _RunAbandoned
from veyra_agent_platform.local.runtime.tools import ToolExecution, ToolRuntimeError

from .test_runtime_routes import (
    _await_run,
    _command_until_settled,
    _run_until_settled,
    _write_source,
)


def _project(client: TestClient) -> str:
    source = _write_source(client)
    source["extensions"]["veyra"]["verification"] = {
        "required": True,
        "checks": ["output.not_empty"],
    }
    source["transitions"][2]["to"] = "verify"
    source["nodes"].insert(
        3,
        {"id": "verify", "component_type": "Verifier", "checks": ["output.not_empty"]},
    )
    source["transitions"][-1]["to"] = "verify"
    source["transitions"].extend(
        [
            {"from": "verify", "port": "passed", "to": "output"},
            {"from": "verify", "port": "failed", "to": "output"},
        ]
    )
    source["ui"]["positions"]["verify"] = {"x": 0, "y": 100}
    response = client.post("/api/v1/projects", json={"agents": [source]})
    assert response.status_code == 201, response.text
    project = response.json()
    return (
        f"/api/v1/projects/{project['project_id']}/agents/"
        f"{project['agents'][0]['agent_id']}/run"
    )


def _checkpoint(detail: dict) -> str:
    return [
        event["payload"]["checkpoint_id"]
        for event in detail["events"]
        if event["kind"] == "checkpoint.created"
        and event["payload"]["waiting_kind"] == "execution"
    ][-1]


def _resume(
    client: TestClient,
    url: str,
    detail: dict,
    *,
    key: str | None = None,
    checkpoint: str | None = None,
):
    return client.post(
        f"{url}s/{detail['run_id']}/commands",
        json={"command": "resume", "checkpoint_id": checkpoint or _checkpoint(detail)},
        headers={"Idempotency-Key": key or new_uuid7()},
    )


def _interrupt_at(client: TestClient, monkeypatch: pytest.MonkeyPatch, node: str):
    runtime = client.app.state.runtime
    original = runtime._checkpoint_execution
    interrupted = threading.Event()

    def checkpoint(*args, **kwargs):
        original(*args, **kwargs)
        if args[3] == node:
            interrupted.set()
            raise _RunAbandoned()

    monkeypatch.setattr(runtime, "_checkpoint_execution", checkpoint)
    return interrupted


def test_resume_pins_checkpoint_after_effect_and_verifier_across_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    effects = []

    def write(**kwargs):
        effects.append("write")
        return ToolExecution({"written": True}, {"outcome": "succeeded"})

    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(
        create_app(settings, tool_adapters={"veyra.runtime.filesystem.write": write})
    ) as client:
        url = _project(client)
        interrupted = _interrupt_at(client, monkeypatch, "output")
        waiting = _run_until_settled(
            client, url, {"path": "out.txt", "content": "original"}
        )
        assert (
            client.post(
                f"{url}s/{waiting['run_id']}/commands",
                json={"command": "approve"},
                headers={"Idempotency-Key": new_uuid7()},
            ).status_code
            == 200
        )
        assert interrupted.wait(5)
    with TestClient(
        create_app(settings, tool_adapters={"veyra.runtime.filesystem.write": write})
    ) as restarted:
        original = restarted.get(f"{url}s/{waiting['run_id']}").json()
        assert original["status"] == "interrupted"
        draft_url = url.removesuffix("/run") + "/draft"
        draft = restarted.get(draft_url).json()
        draft["source"]["nodes"][1]["prompt"] = "New Draft must not be used"
        assert (
            restarted.patch(
                draft_url,
                json={
                    "source": draft["source"],
                    "expected_revision": draft["revision"],
                },
                headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
            ).status_code
            == 200
        )
        key = new_uuid7()
        response = _resume(restarted, url, original, key=key)
        assert response.status_code == 200, response.text
        child = _await_run(restarted, url, response.json()["run_id"])
        assert child["status"] == "verified"
        assert child["result"] == {"written": True}
        assert child["version_id"] == original["version_id"]
        assert child["run_id"] != original["run_id"]
        assert effects == ["write"]
        assert [
            event["node_id"]
            for event in child["events"]
            if event["kind"] == "node.started"
        ] == ["output"]
        created = child["events"][0]["payload"]
        assert created["resume_of_run_id"] == original["run_id"]
        assert created["checkpoint_id"] == _checkpoint(original)
        assert created["inputs"] == {"path": "out.txt", "content": "original"}
        assert (
            created["recovery_identity"]["permissions"]
            == draft["source"]["extensions"]["veyra"]["permissions"]
        )
        repository = restarted.app.state.runtime.repository
        assert repository.run_inputs(child["run_id"]) == created["inputs"]
        with repository.transaction() as connection:
            command = connection.execute(
                "SELECT * FROM runtime_run_commands WHERE command_id = ?",
                (created["resume_command_id"],),
            ).fetchone()
            assert json.loads(command["payload_json"]) == {
                "checkpoint_id": _checkpoint(original),
                "resume_run_id": child["run_id"],
            }
            assert command["run_id"] == original["run_id"]
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM runtime_tool_calls WHERE run_id = ?",
                    (original["run_id"],),
                ).fetchone()[0]
                == 1
            )
        assert restarted.get(f"{url}s/{original['run_id']}").json() == original
        assert (
            _resume(restarted, url, original, key=key).json()["run_id"]
            == child["run_id"]
        )
        assert _resume(restarted, url, original).json()["run_id"] == child["run_id"]
        assert len(restarted.get(f"{url}s").json()["runs"]) == 2
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(f"{url}s/{child['run_id']}").json() == child
        assert (
            _resume(restarted, url, original, key=key).json()["run_id"]
            == child["run_id"]
        )
        frames = (
            restarted.get(f"{url}s/{child['run_id']}/events").text.strip().split("\n\n")
        )
        events = [
            json.loads(line[6:])
            for frame in frames
            if frame.startswith("id: ")
            for line in frame.splitlines()
            if line.startswith("data: ")
        ]
        assert events == child["events"]
        assert all(RunEvent.from_dict(event) for event in events)


@pytest.mark.parametrize(
    "case", ["dispatch", "approval", "cancelled", "stale", "profile", "lock", "missing"]
)
def test_resume_rejects_unrecoverable_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    def write(**kwargs):
        raise ToolRuntimeError("tool_timeout", "Unknown effect")

    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(
        create_app(settings, tool_adapters={"veyra.runtime.filesystem.write": write})
    ) as client:
        url = _project(client)
        interrupted = (
            _interrupt_at(client, monkeypatch, "write")
            if case in {"stale", "profile", "lock", "missing"}
            else None
        )
        waiting = _run_until_settled(client, url, {"path": "out.txt", "content": "one"})
        if case == "cancelled":
            _command_until_settled(client, url, waiting["run_id"], "stop")
        elif case != "approval":
            response = client.post(
                f"{url}s/{waiting['run_id']}/commands",
                json={"command": "approve"},
                headers={"Idempotency-Key": new_uuid7()},
            )
            assert response.status_code == 200
            if interrupted:
                assert interrupted.wait(5)
                client.app.state.runtime.repository.interrupt_orphan_runs()
            else:
                assert _await_run(client, url, waiting["run_id"])["status"] == "failed"
        detail = client.get(f"{url}s/{waiting['run_id']}").json()
        selected = _checkpoint(detail)
        if case == "stale":
            selected = detail["events"][2]["payload"]["checkpoint_id"]
        elif case == "profile":
            client.app.state.runtime.model.settings = (
                client.app.state.runtime.model.settings.model_copy(
                    update={"model_id": "changed-model"}
                )
            )
        elif case == "lock":
            catalog = client.app.state.runtime.tools.catalog
            original = catalog.by_reference
            monkeypatch.setattr(
                catalog,
                "by_reference",
                lambda reference: {**original(reference), "content_hash": "0" * 64},
            )
        elif case == "missing":
            selected = new_uuid7()
        response = _resume(client, url, detail, checkpoint=selected)
        assert response.status_code == 422, response.text
        expected = {
            "dispatch": "resume_effect_unsafe",
            "approval": "command_not_applicable",
            "cancelled": "command_not_applicable",
            "stale": "resume_checkpoint_invalid",
            "profile": "resume_identity_changed",
            "lock": "resume_dependencies_unavailable",
            "missing": "resume_checkpoint_invalid",
        }
        assert response.json()["code"] == expected[case]
        assert client.get(f"{url}s/{waiting['run_id']}").json() == detail
        assert len(client.get(f"{url}s").json()["runs"]) == 1


def test_resume_concurrency_and_stop_before_child_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    effects = []

    def write(**kwargs):
        effects.append("write")
        return ToolExecution({"written": True}, {"outcome": "succeeded"})

    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(
        create_app(settings, tool_adapters={"veyra.runtime.filesystem.write": write})
    ) as client:
        url = _project(client)
        interrupted = _interrupt_at(client, monkeypatch, "write")
        waiting = _run_until_settled(client, url, {"path": "out.txt", "content": "one"})
        client.post(
            f"{url}s/{waiting['run_id']}/commands",
            json={"command": "approve"},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert interrupted.wait(5)
    with TestClient(
        create_app(settings, tool_adapters={"veyra.runtime.filesystem.write": write})
    ) as restarted:
        detail = restarted.get(f"{url}s/{waiting['run_id']}").json()
        workers = []
        monkeypatch.setattr(
            restarted.app.state.runtime,
            "_schedule_execution",
            lambda run_id, worker: workers.append(worker),
        )
        key = new_uuid7()
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(
                pool.map(
                    lambda command_key: _resume(
                        restarted, url, detail, key=command_key
                    ),
                    [key, key, new_uuid7(), new_uuid7()],
                )
            )
        assert all(response.status_code == 200 for response in responses)
        assert len({response.json()["run_id"] for response in responses}) == 1
        assert len(workers) == 1
        child_id = responses[0].json()["run_id"]
        _command_until_settled(restarted, url, child_id, "stop")
        stopped = restarted.get(f"{url}s/{child_id}").json()
        workers[0]()
        assert restarted.get(f"{url}s/{child_id}").json() == stopped
        assert effects == []
        assert _resume(restarted, url, detail).json()["run_id"] == child_id
        assert len(restarted.get(f"{url}s").json()["runs"]) == 2


def test_resume_child_survives_schedule_loss_and_retry_cannot_replay_ancestor_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    effects = []

    def write(**kwargs):
        effects.append("write")
        return ToolExecution({"written": True}, {"outcome": "succeeded"})

    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(
        create_app(settings, tool_adapters={"veyra.runtime.filesystem.write": write})
    ) as client:
        url = _project(client)
        interrupted = _interrupt_at(client, monkeypatch, "output")
        waiting = _run_until_settled(client, url, {"path": "out.txt", "content": "one"})
        client.post(
            f"{url}s/{waiting['run_id']}/commands",
            json={"command": "approve"},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert interrupted.wait(5)
    with TestClient(create_app(settings)) as client:
        detail = client.get(f"{url}s/{waiting['run_id']}").json()
        monkeypatch.setattr(
            client.app.state.runtime, "_schedule_execution", lambda *args: None
        )
        child = _resume(client, url, detail)
        assert child.status_code == 200, child.text
        child_id = child.json()["run_id"]
    with TestClient(create_app(settings)) as client:
        child = client.get(f"{url}s/{child_id}").json()
        assert child["status"] == "interrupted"
        retry = client.post(
            f"{url}s/{child_id}/commands",
            json={"command": "retry"},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert retry.status_code == 422
        assert retry.json()["code"] == "retry_effect_unsafe"
        resumed = _resume(client, url, child)
        assert resumed.status_code == 200, resumed.text
        result = _await_run(client, url, resumed.json()["run_id"])
        assert result["status"] == "verified"
        assert result["result"] == {"written": True}
        assert effects == ["write"]
        assert client.get(f"{url}s/{child_id}").json() == child


@pytest.mark.parametrize("fault_point", ["insert_run_command", "remember_response"])
def test_stop_wins_before_resume_and_resume_transaction_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault_point: str,
) -> None:
    def evidence(connection):
        return {
            table: [
                tuple(row)
                for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
            ]
            for table in (
                "runtime_runs",
                "runtime_run_events",
                "runtime_run_commands",
                "runtime_checkpoints",
                "runtime_tool_calls",
                "runtime_approval_requests",
                "idempotency_records",
            )
        }

    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        url = _project(client)
        interrupted = _interrupt_at(client, monkeypatch, "write")
        waiting = _run_until_settled(client, url, {"path": "out.txt", "content": "one"})
        client.post(
            f"{url}s/{waiting['run_id']}/commands",
            json={"command": "approve"},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert interrupted.wait(5)
        runtime = client.app.state.runtime
        detail = client.get(f"{url}s/{waiting['run_id']}").json()
        original = runtime._resume_run
        entered, release = threading.Event(), threading.Event()

        def delayed(*args, **kwargs):
            entered.set()
            assert release.wait(5)
            return original(*args, **kwargs)

        monkeypatch.setattr(runtime, "_resume_run", delayed)
        key = new_uuid7()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(_resume, client, url, detail, key=key)
            try:
                assert entered.wait(5)
                _command_until_settled(client, url, waiting["run_id"], "stop")
                stopped = client.get(f"{url}s/{waiting['run_id']}").json()
                with runtime.repository.transaction() as connection:
                    baseline = evidence(connection)
            finally:
                release.set()
            response = pending.result()
            assert response.status_code == 422
            assert response.json()["code"] == "command_not_applicable"
        assert _resume(client, url, detail, key=key).status_code == 422
        with runtime.repository.transaction() as connection:
            assert evidence(connection) == baseline
        assert client.get(f"{url}s/{waiting['run_id']}").json() == stopped
        assert len(client.get(f"{url}s").json()["runs"]) == 1
    with TestClient(
        create_app(
            settings,
            tool_adapters={
                "veyra.runtime.filesystem.write": lambda **kwargs: ToolExecution(
                    {"written": True}, {"outcome": "succeeded"}
                )
            },
        )
    ) as client:
        url = _project(client)
        checkpoint_execution = client.app.state.runtime._checkpoint_execution
        interrupted = _interrupt_at(client, monkeypatch, "write")
        waiting = _run_until_settled(client, url, {"path": "out.txt", "content": "two"})
        client.post(
            f"{url}s/{waiting['run_id']}/commands",
            json={"command": "approve"},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert interrupted.wait(5)
        runtime = client.app.state.runtime
        runtime.repository.interrupt_orphan_runs()
        detail = client.get(f"{url}s/{waiting['run_id']}").json()
        assert detail["status"] == "interrupted"
        monkeypatch.setattr(runtime, "_checkpoint_execution", checkpoint_execution)
        with runtime.repository.transaction() as connection:
            baseline = evidence(connection)
        key = new_uuid7()
        injected = []
        workers = []
        monkeypatch.setattr(
            runtime,
            "_schedule_execution",
            lambda run_id, worker: workers.append(worker),
        )
        original_write = getattr(runtime.repository, fault_point)

        def fail(connection, *args, **kwargs):
            original_write(connection, *args, **kwargs)
            partial = evidence(connection)
            assert len(partial["runtime_runs"]) == len(baseline["runtime_runs"]) + 1
            assert (
                len(partial["runtime_run_commands"])
                == len(baseline["runtime_run_commands"]) + 1
            )
            if fault_point == "remember_response":
                assert (
                    len(partial["runtime_run_events"])
                    == len(baseline["runtime_run_events"]) + 3
                )
                assert (
                    len(partial["runtime_checkpoints"])
                    == len(baseline["runtime_checkpoints"]) + 1
                )
                assert (
                    len(partial["idempotency_records"])
                    == len(baseline["idempotency_records"]) + 1
                )
            injected.append(fault_point)
            raise ValueError("transaction fault")

        monkeypatch.setattr(runtime.repository, fault_point, fail)
        with pytest.raises(ValueError, match="transaction fault"):
            runtime.command(
                detail["project_id"],
                detail["agent_id"],
                detail["run_id"],
                "resume",
                key,
                checkpoint_id=_checkpoint(detail),
            )
        with runtime.repository.transaction() as connection:
            assert evidence(connection) == baseline
        response = _resume(client, url, detail, key=key)
        assert response.status_code == 500
        assert response.json()["code"] == "local_internal_error"
        assert response.json()["message"] == "transaction fault"
        assert injected == [fault_point, fault_point]
        assert workers == []
        with runtime.repository.transaction() as connection:
            assert evidence(connection) == baseline
        assert len(client.get(f"{url}s").json()["runs"]) == 1
        assert client.get(f"{url}s/{waiting['run_id']}").json() == detail

        monkeypatch.setattr(runtime.repository, fault_point, original_write)
        response = _resume(client, url, detail, key=key)
        assert response.status_code == 200, response.text
        child_id = response.json()["run_id"]
        assert child_id != detail["run_id"]
        assert _resume(client, url, detail, key=key).json() == response.json()
        assert len(workers) == 1
        workers[0]()
        child = client.get(f"{url}s/{child_id}").json()
        assert child["status"] == "verified"
        assert child["events"][0]["payload"]["resume_of_run_id"] == detail["run_id"]
        assert _resume(client, url, detail, key=key).json()["run_id"] == child_id
        assert len(client.get(f"{url}s").json()["runs"]) == 2
        assert client.get(f"{url}s/{waiting['run_id']}").json() == detail
