"""Explicit Workflow Stop ends delivery without fabricating business outputs."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7

from .test_loop_resource_truth import _client
from .test_runtime_routes import ScriptedRuntimeTransport
from .test_workflow_version_boundary import await_workflow, save

REPORT = "Reviewed project report: delivery dates conflict; approver is unknown."


def _setup(client: TestClient, *, legacy_decline: bool = False) -> tuple[str, str]:
    created = client.post("/api/v1/projects", json={"name": "Reviewed delivery"})
    assert created.status_code == 201, created.text
    project_id = created.json()["project_id"]
    workflow = client.post(
        f"/api/v1/projects/{project_id}/workflows",
        json={"name": "Approve reviewed report"},
    )
    assert workflow.status_code == 201, workflow.text
    url = f"/api/v1/projects/{project_id}/workflows/{workflow.json()['workflow_id']}"
    draft = client.get(f"{url}/draft").json()
    terminal = (
        {
            "id": "decline",
            "component_type": "Transform",
            "mapping": {"finalreport": "Declined"},
        }
        if legacy_decline
        else {"id": "stop", "component_type": "Stop"}
    )
    nodes = [
        {"id": "start", "component_type": "Start"},
        {
            "id": "candidate",
            "component_type": "Transform",
            "mapping": {"finalreport": REPORT},
        },
        {
            "id": "approval",
            "component_type": "HumanApproval",
            "prompt": "Approve delivery of this report?\n{{finalreport}}",
        },
        {
            "id": "deliver",
            "component_type": "Transform",
            "mapping": {"finalreport": "{{finalreport}}"},
        },
        {"id": "output", "component_type": "Output", "output_name": "finalreport"},
        terminal,
    ]
    transitions = [
        {"from": "start", "port": "next", "to": "candidate"},
        {"from": "candidate", "port": "next", "to": "approval"},
        {"from": "approval", "port": "approved", "to": "deliver"},
        {"from": "approval", "port": "rejected", "to": terminal["id"]},
        {"from": "deliver", "port": "next", "to": "output"},
    ]
    if legacy_decline:
        transitions.append({"from": "decline", "port": "next", "to": "output"})
    source = draft["source"]
    source.update(
        inputs={"request": "string"},
        outputs={"finalreport": "string"},
        nodes=nodes,
        transitions=transitions,
        lock={},
        ui={
            "positions": {
                node["id"]: {"x": index * 180, "y": 0}
                for index, node in enumerate(nodes)
            }
        },
    )
    source["extensions"]["veyra"]["permissions"] = {"tools": [], "network_hosts": []}
    source["extensions"]["veyra"]["verification"] = {"required": False, "checks": []}
    saved = save(client, url, draft)
    committed = client.post(
        f"{url}/commit",
        json={"expected_revision": saved["revision"]},
        headers={"If-Match": saved["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert committed.status_code == 200, committed.text
    return url, committed.json()["version_id"]


def _start(client: TestClient, url: str, version_id: str) -> dict[str, Any]:
    started = client.post(
        f"{url}/run",
        json={
            "source": "committed",
            "version_id": version_id,
            "inputs": {"request": "Review the original project material."},
        },
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert started.status_code == 200, started.text
    waiting = await_workflow(client, url, started.json()["run_id"])
    assert waiting["status"] == "waiting", waiting
    assert waiting["result"] is None
    assert waiting["waiting"]["kind"] == "approval"
    assert REPORT in waiting["waiting"]["prompt"]
    assert waiting["version_id"] == version_id
    return waiting


def _decide(
    client: TestClient,
    url: str,
    waiting: dict[str, Any],
    decision: str,
    *,
    key: str | None = None,
) -> dict[str, Any]:
    response = client.post(
        f"{url}/runs/{waiting['run_id']}/commands",
        json={
            "command": decision,
            "expected_request_id": waiting["waiting"]["request_id"],
        },
        headers={"Idempotency-Key": key or new_uuid7()},
    )
    assert response.status_code == 200, response.text
    return await_workflow(client, url, waiting["run_id"])


def _started(run: dict[str, Any]) -> list[str]:
    return [
        event["node_id"] for event in run["events"] if event["kind"] == "node.started"
    ]


def _assert_no_external_calls(
    client: TestClient,
    model: ScriptedRuntimeTransport,
    tools: Mock,
    run: dict[str, Any],
) -> None:
    assert model.calls == []
    tools.assert_not_called()
    assert run["children"] == []
    with closing(client.app.state.runtime.repository._connect()) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM runtime_runs").fetchone()[0] == 0
        )


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_explicit_stop_keeps_candidate_private_until_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, decision: str
) -> None:
    model = ScriptedRuntimeTransport([])
    with _client(tmp_path, model) as client:
        tools = Mock(side_effect=AssertionError("No Workflow Tool may execute"))
        monkeypatch.setattr(client.app.state.runtime.tools, "execute", tools)
        url, version_id = _setup(client)
        waiting = _start(client, url, version_id)
        assert _started(waiting) == ["start", "candidate", "approval"]
        finished = _decide(client, url, waiting, decision)
        assert finished["waiting"] is None
        assert finished["error"] is None
        assert finished["finished_at"]
        assert finished["version_id"] == version_id
        if decision == "approve":
            assert finished["status"] == "unverified", finished
            assert finished["result"] == {"finalreport": REPORT}
            assert _started(finished) == [
                "start",
                "candidate",
                "approval",
                "deliver",
                "output",
            ]
            assert not any(
                event["kind"] == "run.cancelled" for event in finished["events"]
            )
        else:
            assert finished["status"] == "cancelled", finished
            assert finished["result"] is None
            assert _started(finished) == ["start", "candidate", "approval", "stop"]
            assert [event["kind"] for event in finished["events"][-2:]] == [
                "node.completed",
                "run.cancelled",
            ]
            assert finished["events"][-2]["node_id"] == "stop"
            assert not any(
                event["kind"] == "run.completed" for event in finished["events"]
            )
        _assert_no_external_calls(client, model, tools, finished)


def test_stop_preserves_bound_decisions_and_does_not_restart_on_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = ScriptedRuntimeTransport([])
    with _client(tmp_path, model) as client:
        tools = Mock(side_effect=AssertionError("No Workflow Tool may execute"))
        monkeypatch.setattr(client.app.state.runtime.tools, "execute", tools)
        url, version_id = _setup(client)
        waiting = _start(client, url, version_id)
        command_url = f"{url}/runs/{waiting['run_id']}/commands"
        stale = client.post(
            command_url,
            json={"command": "reject", "expected_request_id": new_uuid7()},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert stale.status_code == 422, stale.text
        assert stale.json()["code"] == "command_request_changed"
        assert (
            client.get(f"{url}/runs/{waiting['run_id']}").json()["waiting"]
            == waiting["waiting"]
        )
        key = new_uuid7()
        stopped = _decide(client, url, waiting, "reject", key=key)
        assert stopped["status"] == "cancelled", stopped
        replayed = _decide(client, url, waiting, "reject", key=key)
        assert replayed == stopped
        late = client.post(
            command_url,
            json={
                "command": "approve",
                "expected_request_id": waiting["waiting"]["request_id"],
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert late.status_code == 422, late.text
        assert late.json()["code"] == "command_not_applicable"
        client.app.state.workflow_runtime._execute(waiting["run_id"])
        assert client.get(f"{url}/runs/{waiting['run_id']}").json() == stopped
        _assert_no_external_calls(client, model, tools, stopped)


def test_explicit_legacy_rejected_route_still_returns_its_declared_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = ScriptedRuntimeTransport([])
    with _client(tmp_path, model) as client:
        tools = Mock(side_effect=AssertionError("No Workflow Tool may execute"))
        monkeypatch.setattr(client.app.state.runtime.tools, "execute", tools)
        url, version_id = _setup(client, legacy_decline=True)
        waiting = _start(client, url, version_id)
        finished = _decide(client, url, waiting, "reject")
        assert finished["status"] == "unverified", finished
        assert finished["result"] == {"finalreport": "Declined"}
        assert _started(finished) == [
            "start",
            "candidate",
            "approval",
            "decline",
            "output",
        ]
        assert not any(event["kind"] == "run.cancelled" for event in finished["events"])
        _assert_no_external_calls(client, model, tools, finished)
