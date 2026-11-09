"""User actions bind the displayed request across native loops and Workflows."""

from __future__ import annotations

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.unit.local.test_gated_role_composition import _generate, _task
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.task_structure import ExecutionBoundary, TaskStage
from veyra_agent_platform.local.builder.composite_apply import apply_composite
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.service import RuntimeError as RuntimeFailure

from .test_runtime_routes import ScriptedRuntimeTransport, _await_run
from .test_workflow_version_boundary import await_workflow
from .verified_runtime_model import verified_client


@dataclass
class Flow:
    client: TestClient
    transport: ScriptedRuntimeTransport
    project_id: str
    root: Path
    url: str
    run_id: str
    first: dict[str, Any]

    def detail(self) -> dict[str, Any]:
        return await_workflow(self.client, self.url, self.run_id)

    def command(
        self,
        command: str,
        request_id: str,
        *,
        inputs: dict | None = None,
        key: str | None = None,
    ):
        return self.client.post(
            f"{self.url}/runs/{self.run_id}/commands",
            json={
                "command": command,
                "expected_request_id": request_id,
                **({"inputs": inputs} if inputs is not None else {}),
            },
            headers={"Idempotency-Key": key or new_uuid7()},
        )

    def child_url(self) -> str:
        wait = self.first["waiting"]
        return (
            f"/api/v1/projects/{self.project_id}/agents/{wait['agent_id']}"
            f"/runs/{wait['child_run_id']}"
        )


@contextmanager
def _flow(
    tmp_path: Path, *, typed: bool = False, two_writes: bool = False
) -> Iterator[Flow]:
    task = _task()
    task = replace(
        task, outputs=(task.outputs[0], replace(task.outputs[1], required=False))
    )
    if typed:
        task = replace(
            task,
            stages=(
                TaskStage(id="choose_one", summary="Choose first file"),
                TaskStage(id="choose_two", summary="Choose final file"),
                replace(
                    task.stages[0],
                    input_sources={"material_path": "choose_two.file_path"},
                ),
                *task.stages[1:],
            ),
            execution_boundaries=(
                *task.execution_boundaries,
                *(
                    ExecutionBoundary(
                        kind="human_input",
                        stage=stage,
                        reason="Select source",
                        question="Which file?",
                        expected_schema={"file_path": "string"},
                    )
                    for stage in ("choose_one", "choose_two")
                ),
            ),
        )
    else:
        task = replace(
            task,
            execution_boundaries=(
                *task.execution_boundaries,
                ExecutionBoundary(
                    kind="human_input",
                    stage="review",
                    reason="Clarify source",
                    question="Which column?",
                ),
            ),
        )
    report = "Reviewed synthetic source"
    report_path = "reports/first.md" if two_writes else "reports/review.md"
    steps = (
        []
        if typed
        else [
            {
                "action": "ask_user",
                "question": "Which column?",
                "context": {"columns": ["amount", "total"]},
            },
            {
                "action": "ask_user",
                "question": "Which unit?",
                "context": {"units": ["USD", "CNY"]},
            },
        ]
    )
    steps.extend(
        [
            {
                "action": "tool",
                "tool": "veyra.tool.filesystem.read@1.0.0",
                "arguments": {"path": "assets/material.txt"},
            },
            {
                "action": "final",
                "outputs": {
                    "report-text": report,
                    "report-path": report_path,
                    "outcome": {"reviewed": True},
                },
            },
            {
                "action": "tool",
                "tool": "veyra.tool.filesystem.write@1.0.0",
                "arguments": {"path": report_path, "content": report},
            },
        ]
    )
    if two_writes:
        steps.append(
            {
                "action": "tool",
                "tool": "veyra.tool.filesystem.write@1.0.0",
                "arguments": {"path": "reports/second.md", "content": report},
            }
        )
    steps.append(
        {
            "action": "final",
            "outputs": {
                "saved-report": {
                    "path": "reports/second.md" if two_writes else report_path
                }
            },
        }
    )
    transport = ScriptedRuntimeTransport([json.dumps(step) for step in steps])
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    product = _generate(task)
    assert product.status == "review", product.diagnostics
    with verified_client(settings, transport) as client:
        project = client.post(
            "/api/v1/projects", json={"name": "Request-bound flow"}
        ).json()
        pid, root = project["project_id"], Path(project["root_path"])
        (root / "assets").mkdir(exist_ok=True)
        (root / "assets/material.txt").write_bytes(b"Original synthetic data")
        for tool in ("read", "write"):
            resource = ResourceCatalog().detail(
                f"veyra.tool.filesystem.{tool}", "1.0.0"
            )
            bound = client.post(
                f"/api/v1/projects/{pid}/resources",
                json={key: resource[key] for key in ("reference", "content_hash")},
            )
            assert bound.status_code == 201, bound.text
        applied = apply_composite(
            projects=client.app.state.projects,
            library=client.app.state.library,
            project_id=pid,
            companions=product.orchestration.companions,
            workflow=product.orchestration.workflow,
            flow=product.orchestration.flow,
        )
        url = f"/api/v1/projects/{pid}/workflows/{applied['workflow_id']}"
        draft = client.get(f"{url}/draft").json()
        committed = client.post(
            f"{url}/commit",
            json={"expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert committed.status_code == 200, committed.text
        started = client.post(
            f"{url}/run",
            json={
                "inputs": {"materialpath": "assets/material.txt"},
                "source": "committed",
                "version_id": committed.json()["version_id"],
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        rid = started.json()["run_id"]
        yield Flow(
            client, transport, pid, root, url, rid, await_workflow(client, url, rid)
        )


def _request_id(detail: dict[str, Any]) -> str:
    return next(
        event["payload"]["request_id"]
        for event in reversed(detail["events"])
        if event["kind"] == "approval.requested"
    )


@pytest.mark.parametrize("legacy_event_alias", [False, True])
def test_agent_old_question_is_not_consumed_by_a_new_question(
    tmp_path: Path, legacy_event_alias: bool
) -> None:
    with _flow(tmp_path) as flow:
        url = flow.child_url()
        first = flow.client.get(url).json()
        request_id = _request_id(first)
        if legacy_event_alias:
            request_id = next(
                event["event_id"]
                for event in reversed(first["events"])
                if event["kind"] == "approval.requested"
            )
        key = new_uuid7()
        body = {
            "command": "reply",
            "inputs": {"reply": "amount"},
            "expected_request_id": request_id,
        }
        replied = flow.client.post(
            f"{url}/commands", json=body, headers={"Idempotency-Key": key}
        )
        assert replied.status_code == 200, replied.text
        second = _await_run(
            flow.client,
            url.rsplit("/runs/", 1)[0] + "/run",
            first["run_id"],
        )
        second_id = _request_id(second)
        assert second_id != request_id and len(flow.transport.calls) == 2
        stale = flow.client.post(
            f"{url}/commands", json=body, headers={"Idempotency-Key": new_uuid7()}
        )
        assert (
            stale.status_code == 422
            and stale.json()["code"] == "command_request_changed"
        )
        assert _request_id(flow.client.get(url).json()) == second_id
        assert (
            flow.client.post(
                f"{url}/commands", json=body, headers={"Idempotency-Key": key}
            ).status_code
            == 200
        )
        conflict = flow.client.post(
            f"{url}/commands",
            json={**body, "expected_request_id": second_id},
            headers={"Idempotency-Key": key},
        )
        assert conflict.status_code == 409
        assert len(flow.transport.calls) == 2
        assert not (flow.root / "reports/review.md").exists()


def test_parent_refreshes_direct_child_reply_but_rejects_stale_parent_action(
    tmp_path: Path,
) -> None:
    with _flow(tmp_path) as flow:
        first_id = flow.first["waiting"]["request_id"]
        direct = flow.client.post(
            f"{flow.child_url()}/commands",
            json={
                "command": "reply",
                "inputs": {"reply": "amount"},
                "expected_request_id": first_id,
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert direct.status_code == 200, direct.text
        child = flow.first["waiting"]
        _await_run(
            flow.client,
            f"/api/v1/projects/{flow.project_id}/agents/{child['agent_id']}/run",
            child["child_run_id"],
        )
        second = flow.detail()
        assert second["waiting"]["prompt"] == "Which unit?"
        assert second["waiting"]["child_run_id"] == child["child_run_id"]
        stale = flow.command("reply", first_id, inputs={"reply": "old column answer"})
        assert (
            stale.status_code == 422
            and stale.json()["code"] == "command_request_changed"
        )
        assert len(flow.transport.calls) == 2
        assert (
            flow.command(
                "reply", second["waiting"]["request_id"], inputs={"reply": "CNY"}
            ).status_code
            == 200
        )
        gate = flow.detail()
        assert gate["waiting"]["kind"] == "approval"
        assert (
            flow.command("approve", second["waiting"]["request_id"]).status_code == 422
        )
        key = new_uuid7()
        assert (
            flow.command("approve", gate["waiting"]["request_id"], key=key).status_code
            == 200
        )
        tool = flow.detail()
        assert tool["waiting"]["kind"] == "agent"
        assert not (flow.root / "reports/review.md").exists()
        assert flow.command("approve", gate["waiting"]["request_id"]).status_code == 422
        assert (
            flow.command("approve", gate["waiting"]["request_id"], key=key).status_code
            == 200
        )
        assert len(flow.transport.calls) == 5
        assert flow.command("approve", tool["waiting"]["request_id"]).status_code == 200
        assert flow.detail()["status"] == "verified"
        assert (
            flow.root / "reports/review.md"
        ).read_text() == "Reviewed synthetic source"
        assert (
            flow.root / "assets/material.txt"
        ).read_bytes() == b"Original synthetic data"


def test_old_tool_approval_cannot_approve_the_next_write(tmp_path: Path) -> None:
    with _flow(tmp_path, two_writes=True) as flow:
        for reply in ("amount", "CNY"):
            wait = flow.detail()["waiting"]
            assert (
                flow.command(
                    "reply", wait["request_id"], inputs={"reply": reply}
                ).status_code
                == 200
            )
        gate = flow.detail()["waiting"]
        assert flow.command("approve", gate["request_id"]).status_code == 200
        first = flow.detail()["waiting"]
        key = new_uuid7()
        assert flow.command("approve", first["request_id"], key=key).status_code == 200
        second = flow.detail()["waiting"]
        assert first["request_id"] != second["request_id"]
        assert second["approval_summary"]["target"] == "reports/second.md"
        assert (flow.root / "reports/first.md").is_file()
        assert not (flow.root / "reports/second.md").exists()
        assert flow.command("approve", first["request_id"]).status_code == 422
        assert flow.command("approve", first["request_id"], key=key).status_code == 200
        assert not (flow.root / "reports/second.md").exists()
        assert len(flow.transport.calls) == 6
        assert flow.command("approve", second["request_id"]).status_code == 200
        assert flow.detail()["status"] == "verified"
        assert (flow.root / "reports/second.md").is_file()
        assert len(flow.transport.calls) == 7


def test_parent_and_child_command_roll_back_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _flow(tmp_path) as flow:
        service = flow.client.app.state.workflow_runtime
        consume = service._consume_wait

        def fail_after_parent_update(*args, **kwargs):
            consume(*args, **kwargs)
            raise RuntimeFailure(
                "command_request_changed", "Controlled stale parent race"
            )

        monkeypatch.setattr(service, "_consume_wait", fail_after_parent_update)
        wait = flow.first["waiting"]
        key = new_uuid7()
        rejected = flow.command(
            "reply", wait["request_id"], inputs={"reply": "amount"}, key=key
        )
        assert rejected.status_code == 422, rejected.text
        assert flow.detail()["waiting"]["request_id"] == wait["request_id"]
        child = flow.client.get(flow.child_url()).json()
        assert child["status"] == "waiting" and _request_id(child) == wait["request_id"]
        assert len(flow.transport.calls) == 1
        assert not any(
            event["kind"] == "approval.resolved" for event in child["events"]
        )
        with flow.client.app.state.repository.transaction() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM idempotency_records WHERE scope = ?",
                    (f"workflow-command:{flow.run_id}",),
                ).fetchone()[0]
                == 0
            )
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM idempotency_records WHERE scope = ?",
                    (f"run-command:{wait['child_run_id']}",),
                ).fetchone()[0]
                == 0
            )
        monkeypatch.setattr(service, "_consume_wait", consume)
        assert (
            flow.command(
                "reply", wait["request_id"], inputs={"reply": "amount"}, key=key
            ).status_code
            == 200
        )
        assert flow.detail()["waiting"]["prompt"] == "Which unit?"
        assert not any(
            event["kind"] == "node.completed" and event["node_id"] == wait["node_id"]
            for event in flow.detail()["events"]
        )


def test_typed_workflow_input_waits_have_distinct_request_bindings(
    tmp_path: Path,
) -> None:
    with _flow(tmp_path, typed=True) as flow:
        first = flow.first["waiting"]
        field = first["expected_fields"][0]
        assert (
            flow.command(
                "reply", first["request_id"], inputs={field: "assets/material.txt"}
            ).status_code
            == 200
        )
        second = flow.detail()["waiting"]
        assert second["request_id"] != first["request_id"]
        first_completed = [
            event
            for event in flow.detail()["events"]
            if event["kind"] == "node.completed"
            and event["node_id"] == first["node_id"]
        ]
        assert len(first_completed) == 1
        stale = flow.command(
            "reply", first["request_id"], inputs={field: "assets/old.txt"}
        )
        assert stale.status_code == 422 and len(flow.transport.calls) == 0
        assert (
            flow.command(
                "reply",
                second["request_id"],
                inputs={second["expected_fields"][0]: "assets/material.txt"},
            ).status_code
            == 200
        )
        assert flow.detail()["waiting"]["kind"] == "approval"
        assert len(flow.transport.calls) == 2
        assert not (flow.root / "reports/review.md").exists()


@pytest.mark.parametrize("child_decision", ["reply", "stop"])
def test_direct_child_completion_or_stop_settles_parent_without_duplicate_dispatch(
    tmp_path: Path, child_decision: str
) -> None:
    with _flow(tmp_path) as flow:
        url = flow.child_url()
        if child_decision == "reply":
            for reply in ("amount", "CNY"):
                snapshot = flow.client.get(url).json()
                response = flow.client.post(
                    f"{url}/commands",
                    json={
                        "command": "reply",
                        "inputs": {"reply": reply},
                        "expected_request_id": _request_id(snapshot),
                    },
                    headers={"Idempotency-Key": new_uuid7()},
                )
                assert response.status_code == 200, response.text
                _await_run(
                    flow.client, url.rsplit("/runs/", 1)[0] + "/run", snapshot["run_id"]
                )
        else:
            stopped = flow.client.post(
                f"{url}/commands",
                json={"command": "stop"},
                headers={"Idempotency-Key": new_uuid7()},
            )
            assert stopped.status_code == 200, stopped.text
        with ThreadPoolExecutor(max_workers=4) as executor:
            replies = list(
                executor.map(
                    lambda _: flow.client.get(f"{flow.url}/runs/{flow.run_id}"),
                    range(8),
                )
            )
        assert all(response.status_code == 200 for response in replies)
        final = flow.detail()
        assert len(final["children"]) == 1
        if child_decision == "reply":
            assert (
                final["status"] == "waiting" and final["waiting"]["kind"] == "approval"
            )
            assert len(flow.transport.calls) == 4
            assert (
                sum(
                    event["kind"] == "node.started" and event["node_id"] == "check"
                    for event in final["events"]
                )
                == 1
            )
        else:
            assert (
                final["status"] == "failed"
                and final["error"]["code"] == "workflow_agent_failed"
            )
            assert len(flow.transport.calls) == 1
            assert flow.detail()["status"] == "failed"
        assert not (flow.root / "reports/review.md").exists()


def test_legacy_independent_wait_gains_a_stable_request_id_without_execution(
    tmp_path: Path,
) -> None:
    with _flow(tmp_path, typed=True) as flow:
        old = flow.first["waiting"]
        with flow.client.app.state.repository.transaction() as connection:
            row = connection.execute(
                "SELECT context_json FROM workflow_runs WHERE run_id = ?",
                (flow.run_id,),
            ).fetchone()
            context = json.loads(row["context_json"])
            context["waiting"].pop("request_id")
            connection.execute(
                "UPDATE workflow_runs SET context_json = ? WHERE run_id = ?",
                (json.dumps(context), flow.run_id),
            )
        restored = flow.detail()["waiting"]
        assert restored["request_id"] and restored["request_id"] != old["request_id"]
        assert flow.detail()["waiting"] == restored
        assert len(flow.transport.calls) == 0
        assert (
            flow.command(
                "reply",
                old["request_id"],
                inputs={old["expected_fields"][0]: "assets/material.txt"},
            ).status_code
            == 422
        )
        assert (
            flow.command(
                "reply",
                restored["request_id"],
                inputs={restored["expected_fields"][0]: "assets/material.txt"},
            ).status_code
            == 200
        )
        assert flow.detail()["waiting"]["request_id"] != restored["request_id"]
        assert len(flow.transport.calls) == 0
