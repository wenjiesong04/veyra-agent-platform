"""Execute compiler-generated roles and gates with native filesystem tools."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tests.unit.local.test_gated_role_composition import _generate, _task
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.task_structure import ExecutionBoundary
from veyra_agent_platform.local.builder.composite_apply import apply_composite
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.resources import ResourceCatalog

from .test_runtime_routes import ScriptedRuntimeTransport
from .test_workflow_version_boundary import await_workflow
from .verified_runtime_model import verified_client


@pytest.mark.parametrize("decision", ["approve", "reject", "invalid_report"])
def test_generated_report_requires_check_and_business_consent_before_native_write(
    tmp_path: Path, decision: str
) -> None:
    report = "Reviewed synthetic material" if decision != "invalid_report" else ""
    transport = ScriptedRuntimeTransport(
        [
            json.dumps(
                {
                    "action": "tool",
                    "tool": "veyra.tool.filesystem.read@1.0.0",
                    "arguments": {"path": "assets/material.txt"},
                }
            ),
            json.dumps(
                {
                    "action": "final",
                    "outputs": {
                        "report-text": report,
                        "report-path": "reports/review.md",
                        "outcome": {"reviewed": True},
                    },
                }
            ),
            json.dumps(
                {
                    "action": "tool",
                    "tool": "veyra.tool.filesystem.write@1.0.0",
                    "arguments": {"path": "reports/review.md", "content": report},
                }
            ),
            json.dumps(
                {
                    "action": "final",
                    "outputs": {"saved-report": {"path": "reports/review.md"}},
                }
            ),
        ]
    )
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'db.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with verified_client(settings, transport) as client:
        project = client.post("/api/v1/projects", json={"name": "Gated report"}).json()
        pid = project["project_id"]
        root = Path(project["root_path"])
        original = root / "assets/material.txt"
        original.parent.mkdir(exist_ok=True)
        original.write_text("Synthetic material", encoding="utf-8")
        catalog = ResourceCatalog()
        for tool in ("read", "write"):
            resource = catalog.detail(f"veyra.tool.filesystem.{tool}", "1.0.0")
            bound = client.post(
                f"/api/v1/projects/{pid}/resources",
                json={key: resource[key] for key in ("reference", "content_hash")},
            )
            assert bound.status_code == 201, bound.text
        product = _generate(_task())
        assert product.status == "review", product.diagnostics
        assert product.orchestration is not None
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
        current = await_workflow(client, url, rid)
        target = root / "reports/review.md"
        assert not target.exists()
        assert original.read_text(encoding="utf-8") == "Synthetic material"
        assert len(transport.calls) == 2
        if decision == "invalid_report":
            assert current["status"] != "waiting", current
            assert any(
                event["kind"] == "verifier.result"
                and event["payload"]["passed"] is False
                for event in current["events"]
            )
            return
        assert current["status"] == "waiting", current
        assert current["waiting"]["kind"] == "approval", current
        response = client.post(
            f"{url}/runs/{rid}/commands",
            json={"command": decision},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert response.status_code == 200, response.text
        current = await_workflow(client, url, rid)
        if decision == "reject":
            assert not target.exists()
            assert len(transport.calls) == 2
            return
        assert current["status"] == "waiting", current
        assert current["waiting"]["kind"] == "agent", current
        assert not target.exists()
        authorized = client.post(
            f"{url}/runs/{rid}/commands",
            json={"command": "approve"},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert authorized.status_code == 200, authorized.text
        finished = await_workflow(client, url, rid)
        assert finished["status"] == "verified", finished
        assert finished["result"]["reporttext"] == report
        assert finished["result"]["savedreport"] == {"path": "reports/review.md"}
        assert target.read_text(encoding="utf-8") == report
        assert original.read_text(encoding="utf-8") == "Synthetic material"
        assert "Synthetic material" in json.dumps(transport.calls[1])
        assert report in json.dumps(transport.calls[2])
        writer = finished["children"][-1]
        child = client.get(
            f"/api/v1/projects/{pid}/agents/{writer['agent_id']}/runs/{writer['child_run_id']}"
        ).json()
        assert any(event["kind"] == "tool.completed" for event in child["events"]), (
            child
        )


@pytest.mark.parametrize("decision", ["approve", "reject", "stop"])
def test_workflow_forwards_native_questions_without_authorizing_later_writes(
    tmp_path: Path, decision: str
) -> None:
    report = "Only reviewed data"
    transport = ScriptedRuntimeTransport(
        [
            json.dumps(
                {
                    "action": "ask_user",
                    "question": "Which column?",
                    "context": {"columns": ["amount", "total"]},
                }
            ),
            json.dumps(
                {
                    "action": "ask_user",
                    "question": "Which unit?",
                    "context": {"units": ["USD", "CNY"]},
                }
            ),
            json.dumps(
                {
                    "action": "tool",
                    "tool": "veyra.tool.filesystem.read@1.0.0",
                    "arguments": {"path": "assets/material.txt"},
                }
            ),
            json.dumps(
                {
                    "action": "final",
                    "outputs": {
                        "report-text": report,
                        "report-path": "reports/review.md",
                        "outcome": {"reviewed": True},
                    },
                }
            ),
            json.dumps(
                {
                    "action": "tool",
                    "tool": "veyra.tool.filesystem.write@1.0.0",
                    "arguments": {"path": "reports/review.md", "content": report},
                }
            ),
            json.dumps(
                {
                    "action": "final",
                    "outputs": {"saved-report": {"path": "reports/review.md"}},
                }
            ),
        ]
    )
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'db.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    task = _task()
    task = replace(
        task,
        outputs=(task.outputs[0], replace(task.outputs[1], required=False)),
        execution_boundaries=(
            *task.execution_boundaries,
            ExecutionBoundary(
                kind="human_input",
                stage="review",
                reason="Ask only when unclear",
                question="Which column?",
            ),
        ),
    )
    product = _generate(task)
    assert product.status == "review", product.diagnostics
    with verified_client(settings, transport) as client:
        project = client.post(
            "/api/v1/projects", json={"name": "Native questions"}
        ).json()
        pid = project["project_id"]
        root = Path(project["root_path"])
        original = root / "assets/material.txt"
        original.parent.mkdir(exist_ok=True)
        original.write_text("Original data", encoding="utf-8")
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
        current = await_workflow(client, url, rid)
        waiting = current["waiting"]
        assert waiting["kind"] == "input" and waiting["prompt"] == "Which column?"
        assert waiting["input_schema"] == {"reply": "string"}
        assert waiting["context"] == {"columns": ["amount", "total"]}
        first_child = waiting["child_run_id"]
        first_request = waiting["request_id"]
        assert len(transport.calls) == 1
        target = root / "reports/review.md"
        assert not target.exists()

        def command(name: str, inputs: dict | None = None, key: str | None = None):
            return client.post(
                f"{url}/runs/{rid}/commands",
                json={
                    "command": name,
                    **({"inputs": inputs} if inputs is not None else {}),
                },
                headers={"Idempotency-Key": key or new_uuid7()},
            )

        if decision == "stop":
            assert command("stop").status_code == 200
            stopped = client.get(f"{url}/runs/{rid}").json()
            assert stopped["status"] == "cancelled"
            assert stopped["children"][0]["status"] == "cancelled"
            assert len(transport.calls) == 1 and not target.exists()
            return
        assert command("approve").status_code == 422
        assert command("reply", {"wrong": "amount"}).status_code == 422
        assert len(transport.calls) == 1
        key = new_uuid7()
        assert command("reply", {"reply": "amount"}, key).status_code == 200
        current = await_workflow(client, url, rid)
        assert current["waiting"]["child_run_id"] == first_child
        assert current["waiting"]["request_id"] != first_request
        assert current["waiting"]["prompt"] == "Which unit?"
        assert "amount" in json.dumps(transport.calls[1])
        assert command("reply", {"reply": "amount"}, key).status_code == 200
        assert len(transport.calls) == 2
        assert command("reply", {"reply": "CNY"}).status_code == 200
        current = await_workflow(client, url, rid)
        assert current["waiting"]["kind"] == "approval"
        assert len(transport.calls) == 4 and not target.exists()
        assert command("reply", {"reply": "save"}).status_code == 422
        assert command(decision).status_code == 200
        current = await_workflow(client, url, rid)
        if decision == "reject":
            assert current["status"] == "cancelled", current
            assert current["result"] is None
            assert len(transport.calls) == 4 and not target.exists()
        else:
            assert current["waiting"]["kind"] == "agent"
            assert (
                current["waiting"]["tool_reference"]
                == "veyra.tool.filesystem.write@1.0.0"
            )
            assert (
                current["waiting"]["approval_summary"]["target"] == "reports/review.md"
            )
            assert len(transport.calls) == 5 and not target.exists()
            assert command("reply", {"reply": "yes"}).status_code == 422
            assert command("approve").status_code == 200
            current = await_workflow(client, url, rid)
            assert current["status"] == "verified", current
            assert target.read_text(encoding="utf-8") == report
            assert len(transport.calls) == 6
        assert len(current["children"]) == (2 if decision == "approve" else 1)
        assert current["children"][0]["child_run_id"] == first_child
        assert original.read_text(encoding="utf-8") == "Original data"
