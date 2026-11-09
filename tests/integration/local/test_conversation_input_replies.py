"""Native input replies remain user evidence in later conversation turns."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.service import RuntimeError as RuntimeFailure

from .test_complex_agent_acceptance import _app_start, _commit
from .test_loop_resource_truth import (
    _attach,
    _client,
    _create_project,
    _loop_source,
    _pin,
    _set_io,
)
from .test_runtime_routes import ScriptedRuntimeTransport, _await_run
from .test_waiting_request_binding import _flow


def _source() -> dict[str, Any]:
    return _set_io(
        _loop_source("Summarize only supplied task facts"),
        {"request": "string"},
        {"result": "string"},
    )


def _messages(client: TestClient, base: str, conversation_id: str) -> list[dict]:
    response = client.get(f"{base}/conversations/{conversation_id}")
    assert response.status_code == 200, response.text
    return response.json()["messages"]


def _reply(
    client: TestClient,
    base: str,
    run: dict[str, Any],
    answer: str,
    *,
    request_id: str | None = None,
    key: str | None = None,
):
    request = next(
        event["payload"]["request_id"]
        for event in reversed(run["events"])
        if event["kind"] == "approval.requested"
    )
    return client.post(
        f"{base}/runs/{run['run_id']}/commands",
        json={
            "command": "reply",
            "expected_request_id": request_id or request,
            "inputs": {"reply": answer},
        },
        headers={"Idempotency-Key": key or new_uuid7()},
    )


def test_reply_is_durable_and_reaches_only_the_same_committed_conversation(
    tmp_path: Path,
) -> None:
    marker = "CORRECTED_OWNER_BOB_481"
    transport = ScriptedRuntimeTransport(
        [
            json.dumps({"action": "ask_user", "question": "Who is the owner?"}),
            json.dumps({"action": "final", "outputs": {"result": "Task updated"}}),
            json.dumps({"action": "final", "outputs": {"result": "Next result"}}),
            json.dumps({"action": "final", "outputs": {"result": "Fresh result"}}),
        ]
    )
    with _client(tmp_path, transport) as client:
        project = _create_project(client, _source())
        pid, aid = project["project_id"], project["agents"][0]["agent_id"]
        base = f"/api/v1/projects/{pid}/agents/{aid}"
        version = _commit(client, pid, aid)
        first = _app_start(client, f"{base}/run", {"request": "Owner not recorded"})
        assert first["status"] == "waiting"
        cid = first["conversation_id"]
        key = new_uuid7()
        accepted = _reply(client, base, first, marker, key=key)
        assert accepted.status_code == 200, accepted.text
        completed = _await_run(client, f"{base}/run", first["run_id"])
        assert completed["status"] == "unverified"
        messages = _messages(client, base, cid)
        assert [(row["role"], row["content"]) for row in messages] == [
            ("user", "Owner not recorded"),
            ("user", marker),
            ("assistant", "Task updated"),
        ]
        assert messages[1]["run_id"] == first["run_id"]
        assert messages[1]["conversation_id"] == cid
        replay = _reply(client, base, first, marker, key=key)
        assert replay.status_code == 200, replay.text
        assert _messages(client, base, cid) == messages
        assert len(transport.calls) == 2

        second = _app_start(
            client,
            f"{base}/run",
            {"request": "Summarize again"},
            conversation_id=cid,
        )
        assert second["conversation_id"] == cid
        assert second["version_id"] == version["version_id"]
        assert second["run_id"] != first["run_id"]
        assert f"user: {marker}" in json.dumps(transport.calls[-1])
        assert "assistant: Task updated" in json.dumps(transport.calls[-1])
        fresh = _app_start(client, f"{base}/run", {"request": "Fresh facts"})
        assert fresh["conversation_id"] != cid
        assert marker not in json.dumps(transport.calls[-1])


def test_changed_input_request_cannot_append_a_stale_reply(tmp_path: Path) -> None:
    transport = ScriptedRuntimeTransport(
        [
            json.dumps({"action": "ask_user", "question": "Which owner?"}),
            json.dumps({"action": "ask_user", "question": "Which date?"}),
        ]
    )
    with _client(tmp_path, transport) as client:
        project = _create_project(client, _source())
        pid, aid = project["project_id"], project["agents"][0]["agent_id"]
        base = f"/api/v1/projects/{pid}/agents/{aid}"
        _commit(client, pid, aid)
        first = _app_start(client, f"{base}/run", {"request": "Initial facts"})
        rejected = _reply(client, base, first, "WRONG_REQUEST", request_id=new_uuid7())
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "command_request_changed"
        assert len(_messages(client, base, first["conversation_id"])) == 1
        assert _reply(client, base, first, "Confirmed owner").status_code == 200
        second = _await_run(client, f"{base}/run", first["run_id"])
        assert second["status"] == "waiting"
        before = _messages(client, base, first["conversation_id"])
        stale = _reply(client, base, first, "STALE_REPLY")
        assert stale.status_code == 422
        assert stale.json()["code"] == "command_request_changed"
        assert _messages(client, base, first["conversation_id"]) == before
        assert len(transport.calls) == 2


def test_tool_approval_does_not_append_a_user_message(tmp_path: Path) -> None:
    write = ResourceCatalog().detail("veyra.tool.filesystem.write", "1.0.0")
    source = _attach(_source(), write)
    transport = ScriptedRuntimeTransport(
        [
            json.dumps(
                {
                    "action": "tool",
                    "tool": write["reference"],
                    "arguments": {"path": "reports/result.txt", "content": "Facts"},
                }
            ),
            json.dumps({"action": "final", "outputs": {"result": "Saved facts"}}),
        ]
    )
    with _client(tmp_path, transport) as client:
        project = _create_project(client, source)
        pid, aid = project["project_id"], project["agents"][0]["agent_id"]
        base = f"/api/v1/projects/{pid}/agents/{aid}"
        _pin(client, pid, write)
        _commit(client, pid, aid)
        first = _app_start(client, f"{base}/run", {"request": "Save supplied facts"})
        assert first["status"] == "waiting"
        rejected = _reply(client, base, first, "Not an approval")
        assert rejected.status_code == 422
        approved = client.post(
            f"{base}/runs/{first['run_id']}/commands",
            json={"command": "approve"},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert approved.status_code == 200, approved.text
        completed = _await_run(client, f"{base}/run", first["run_id"])
        assert completed["status"] == "unverified"
        users = [
            row["content"]
            for row in _messages(client, base, first["conversation_id"])
            if row["role"] == "user"
        ]
        assert users == ["Save supplied facts"]


@pytest.mark.parametrize("changed", ["project_id", "agent_id", "agent_version_id"])
def test_reply_checks_the_existing_conversation_binding(
    tmp_path: Path, changed: str
) -> None:
    transport = ScriptedRuntimeTransport(
        json.dumps({"action": "ask_user", "question": "Which owner?"})
    )
    with _client(tmp_path, transport) as client:
        project = _create_project(client, _source())
        pid, aid = project["project_id"], project["agents"][0]["agent_id"]
        base = f"/api/v1/projects/{pid}/agents/{aid}"
        _commit(client, pid, aid)
        first = _app_start(client, f"{base}/run", {"request": "Initial facts"})
        other = _create_project(client, _source())
        other_aid = other["agents"][0]["agent_id"]
        version = _commit(client, other["project_id"], other_aid)
        replacement = {
            "project_id": other["project_id"],
            "agent_id": other_aid,
            "agent_version_id": version["version_id"],
        }[changed]
        repository = client.app.state.runtime.repository
        with repository.transaction() as connection:
            connection.execute(
                f"UPDATE agent_conversations SET {changed} = ? "
                "WHERE conversation_id = ?",
                (replacement, first["conversation_id"]),
            )
        before = repository.agent_conversation_messages(first["conversation_id"])
        rejected = _reply(client, base, first, "MUST_NOT_BE_APPENDED")
        assert rejected.status_code == 422
        assert rejected.json()["code"] == (
            "conversation_version_mismatch"
            if changed == "agent_version_id"
            else "conversation_not_found"
        )
        assert [
            dict(row)
            for row in repository.agent_conversation_messages(first["conversation_id"])
        ] == [dict(row) for row in before]
        assert len(transport.calls) == 1
        assert (
            client.get(f"{base}/runs/{first['run_id']}").json()["status"] == "waiting"
        )


def test_workflow_child_reply_does_not_invent_an_agent_conversation(
    tmp_path: Path,
) -> None:
    with _flow(tmp_path) as flow:
        child = flow.client.get(flow.child_url()).json()
        assert child["conversation_id"] is None
        before = flow.client.app.state.runtime.repository.agent_conversations(
            flow.project_id, child["agent_id"]
        )
        accepted = flow.command(
            "reply", flow.first["waiting"]["request_id"], inputs={"reply": "amount"}
        )
        assert accepted.status_code == 200, accepted.text
        child = _await_run(
            flow.client,
            f"/api/v1/projects/{flow.project_id}/agents/{child['agent_id']}/run",
            child["run_id"],
        )
        assert child["status"] == "waiting"
        assert child["conversation_id"] is None
        assert (
            flow.client.app.state.runtime.repository.agent_conversations(
                flow.project_id, child["agent_id"]
            )
            == before
        )


def test_reply_and_approval_resolution_roll_back_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = ScriptedRuntimeTransport(
        json.dumps({"action": "ask_user", "question": "Which owner?"})
    )
    with _client(tmp_path, transport) as client:
        project = _create_project(client, _source())
        pid, aid = project["project_id"], project["agents"][0]["agent_id"]
        base = f"/api/v1/projects/{pid}/agents/{aid}"
        _commit(client, pid, aid)
        first = _app_start(client, f"{base}/run", {"request": "Initial facts"})
        before = _messages(client, base, first["conversation_id"])
        repository = client.app.state.runtime.repository

        def failed_touch(*args, **kwargs):
            raise RuntimeFailure("conversation_write_failed", "Synthetic write failure")

        with monkeypatch.context() as patch:
            patch.setattr(repository, "touch_agent_conversation", failed_touch)
            rejected = _reply(client, base, first, "ROLLBACK_REPLY")
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "conversation_write_failed"
        assert _messages(client, base, first["conversation_id"]) == before
        pending = client.get(f"{base}/runs/{first['run_id']}").json()
        assert pending["status"] == "waiting"
        assert not any(
            event["kind"] == "approval.resolved" for event in pending["events"]
        )
        assert len(transport.calls) == 1
