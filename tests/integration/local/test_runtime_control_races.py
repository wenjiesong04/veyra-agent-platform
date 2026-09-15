from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.wire import RunEvent
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.runtime.tools import ToolExecution

from .test_runtime_routes import _command_until_settled, _write_source


@pytest.mark.parametrize("command", ["stop", "approve", "reject"])
def test_approval_pause_commits_state_and_evidence_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    effects: list[str] = []

    def fake_write(**kwargs: object) -> ToolExecution:
        effects.append("write")
        return ToolExecution({"written": True}, {"outcome": "succeeded"})

    with TestClient(create_app(settings)) as client:
        project = client.post(
            "/api/v1/projects", json={"agents": [_write_source(client)]}
        ).json()
        p, a = project["project_id"], project["agents"][0]["agent_id"]
        url = f"/api/v1/projects/{p}/agents/{a}/run"
        runtime = client.app.state.runtime
        pause, complete = runtime._pause_run, runtime._complete_execution
        entered, release, finished = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )

        def delayed_pause(*args: object, **kwargs: object) -> object:
            entered.set()
            assert release.wait(5)
            return pause(*args, **kwargs)

        def finish(*args: object, **kwargs: object) -> None:
            try:
                complete(*args, **kwargs)
            finally:
                finished.set()

        monkeypatch.setattr(runtime, "_pause_run", delayed_pause)
        monkeypatch.setattr(runtime, "_complete_execution", finish)
        key = new_uuid7()
        started = client.post(
            url,
            json={"inputs": {"path": "out.txt", "content": "one"}},
            headers={"Idempotency-Key": key},
        )
        assert started.status_code == 200
        run_id = started.json()["run_id"]
        detail_url = f"{url}s/{run_id}"
        try:
            assert entered.wait(5)
            before = client.get(detail_url).json()
            if command == "stop":
                _command_until_settled(client, url, run_id, "stop")
                stopped = client.get(detail_url).json()
        finally:
            release.set()
            assert finished.wait(5)
        detail = client.get(detail_url).json()
        if command == "stop":
            assert detail == stopped
            assert detail["status"] == "cancelled"
        else:
            assert detail["status"] == "waiting"
        assert not any(
            event["kind"] in {"node.waiting", "approval.requested"}
            or (
                event["kind"] == "checkpoint.created"
                and event["payload"]["waiting_kind"] == "approval"
            )
            for event in before["events"]
        )
        with runtime.repository.transaction() as connection:
            pending = runtime.repository.pending_approval(connection, run_id)
            checkpoint = runtime.repository.latest_checkpoint(connection, run_id)
            if command == "stop":
                assert pending is None
                assert checkpoint["waiting_kind"] == "execution"
            else:
                assert pending["node_id"] == checkpoint["node_id"] == "approve"
                assert [event["kind"] for event in detail["events"][-3:]] == [
                    "node.waiting",
                    "approval.requested",
                    "checkpoint.created",
                ]
        replay = client.post(
            url,
            json={"inputs": {"path": "out.txt", "content": "one"}},
            headers={"Idempotency-Key": key},
        ).json()
        assert replay["status"] == detail["status"]

    with TestClient(
        create_app(
            settings, tool_adapters={"veyra.runtime.filesystem.write": fake_write}
        )
    ) as restarted:
        assert restarted.get(detail_url).json() == detail
        assert effects == []
        if command != "stop":
            result = _command_until_settled(restarted, url, run_id, command)
            assert result["status"] == "unverified"
            assert result["result"] == {"written": command == "approve"}
            assert effects == (["write"] if command == "approve" else [])
        else:
            rejected = restarted.post(
                f"{detail_url}/commands",
                json={"command": "approve"},
                headers={"Idempotency-Key": new_uuid7()},
            )
            assert rejected.status_code == 422
            assert rejected.json()["code"] == "command_not_applicable"
        events = restarted.get(detail_url).json()["events"]
        assert all(RunEvent.from_dict(event) for event in events)
        replayed = [
            json.loads(line.removeprefix("data: "))
            for frame in restarted.get(f"{detail_url}/events")
            .text.strip()
            .split("\n\n")
            if frame.startswith("id: ")
            for line in frame.splitlines()
            if line.startswith("data: ")
        ]
        assert replayed == events
