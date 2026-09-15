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
from veyra_agent_platform.local.runtime.tools import ToolExecution, ToolRuntimeError

from .test_runtime_routes import (
    _await_run,
    _command_until_settled,
    _run_until_settled,
    _write_source,
)


@pytest.mark.parametrize("ending", ["failed", "completed", "cancelled", "interrupted"])
def test_retry_blocks_dispatched_tool_even_without_receipt(
    tmp_path: Path,
    ending: str,
) -> None:
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    effects: list[str] = []

    def fake_write(**kwargs: object) -> ToolExecution:
        effects.append("write")
        (tmp_path / "external-effect.txt").write_text(str(len(effects)))
        entered.set()
        try:
            if ending in {"cancelled", "interrupted"}:
                assert release.wait(10)
            if ending != "completed":
                raise ToolRuntimeError("tool_timeout", "Effect outcome is unknown")
            return ToolExecution({}, {"outcome": "succeeded"})
        finally:
            returned.set()

    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(
        create_app(
            settings,
            tool_adapters={"veyra.runtime.filesystem.write": fake_write},
        )
    ) as client:
        source = _write_source(client)
        # The completed fake omits the output: execution fails after the effect receipt.
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        url = (
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{project['agents'][0]['agent_id']}/run"
        )
        waiting = _run_until_settled(client, url, {"path": "out.txt", "content": "one"})
        run_id = waiting["run_id"]
        try:
            approved = client.post(
                f"{url}s/{run_id}/commands",
                json={"command": "approve"},
                headers={"Idempotency-Key": new_uuid7()},
            )
            assert approved.status_code == 200
            assert entered.wait(5)
            if ending == "cancelled":
                _command_until_settled(client, url, run_id, "stop")
            elif ending == "interrupted":
                # A new application over the same temporary SQLite recovers the orphan.
                with TestClient(create_app(settings)) as restarted:
                    assert (
                        restarted.get(f"{url}s/{run_id}").json()["status"]
                        == "interrupted"
                    )
            else:
                assert _await_run(client, url, run_id)["status"] == "failed"
            before = client.get(f"{url}s/{run_id}").json()
            assert any(e["kind"] == "tool.started" for e in before["events"])
            repository = client.app.state.runtime.repository
            with repository.transaction() as connection:
                original_receipts = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM runtime_tool_calls WHERE run_id = ?",
                        (run_id,),
                    ).fetchall()
                ]
            if ending == "completed":
                assert json.loads(original_receipts[0]["receipt_json"]) == {
                    "outcome": "succeeded"
                }
            if ending in {"cancelled", "interrupted"}:
                with client.app.state.runtime.repository.transaction() as connection:
                    assert (
                        connection.execute(
                            "SELECT COUNT(*) FROM runtime_tool_calls WHERE run_id = ?",
                            (run_id,),
                        ).fetchone()[0]
                        == 0
                    )
            retry = client.post(
                f"{url}s/{run_id}/commands",
                json={"command": "retry"},
                headers={"Idempotency-Key": new_uuid7()},
            )
            assert retry.status_code == 422, retry.text
            assert retry.json()["code"] == "retry_effect_unsafe"
            assert len(client.get(f"{url}s").json()["runs"]) == 1
            assert client.get(f"{url}s/{run_id}").json() == before
            with repository.transaction() as connection:
                assert [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM runtime_tool_calls WHERE run_id = ?",
                        (run_id,),
                    ).fetchall()
                ] == original_receipts
                assert (
                    connection.execute(
                        "SELECT COUNT(*) FROM runtime_run_commands WHERE run_id = ? "
                        "AND command_type = 'retry'",
                        (run_id,),
                    ).fetchone()[0]
                    == 0
                )
            assert effects == ["write"]
            assert (tmp_path / "external-effect.txt").read_text() == "1"
        finally:
            release.set()
            assert returned.wait(5)


def test_retry_pins_version_inputs_and_lineage_across_restart(tmp_path: Path) -> None:
    effects: list[str] = []

    def fake_write(**kwargs: object) -> ToolExecution:
        effects.append("write")
        return ToolExecution({"written": True}, {"outcome": "succeeded"})

    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(
        create_app(
            settings,
            tool_adapters={"veyra.runtime.filesystem.write": fake_write},
        )
    ) as client:
        project = client.post(
            "/api/v1/projects", json={"agents": [_write_source(client)]}
        ).json()
        url = (
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{project['agents'][0]['agent_id']}"
        )
        inputs = {"path": "out.txt", "content": "original"}
        waiting = _run_until_settled(client, f"{url}/run", inputs)
        run_id = waiting["run_id"]
        _command_until_settled(client, f"{url}/run", run_id, "stop")
        original = client.get(f"{url}/runs/{run_id}").json()
        repository = client.app.state.runtime.repository
        version = dict(repository.version(original["version_id"]))
        draft = client.get(f"{url}/draft").json()
        draft["source"]["nodes"][1]["prompt"] = "Changed Draft approval"
        saved = client.patch(
            f"{url}/draft",
            json={"source": draft["source"], "expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert saved.status_code == 200, saved.text
        saved_draft = client.get(f"{url}/draft").json()
        key = new_uuid7()
        command_url = f"{url}/runs/{run_id}/commands"
        retry = client.post(
            command_url, json={"command": "retry"}, headers={"Idempotency-Key": key}
        )
        assert retry.status_code == 200, retry.text
        child = _await_run(client, f"{url}/run", retry.json()["run_id"])
        assert child["version_id"] == original["version_id"]
        assert child["conversation_id"] == original["conversation_id"]
        assert child["status"] == "waiting"
        assert (
            next(
                event["payload"]["prompt"]
                for event in child["events"]
                if event["kind"] == "approval.requested"
            )
            == "Write out.txt?"
        )
        assert repository.run_inputs(child["run_id"]) == inputs
        assert dict(repository.version(original["version_id"])) == version
        assert len(repository.agent_versions(original["agent_id"])) == 1
        assert client.get(f"{url}/draft").json() == saved_draft
        conversation_url = f"{url}/conversations/{original['conversation_id']}"
        messages = client.get(conversation_url).json()["messages"]
        assert len(messages) == 1 and messages[0]["run_id"] == run_id
        assert client.get(f"{url}/runs/{run_id}").json() == original
        created = child["events"][0]
        assert all(RunEvent.from_dict(event) for event in child["events"])
        assert created["payload"]["retry_of_run_id"] == run_id
        with repository.transaction() as connection:
            command = connection.execute(
                "SELECT * FROM runtime_run_commands WHERE command_id = ?",
                (created["payload"]["retry_command_id"],),
            ).fetchone()
            assert command["run_id"] == run_id and command["status"] == "applied"
            assert (
                json.loads(command["payload_json"])["retry_run_id"] == child["run_id"]
            )
        assert not effects
    with TestClient(
        create_app(
            settings,
            tool_adapters={"veyra.runtime.filesystem.write": fake_write},
        )
    ) as restarted:
        assert restarted.get(f"{url}/runs/{child['run_id']}").json() == child
        assert restarted.get(f"{url}/runs/{run_id}").json() == original
        replay = restarted.post(
            command_url, json={"command": "retry"}, headers={"Idempotency-Key": key}
        )
        assert replay.json()["run_id"] == child["run_id"]
        assert len(restarted.get(f"{url}/runs").json()["runs"]) == 2
        replayed = [
            json.loads(line.removeprefix("data: "))
            for frame in restarted.get(f"{url}/runs/{run_id}/events")
            .text.strip()
            .split("\n\n")
            if frame.startswith("id: ")
            for line in frame.splitlines()
            if line.startswith("data: ")
        ]
        assert replayed == original["events"]
        completed = _command_until_settled(
            restarted, f"{url}/run", child["run_id"], "approve"
        )
        assert completed["status"] == "unverified"
        assert completed["result"] == {"written": True}
        assert effects == ["write"]
        assert restarted.get(f"{url}/runs/{run_id}").json() == original
        replay = restarted.post(
            command_url, json={"command": "retry"}, headers={"Idempotency-Key": key}
        )
        assert replay.json()["run_id"] == child["run_id"]
        assert replay.json()["status"] == "unverified"
        assert effects == ["write"]
        messages = restarted.get(conversation_url).json()["messages"]
        assert [message["run_id"] for message in messages] == [run_id, child["run_id"]]


def test_concurrent_retry_key_creates_one_child(tmp_path: Path) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post(
            "/api/v1/projects", json={"agents": [_write_source(client)]}
        ).json()
        url = (
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{project['agents'][0]['agent_id']}/run"
        )
        waiting = _run_until_settled(client, url, {"path": "out.txt", "content": "one"})
        _command_until_settled(client, url, waiting["run_id"], "stop")
        key, barrier = new_uuid7(), threading.Barrier(2)

        def retry() -> str:
            barrier.wait(timeout=5)
            response = client.post(
                f"{url}s/{waiting['run_id']}/commands",
                json={"command": "retry"},
                headers={"Idempotency-Key": key},
            )
            assert response.status_code == 200, response.text
            return response.json()["run_id"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            children = list(pool.map(lambda _: retry(), range(2)))
        assert children[0] == children[1] != waiting["run_id"]
        assert _await_run(client, url, children[0])["status"] == "waiting"
        assert len(client.get(f"{url}s").json()["runs"]) == 2


def test_stop_before_dispatch_cannot_execute_after_safe_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    effects: list[str] = []
    finished = threading.Event()

    def fake_write(**kwargs: object) -> ToolExecution:
        effects.append("write")
        return ToolExecution({"written": True}, {"outcome": "succeeded"})

    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(
        create_app(
            settings,
            tool_adapters={"veyra.runtime.filesystem.write": fake_write},
        )
    ) as client:
        project = client.post(
            "/api/v1/projects", json={"agents": [_write_source(client)]}
        ).json()
        p, a = project["project_id"], project["agents"][0]["agent_id"]
        url = f"/api/v1/projects/{p}/agents/{a}/run"
        waiting = _run_until_settled(client, url, {"path": "out.txt", "content": "one"})
        runtime = client.app.state.runtime
        persist, complete = runtime._persist_event, runtime._complete_execution

        def stop_before_dispatch(
            run_id: str, node_id: str, kind: str, payload: dict
        ) -> None:
            if kind == "tool.started":
                runtime.command(p, a, run_id, "stop", new_uuid7())
            persist(run_id, node_id, kind, payload)

        def finish(*args: object, **kwargs: object) -> None:
            try:
                complete(*args, **kwargs)
            finally:
                finished.set()

        monkeypatch.setattr(runtime, "_persist_event", stop_before_dispatch)
        monkeypatch.setattr(runtime, "_complete_execution", finish)
        client.post(
            f"{url}s/{waiting['run_id']}/commands",
            json={"command": "approve"},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert finished.wait(5)
        assert effects == []
        child = _command_until_settled(client, url, waiting["run_id"], "retry")
        assert child["status"] == "waiting"
        assert effects == []


def test_retry_after_denied_tool_retains_original_receipt(tmp_path: Path) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        source = _write_source(client)
        source["extensions"]["veyra"]["permissions"]["filesystem_write_roots"] = []
        created = client.post("/api/v1/projects", json={"agents": [source]})
        assert created.status_code == 201, created.text
        project = created.json()
        url = (
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{project['agents'][0]['agent_id']}/run"
        )
        waiting = _run_until_settled(client, url, {"path": "out.txt", "content": "one"})
        failed = _command_until_settled(client, url, waiting["run_id"], "approve")
        assert failed["status"] == "failed"
        assert failed["error"]["code"] == "tool_permission_denied"
        assert not any(e["kind"] == "tool.started" for e in failed["events"])
        repository = client.app.state.runtime.repository
        with repository.transaction() as connection:
            receipt = dict(
                connection.execute(
                    "SELECT * FROM runtime_tool_calls WHERE run_id = ?",
                    (waiting["run_id"],),
                ).fetchone()
            )
        assert receipt["authorization"] == "denied"
        child = _command_until_settled(client, url, waiting["run_id"], "retry")
        assert child["status"] == "waiting"
        assert child["version_id"] == failed["version_id"]
        with repository.transaction() as connection:
            assert (
                dict(
                    connection.execute(
                        "SELECT * FROM runtime_tool_calls WHERE run_id = ?",
                        (waiting["run_id"],),
                    ).fetchone()
                )
                == receipt
            )


def test_retry_transaction_failure_leaves_no_partial_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post(
            "/api/v1/projects", json={"agents": [_write_source(client)]}
        ).json()
        p, a = project["project_id"], project["agents"][0]["agent_id"]
        url = f"/api/v1/projects/{p}/agents/{a}/run"
        waiting = _run_until_settled(client, url, {"path": "out.txt", "content": "one"})
        _command_until_settled(client, url, waiting["run_id"], "stop")
        runtime, key = client.app.state.runtime, new_uuid7()

        def fail(*args: object, **kwargs: object) -> None:
            raise OSError("simulated transaction failure")

        with monkeypatch.context() as patch:
            patch.setattr(runtime.repository, "insert_run_command", fail)
            with pytest.raises(OSError, match="simulated transaction failure"):
                runtime.command(p, a, waiting["run_id"], "retry", key)
        assert len(client.get(f"{url}s").json()["runs"]) == 1
        child = runtime.command(p, a, waiting["run_id"], "retry", key)
        assert _await_run(client, url, child["run_id"])["status"] == "waiting"
        assert len(client.get(f"{url}s").json()["runs"]) == 2
