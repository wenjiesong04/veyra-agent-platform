"""Native Workflow Tools deliver exact files through pinned effect approvals."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.resources import ResourceCatalog

from .test_loop_resource_truth import _client, _pin
from .test_runtime_routes import ScriptedRuntimeTransport
from .test_workflow_version_boundary import await_workflow, save

WRITE = "veyra.tool.filesystem.write@1.0.0"
COMPARE = "veyra.tool.tabular.compare@1.0.0"
REPORT = "# Reconciliation\n\nOrder A: 0.30\nDifference: 1.50\n"


def _write_node(node_id: str, path_value: str = "reportpath") -> dict[str, Any]:
    return {
        "id": node_id,
        "component_type": "Tool",
        "uses": WRITE,
        "input_mapping": {"path": path_value, "content": "report"},
        "output_mapping": {"written": "written"},
    }


def _setup(
    client: TestClient,
    tools: Sequence[dict[str, Any]],
    *,
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    protect: bool = False,
    protected_fields: Sequence[str] = (),
) -> tuple[str, str, Path, dict[str, Any]]:
    created = client.post("/api/v1/projects", json={"name": "Native Tool delivery"})
    assert created.status_code == 201, created.text
    project = created.json()
    project_id = project["project_id"]
    resources = [
        ResourceCatalog().detail(*reference.rsplit("@", 1))
        for reference in dict.fromkeys(node["uses"] for node in tools)
    ]
    _pin(client, project_id, *resources)
    workflow = client.post(
        f"/api/v1/projects/{project_id}/workflows", json={"name": "Save native report"}
    )
    assert workflow.status_code == 201, workflow.text
    url = f"/api/v1/projects/{project_id}/workflows/{workflow.json()['workflow_id']}"
    draft = client.get(f"{url}/draft").json()
    nodes = [
        {"id": "start", "component_type": "Start"},
        *tools,
        {
            "id": "output",
            "component_type": "Output",
            "output_name": next(iter(outputs or {"written": "boolean"})),
        },
    ]
    source = draft["source"]
    source.update(
        inputs=inputs or {"reportpath": "string", "report": "string"},
        outputs=outputs or {"written": "boolean"},
        nodes=nodes,
        transitions=[
            {"from": before["id"], "port": "next", "to": after["id"]}
            for before, after in zip(nodes, nodes[1:], strict=False)
        ],
        lock={
            resource["reference"]: resource["content_hash"] for resource in resources
        },
        ui={
            "positions": {
                node["id"]: {"x": index * 180, "y": 0}
                for index, node in enumerate(nodes)
            }
        },
    )
    permissions: dict[str, Any] = {
        field: list(
            dict.fromkeys(
                value
                for resource in resources
                for value in resource.get("required_permissions", {}).get(field, [])
            )
        )
        for field in (
            "tools",
            "network_hosts",
            "filesystem_read_roots",
            "filesystem_write_roots",
        )
    }
    permissions["shell_workspace_only"] = False
    if permissions["filesystem_write_roots"]:
        permissions["filesystem_write_roots"] = ["project/reports"]
    permissions["protect_input_files"] = protect
    if protected_fields:
        permissions["protected_input_fields"] = list(protected_fields)
        permissions["filesystem_read_roots"] = list(
            dict.fromkeys([*permissions["filesystem_read_roots"], "project/reports"])
        )
    source["extensions"]["veyra"]["permissions"] = permissions
    saved = save(client, url, draft)
    version = client.post(
        f"{url}/commit",
        json={"expected_revision": saved["revision"]},
        headers={"If-Match": saved["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert version.status_code == 200, version.text
    return project_id, url, Path(project["root_path"]), version.json()


def _start(
    client: TestClient, url: str, version: dict[str, Any], inputs: dict[str, Any]
) -> dict[str, Any]:
    started = client.post(
        f"{url}/run",
        json={
            "inputs": inputs,
            "source": "committed",
            "version_id": version["version_id"],
        },
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert started.status_code == 200, started.text
    return await_workflow(client, url, started.json()["run_id"])


def _command(
    client: TestClient,
    url: str,
    current: dict[str, Any],
    decision: str,
    *,
    key: str | None = None,
) -> dict[str, Any]:
    response = client.post(
        f"{url}/runs/{current['run_id']}/commands",
        json={
            "command": decision,
            "expected_request_id": current["waiting"]["request_id"],
        },
        headers={"Idempotency-Key": key or new_uuid7()},
    )
    assert response.status_code == 200, response.text
    return await_workflow(client, url, current["run_id"])


def _context(client: TestClient, run_id: str) -> dict[str, Any]:
    return json.loads(
        client.app.state.workflow_runtime.store.row(run_id)["context_json"]
    )


def _events(run: dict[str, Any], kind: str, node_id: str | None = None) -> list[dict]:
    return [
        event
        for event in run["events"]
        if event["kind"] == kind and (node_id is None or event["node_id"] == node_id)
    ]


def _assert_no_model_or_child(
    client: TestClient, model: ScriptedRuntimeTransport, run: dict[str, Any]
) -> None:
    assert model.calls == []
    assert run["children"] == []
    with closing(client.app.state.runtime.repository._connect()) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM runtime_runs").fetchone()[0] == 0
        )


def _assert_tool_wait(run: dict[str, Any], node_id: str = "write") -> None:
    assert run["status"] == "waiting", run
    assert run["waiting"]["kind"] == "approval"
    assert run["waiting"]["node_id"] == node_id
    assert run["waiting"]["context"]["kind"] == "tool_permission"
    assert run["waiting"]["request_id"]
    assert _events(run, "tool.started", node_id) == []


def test_native_write_is_ready_and_saves_exact_report_after_bound_approval(
    tmp_path: Path,
) -> None:
    model = ScriptedRuntimeTransport([])
    relative = "reports/reconciliation.md"
    with _client(tmp_path, model) as client:
        _, url, root, version = _setup(client, [_write_node("write")])
        readiness = client.get(
            f"{url}/runtime-readiness", params={"version_id": version["version_id"]}
        )
        assert readiness.status_code == 200, readiness.text
        assert readiness.json()["ready"] is True, readiness.json()
        checks = readiness.json()["tools"]
        assert len(checks) == 1
        assert checks[0]["node_id"] == "write"
        assert checks[0]["tool_reference"] == WRITE
        assert checks[0]["ready"] is True
        assert checks[0]["code"] == "ready"
        assert checks[0]["approval_required"] is True
        waiting = _start(
            client, url, version, {"reportpath": relative, "report": REPORT}
        )
        _assert_tool_wait(waiting)
        assert not (root / relative).exists()
        _assert_no_model_or_child(client, model, waiting)
        pending = _context(client, waiting["run_id"])["pending_tool"]
        snapshot = {
            "node_id": "write",
            "source_hash": version["source_hash"],
            "tool_reference": WRITE,
            "resource_hash": ResourceCatalog().detail(*WRITE.rsplit("@", 1))[
                "content_hash"
            ],
            "input_digest": sha256_digest(
                {"path": relative, "content": sha256_digest(REPORT)}
            ),
            "arguments": {"path": relative, "content": REPORT},
        }
        assert pending == {
            **snapshot,
            "snapshot_digest": sha256_digest(snapshot),
            "request_id": waiting["waiting"]["request_id"],
        }
        summary = waiting["waiting"]["approval_summary"]
        assert summary["content_preview"] == REPORT
        assert summary["content_bytes"] == len(REPORT.encode())
        assert summary["content_digest"] == sha256_digest({"content": REPORT})

        finished = _command(client, url, waiting, "approve")

        assert finished["status"] == "unverified", finished
        assert finished["result"] == {"written": True}
        assert (root / relative).read_bytes() == REPORT.encode()
        assert (
            hashlib.sha256((root / relative).read_bytes()).hexdigest()
            == hashlib.sha256(REPORT.encode()).hexdigest()
        )
        _assert_no_model_or_child(client, model, finished)
        assert len(_events(finished, "tool.started", "write")) == 1
        assert len(_events(finished, "tool.completed", "write")) == 1
        completed = _events(finished, "node.completed", "write")
        assert len(completed) == 1
        assert completed[0]["payload"] == {"port": "next"}


def test_reject_cancels_native_write_without_creating_report(tmp_path: Path) -> None:
    model = ScriptedRuntimeTransport([])
    with _client(tmp_path, model) as client:
        _, url, root, version = _setup(client, [_write_node("write")])
        waiting = _start(
            client,
            url,
            version,
            {"reportpath": "reports/rejected.md", "report": REPORT},
        )
        _assert_tool_wait(waiting)
        rejected = _command(client, url, waiting, "reject")
        assert rejected["status"] == "cancelled", rejected
        assert rejected["waiting"] is None
        assert not (root / "reports/rejected.md").exists()
        assert _events(rejected, "tool.started") == []
        assert _events(rejected, "tool.completed") == []
        assert _events(rejected, "node.completed", "write") == []
        assert len(_events(rejected, "node.cancelled", "write")) == 1
        _assert_no_model_or_child(client, model, rejected)


def test_each_write_requires_its_own_nonce_and_duplicate_approval_never_rewrites(
    tmp_path: Path,
) -> None:
    model = ScriptedRuntimeTransport([])
    with _client(tmp_path, model) as client:
        _, url, root, version = _setup(
            client,
            [
                _write_node("write_first", "firstpath"),
                _write_node("write_second", "secondpath"),
            ],
            inputs={"firstpath": "string", "secondpath": "string", "report": "string"},
        )
        first = _start(
            client,
            url,
            version,
            {
                "firstpath": "reports/first.md",
                "secondpath": "reports/second.md",
                "report": REPORT,
            },
        )
        _assert_tool_wait(first, "write_first")
        first_key = new_uuid7()
        second = _command(client, url, first, "approve", key=first_key)
        _assert_tool_wait(second, "write_second")
        assert second["waiting"]["request_id"] != first["waiting"]["request_id"]
        assert (root / "reports/first.md").read_bytes() == REPORT.encode()
        assert not (root / "reports/second.md").exists()
        external_edit = b"External edit after the first successful write"
        (root / "reports/first.md").write_bytes(external_edit)

        duplicate = _command(client, url, first, "approve", key=first_key)
        assert duplicate["waiting"] == second["waiting"]
        assert (root / "reports/first.md").read_bytes() == external_edit
        assert len(_events(duplicate, "tool.started", "write_first")) == 1
        assert _events(duplicate, "tool.started", "write_second") == []
        stale = client.post(
            f"{url}/runs/{first['run_id']}/commands",
            json={
                "command": "approve",
                "expected_request_id": first["waiting"]["request_id"],
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert stale.status_code == 422, stale.text
        assert stale.json()["code"] == "command_request_changed"
        assert not (root / "reports/second.md").exists()

        finished = _command(client, url, second, "approve")
        assert finished["status"] == "unverified", finished
        assert (root / "reports/second.md").read_bytes() == REPORT.encode()
        assert (root / "reports/first.md").read_bytes() == external_edit
        assert len(_events(finished, "tool.started", "write_first")) == 1
        assert len(_events(finished, "tool.started", "write_second")) == 1
        replayed = _command(client, url, first, "approve", key=first_key)
        assert replayed["status"] == "unverified"
        assert (root / "reports/first.md").read_bytes() == external_edit
        assert len(_events(replayed, "tool.completed")) == 2
        _assert_no_model_or_child(client, model, replayed)


@pytest.mark.parametrize("changed", ["values", "arguments"])
def test_pending_parameter_change_fails_snapshot_validation_before_native_effect(
    tmp_path: Path, changed: str
) -> None:
    model = ScriptedRuntimeTransport([])
    with _client(tmp_path, model) as client:
        _, url, root, version = _setup(client, [_write_node("write")])
        waiting = _start(
            client,
            url,
            version,
            {"reportpath": "reports/tampered.md", "report": REPORT},
        )
        _assert_tool_wait(waiting)
        repository = client.app.state.workflow_runtime.repository
        with repository.transaction() as connection:
            row = connection.execute(
                "SELECT context_json FROM workflow_runs WHERE run_id = ?",
                (waiting["run_id"],),
            ).fetchone()
            context = json.loads(row["context_json"])
            if changed == "values":
                context["values"]["report"] = "Changed after the approval preview"
            else:
                context["pending_tool"]["arguments"]["content"] = (
                    "Altered pending arguments"
                )
            connection.execute(
                "UPDATE workflow_runs SET context_json = ? WHERE run_id = ?",
                (json.dumps(context), waiting["run_id"]),
            )

        failed = _command(client, url, waiting, "approve")

        assert failed["status"] == "failed", failed
        assert failed["error"]["code"] == "workflow_tool_snapshot_changed"
        assert not (root / "reports/tampered.md").exists()
        assert _events(failed, "tool.started") == []
        assert _events(failed, "tool.completed") == []
        _assert_no_model_or_child(client, model, failed)


def test_approved_native_write_cannot_overwrite_protected_original(
    tmp_path: Path,
) -> None:
    original = b"order,amount\r\nA,0.10\r\nA,0.20\r\n"
    model = ScriptedRuntimeTransport([])
    with _client(tmp_path, model) as client:
        _, url, root, version = _setup(
            client,
            [_write_node("write", "inputpath")],
            inputs={"inputpath": "string", "report": "string"},
            protect=True,
            protected_fields=["inputpath"],
        )
        path = root / "reports/input.csv"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(original)
        original_hash = hashlib.sha256(original).hexdigest()
        waiting = _start(
            client, url, version, {"inputpath": "reports/input.csv", "report": REPORT}
        )
        _assert_tool_wait(waiting)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == original_hash
        protected = _events(waiting, "input.protected")
        assert len(protected) == 1
        assert protected[0]["payload"]["sha256"] == original_hash

        failed = _command(client, url, waiting, "approve")

        assert failed["status"] == "failed", failed
        assert failed["error"]["code"] == "input_file_protected"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == original_hash
        assert path.read_bytes() == original
        assert _events(failed, "tool.completed") == []
        assert (
            _events(failed, "tool.failed")[0]["payload"]["code"]
            == "input_file_protected"
        )
        _assert_no_model_or_child(client, model, failed)


def test_native_tabular_compare_maps_real_underscore_parameters_without_entity_defaults(
    tmp_path: Path,
) -> None:
    model = ScriptedRuntimeTransport([])
    node = {
        "id": "compare",
        "component_type": "Tool",
        "uses": COMPARE,
        "input_mapping": {
            "left_path": "leftpath",
            "right_path": "rightpath",
            "left_key": "key",
            "right_key": "key",
            "left_amount": "amount",
            "right_amount": "amount",
            "include_all_groups": "includeall",
        },
        "output_mapping": {"totals": "totals", "left": "left", "right": "right"},
    }
    left = b"order,amount\nA,0.10\nA,0.20\nB,1.00\n"
    right = b"order,amount\nA,0.30\nB,0.50\n"
    with _client(tmp_path, model) as client:
        _, url, root, version = _setup(
            client,
            [node],
            inputs={
                "leftpath": "string",
                "rightpath": "string",
                "key": "string",
                "amount": "string",
                "includeall": "boolean",
            },
            outputs={"totals": "object", "left": "object", "right": "object"},
        )
        (root / "assets/left.csv").write_bytes(left)
        (root / "assets/right.csv").write_bytes(right)
        finished = _start(
            client,
            url,
            version,
            {
                "leftpath": "assets/left.csv",
                "rightpath": "assets/right.csv",
                "key": "order",
                "amount": "amount",
                "includeall": True,
            },
        )
        assert finished["status"] == "unverified", finished
        assert Decimal(finished["result"]["totals"]["left_all"]) == Decimal("1.30")
        assert Decimal(finished["result"]["totals"]["right_all"]) == Decimal("0.80")
        assert finished["result"]["left"]["sha256"] == hashlib.sha256(left).hexdigest()
        assert (
            finished["result"]["right"]["sha256"] == hashlib.sha256(right).hexdigest()
        )
        completed = _events(finished, "tool.completed", "compare")
        assert len(completed) == 1
        arguments = {
            "left_path": "assets/left.csv",
            "right_path": "assets/right.csv",
            "left_key": "order",
            "right_key": "order",
            "left_amount": "amount",
            "right_amount": "amount",
            "include_all_groups": True,
        }
        assert completed[0]["payload"]["input_digest"] == sha256_digest(arguments)
        assert _events(finished, "approval.resolved") == []
        assert (root / "assets/left.csv").read_bytes() == left
        assert (root / "assets/right.csv").read_bytes() == right
        _assert_no_model_or_child(client, model, finished)


def test_completed_native_receipt_persists_input_hash_snapshot_and_request_link(
    tmp_path: Path,
) -> None:
    model = ScriptedRuntimeTransport([])
    with _client(tmp_path, model) as client:
        _, url, root, version = _setup(client, [_write_node("write")])
        waiting = _start(
            client,
            url,
            version,
            {"reportpath": "reports/receipt.md", "report": REPORT},
        )
        pending = _context(client, waiting["run_id"])["pending_tool"]
        finished = _command(client, url, waiting, "approve")
        assert finished["status"] == "unverified", finished
        resolved = _events(finished, "approval.resolved", "write")[0]
        started = _events(finished, "tool.started", "write")[0]
        completed = _events(finished, "tool.completed", "write")[0]
        payload = completed["payload"]
        assert resolved["payload"] == {
            "decision": "approve",
            "request_id": pending["request_id"],
        }
        assert payload["tool_reference"] == WRITE
        assert payload["adapter"] == "veyra.runtime.filesystem.write"
        assert payload["authorization"] == "allowed"
        assert payload["relative_path"] == "reports/receipt.md"
        assert payload["byte_length"] == len(REPORT.encode())
        assert payload["input_digest"] == pending["input_digest"]
        assert payload["output_digest"] == sha256_digest({"written": True})
        assert payload["snapshot_digest"] == pending["snapshot_digest"]
        assert payload["request_id"] == pending["request_id"]
        for key in ("input_digest", "snapshot_digest", "request_id"):
            assert started["payload"][key] == payload[key]
        assert resolved["sequence"] < started["sequence"] < completed["sequence"]
        repository = client.app.state.workflow_runtime.repository
        with closing(repository._connect()) as connection:
            row = connection.execute(
                "SELECT payload_json FROM workflow_run_events WHERE event_id = ?",
                (completed["event_id"],),
            ).fetchone()
            assert json.loads(row["payload_json"]) == payload
        reloaded = client.get(f"{url}/runs/{finished['run_id']}").json()
        assert _events(reloaded, "tool.completed", "write")[0] == completed
        assert (root / "reports/receipt.md").read_bytes() == REPORT.encode()
        _assert_no_model_or_child(client, model, reloaded)
