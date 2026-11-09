from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.resources import ResourceCatalog

from .test_loop_resource_truth import (
    _attach,
    _client,
    _create_project,
    _loop_source,
    _pin,
    _set_io,
)
from .test_runtime_routes import ScriptedRuntimeTransport, _command_until_settled


@pytest.mark.parametrize(
    "stop_phase", ["during_model", "before_commit", "before_pause", "after_pause"]
)
def test_stopped_loop_retains_failed_read_receipt_without_finishing_or_replaying(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stop_phase: str
) -> None:
    entered, release, finished = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    read = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    source = _attach(
        _set_io(
            _loop_source("Translate text"), {"message": "string"}, {"result": "string"}
        ),
        read,
    )
    actions = [
        {
            "action": "tool",
            "tool": read["reference"],
            "arguments": {"path": "absent.txt"},
        },
        (
            {"action": "ask_user", "question": "Which file should I read?"}
            if stop_phase in {"before_pause", "after_pause"}
            else {"action": "final", "outputs": {"result": "Read was unavailable"}}
        ),
    ]

    class Transport(ScriptedRuntimeTransport):
        def complete(self, messages: object):
            if stop_phase == "during_model" and len(self.calls) == 1:
                entered.set()
                assert release.wait(5)
            return super().complete(messages)

    transport = Transport([json.dumps(action) for action in actions])
    with _client(tmp_path, transport) as client:
        project = _create_project(client, source)
        project_id, agent_id = project["project_id"], project["agents"][0]["agent_id"]
        _pin(client, project_id, read)
        runtime = client.app.state.runtime
        complete = runtime._complete_execution

        def complete_and_signal(*args: Any, **kwargs: Any) -> None:
            try:
                complete(*args, **kwargs)
            finally:
                finished.set()

        monkeypatch.setattr(runtime, "_complete_execution", complete_and_signal)
        if stop_phase != "during_model":
            method = (
                "_pause_run"
                if stop_phase in {"before_pause", "after_pause"}
                else "_commit_outcome"
            )
            persist = getattr(runtime, method)

            def persist_after_stop(*args: Any, **kwargs: Any):
                committed = (
                    persist(*args, **kwargs) if stop_phase == "after_pause" else None
                )
                entered.set()
                assert release.wait(5)
                return (
                    committed
                    if stop_phase == "after_pause"
                    else persist(*args, **kwargs)
                )

            monkeypatch.setattr(runtime, method, persist_after_stop)
        run_url = f"/api/v1/projects/{project_id}/agents/{agent_id}/run"
        started = client.post(
            run_url,
            json={"inputs": {"message": "Use the selected project material"}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        run_id = started.json()["run_id"]
        try:
            assert entered.wait(5)
            stopped = _command_until_settled(client, run_url, run_id, "stop")
            assert stopped["status"] == "cancelled"
        finally:
            release.set()
            assert finished.wait(5)
        detail = client.get(f"{run_url}s/{run_id}").json()
        assert detail["status"] == "cancelled"
        assert detail["result"] is None
        assert not any(event["kind"] == "run.completed" for event in detail["events"])
        with runtime.repository.transaction() as connection:
            records = connection.execute(
                "SELECT * FROM runtime_tool_calls WHERE run_id = ?", (run_id,)
            ).fetchall()
        assert len(records) == 1
        receipt = json.loads(records[0]["receipt_json"])
        assert receipt["outcome"] == "failed"
        assert receipt["recovery"] == "observe"
        assert receipt["code"] == "tool_input_invalid"
        assert records[0]["authorization"] == "allowed"
        assert len(transport.calls) == 2
        assert sum(event["kind"] == "tool.started" for event in detail["events"]) == 1
