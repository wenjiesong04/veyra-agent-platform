"""Runtime acceptance for Builder Generation Architecture V2.

Proposal → Apply → Run → pause → resume → state → verify → output.
Scripted Factory and Runtime providers only.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.runtime.tools import ToolExecution
from veyra_agent_platform.local.secrets import MacOSKeychainSecretStore

from .test_factory_routes import ScriptedKimiTransport, _completion
from .test_loop_resource_truth import _PNG
from .test_runtime_routes import ScriptedRuntimeTransport
from .verified_runtime_model import verified_client

RESEARCH = "帮我做一个研究助手，可以搜索网页并整理报告"
WORKSPACE = "帮我做一个可以查看和修改项目文件的开发助手，写文件前需要确认"
SECONDHAND = (
    "帮我做一个二手商品整理和上架助手。"
    "我会一次上传很多照片。"
    "它要识别商品、查价格、写介绍。"
    "型号看不出来就问我。"
    "价格要让我确认。"
    "每件商品状态和价格历史都要保存。"
)
DOCUMENT = "上传一份合同。提取关键信息。如果金额超过 10 万让我审批。确认后存档。"


@pytest.fixture(autouse=True)
def isolate_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MacOSKeychainSecretStore, "get", lambda self, ref: None)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("VEYRA_FACTORY_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("VEYRA_FACTORY_MODEL_ID", raising=False)
    monkeypatch.delenv("VEYRA_RUNTIME_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("VEYRA_RUNTIME_MODEL_ID", raising=False)


def _final(outputs: dict[str, Any]) -> str:
    return json.dumps({"action": "final", "outputs": outputs})


def _fake_search(**kwargs: Any) -> ToolExecution:
    values = kwargs["values"]
    authorization = kwargs["authorization"]
    output = {
        "provider": "scripted",
        "query": values.get("query"),
        "results": [
            {
                "title": "Fixture evidence",
                "url": "https://example.test/research",
                "snippet": "SEARCH_RESULT_V2",
            }
        ],
        "status": 200,
    }
    return ToolExecution(
        output=output,
        receipt={
            "tool_reference": authorization.tool_reference,
            "adapter": authorization.adapter,
            "permission": "allowed",
            "authorization": "allowed",
            "input_digest": authorization.input_digest,
            "output_digest": "b" * 64,
            "byte_length": 12,
            "relative_path": "",
        },
    )


def _client(
    tmp_path: Path, runtime: object | None = None
) -> AbstractContextManager[TestClient]:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    options: dict[str, Any] = {
        "factory_transport": ScriptedKimiTransport(
            [_completion("ok") for _ in range(24)]
        ),
        "tool_adapters": {"veyra.runtime.web.search": _fake_search},
    }
    if runtime is None:
        return TestClient(create_app(settings, **options))
    return verified_client(settings, runtime, **options)


def _project(client: TestClient) -> str:
    created = client.post("/api/v1/projects", json={"name": "V2 Runtime"})
    assert created.status_code == 201, created.text
    return str(created.json()["project_id"])


def _generate(client: TestClient, project_id: str, goal: str) -> dict[str, Any]:
    created = client.post(
        f"/api/v1/projects/{project_id}/factory/sessions",
        json={"goal": goal},
    )
    assert created.status_code in {200, 201}, created.text
    generated = client.post(
        f"/api/v1/projects/{project_id}/factory/sessions/"
        f"{created.json()['session_id']}/generate"
    )
    assert generated.status_code == 200, generated.text
    return generated.json()


def _apply(
    client: TestClient, project_id: str, session: dict[str, Any]
) -> dict[str, Any]:
    applied = client.post(
        f"/api/v1/projects/{project_id}/factory/sessions/"
        f"{session['session_id']}/apply-draft",
        json={"confirm": True},
    )
    assert applied.status_code == 200, applied.text
    return applied.json()


def _await_agent(client: TestClient, url: str, run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 20
    detail: dict[str, Any] = {}
    while time.monotonic() < deadline:
        detail = client.get(f"{url}s/{run_id}").json()
        if detail["status"] != "running":
            return detail
        time.sleep(0.05)
    raise AssertionError(f"agent run stayed running: {detail}")


def _await_workflow(client: TestClient, url: str, run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 20
    detail: dict[str, Any] = {}
    while time.monotonic() < deadline:
        detail = client.get(f"{url}/runs/{run_id}").json()
        if detail["status"] != "running":
            return detail
        time.sleep(0.05)
    raise AssertionError(f"workflow run stayed running: {detail}")


def _started_counts(detail: dict[str, Any]) -> Counter[str]:
    return Counter(
        str(event["node_id"])
        for event in detail["events"]
        if event["kind"] == "node.started"
    )


def _ref(artifact_id: str, filename: str, media_type: str) -> dict[str, str]:
    return {
        "kind": "artifact",
        "artifact_id": artifact_id,
        "media_type": media_type,
        "filename": filename,
    }


def test_research_v2_stays_pure_agent_and_runs(tmp_path: Path) -> None:
    transport = ScriptedRuntimeTransport(
        _final({"result": {"summary": "bounded findings", "hit": "SEARCH_RESULT_V2"}})
    )
    with _client(tmp_path, runtime=transport) as client:
        project_id = _project(client)
        session = _generate(client, project_id, RESEARCH)
        assert session.get("product_shape") == "PURE_AGENT"
        assert session.get("target_kind") == "agent"
        types = [node["component_type"] for node in session["blueprint"]["nodes"]]
        assert types == ["Start", "Model", "Output"]
        applied = _apply(client, project_id, session)
        agent_id = applied["agent"]["agent_id"]
        url = f"/api/v1/projects/{project_id}/agents/{agent_id}/run"
        draft = client.get(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/draft"
        ).json()
        committed = client.post(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/commit",
            json={"expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert committed.status_code == 200, committed.text
        started = client.post(
            url,
            json={
                "inputs": {"request": "summarize public notes"},
                "source": "committed",
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        settled = _await_agent(client, url, started.json()["run_id"])
        assert settled["status"] in {"verified", "unverified"}


def test_workspace_editor_keeps_tool_approval_canvas(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id = _project(client)
        session = _generate(client, project_id, WORKSPACE)
        assert session.get("product_shape") == "PURE_AGENT"
        preview = session.get("proposal_preview") or {}
        assert preview.get("tool_approvals")
        assert not preview.get("business_approvals")
        types = [node["component_type"] for node in session["blueprint"]["nodes"]]
        assert types == ["Start", "Model", "Output"]
        assert "HumanApproval" not in types


def test_document_approval_pauses_then_persists(tmp_path: Path) -> None:
    transport = ScriptedRuntimeTransport(
        [
            _final({"result": {"title": "合同"}, "amount": 200000}),
            _final({"result": {"title": "合同"}, "amount": 200000}),
        ]
    )
    with _client(tmp_path, runtime=transport) as client:
        project_id = _project(client)
        session = _generate(client, project_id, DOCUMENT)
        assert session.get("product_shape") in {"WORKFLOW", "AGENT_WORKFLOW"}
        types = [node["component_type"] for node in session["blueprint"]["nodes"]]
        assert "Condition" in types
        assert "HumanApproval" in types
        applied = _apply(client, project_id, session)
        workflow = applied["workflow"]
        workflow_id = workflow["workflow_id"]
        url = f"/api/v1/projects/{project_id}/workflows/{workflow_id}"
        artifact = client.post(
            f"/api/v1/projects/{project_id}/artifacts",
            files={"file": ("contract.txt", b"amount 200000", "text/plain")},
        )
        assert artifact.status_code in {200, 201}, artifact.text
        record = artifact.json()
        started = client.post(
            f"{url}/run",
            json={
                "inputs": {
                    "contract": _ref(
                        str(record["artifact_id"]),
                        "contract.txt",
                        str(record.get("media_type") or "text/plain"),
                    ),
                    "message": "please extract",
                }
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        waiting = _await_workflow(client, url, started.json()["run_id"])
        assert waiting["status"] == "waiting", waiting
        decided = client.post(
            f"{url}/runs/{waiting['run_id']}/commands",
            json={"command": "approve"},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert decided.status_code == 200, decided.text
        settled = _await_workflow(client, url, waiting["run_id"])
        assert settled["status"] == "verified", settled
        assert len(transport.calls) == 1
        assert _started_counts(settled)["analyze"] == 1
    with sqlite3.connect(tmp_path / "app.sqlite3") as connection:
        records = connection.execute(
            "SELECT entity_id, project_id, entity_type, revision FROM entity_records"
        ).fetchall()
        assert [(row[1], row[2], row[3]) for row in records] == [
            (project_id, "ContractRecord", 1)
        ]
        assert connection.execute(
            "SELECT field, source FROM entity_events WHERE entity_id = ?",
            (records[0][0],),
        ).fetchall() == [("create", "tool")]


def test_workflow_state_write_then_read_uses_entity_store(tmp_path: Path) -> None:
    transport = ScriptedRuntimeTransport(
        _final({"result": {"title": "合同"}, "amount": 5})
    )
    with _client(tmp_path, runtime=transport) as client:
        project_id = _project(client)
        session = _generate(client, project_id, DOCUMENT)
        workflow_id = _apply(client, project_id, session)["workflow"]["workflow_id"]
        url = f"/api/v1/projects/{project_id}/workflows/{workflow_id}"
        draft = client.get(f"{url}/draft")
        source = draft.json()["source"]
        node_ids = [node["id"] for node in source["nodes"]]
        source["nodes"].insert(
            node_ids.index("verify"),
            {
                "id": "read_state",
                "component_type": "Tool",
                "uses": "veyra.tool.entity.read@1.0.0",
            },
        )
        for transition in source["transitions"]:
            if transition["from"] == "persist":
                transition["to"] = "read_state"
        source["transitions"].append(
            {"from": "read_state", "port": "next", "to": "verify"}
        )
        tools = client.get("/api/v1/resources", params={"kind": "tool"}).json()
        read_tool = next(
            item
            for item in tools["resources"]
            if item["resource_id"] == "veyra.tool.entity.read"
        )
        source["lock"][read_tool["reference"]] = read_tool["content_hash"]
        source["extensions"]["veyra"]["permissions"]["tools"].append(
            read_tool["resource_id"]
        )
        saved = client.patch(
            f"{url}/draft",
            json={"source": source, "expected_revision": draft.json()["revision"]},
            headers={"If-Match": draft.headers["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert saved.status_code == 200, saved.text
        committed = client.post(
            f"{url}/commit",
            json={"expected_revision": saved.json()["revision"]},
            headers={
                "If-Match": saved.json()["etag"],
                "Idempotency-Key": new_uuid7(),
            },
        )
        assert committed.status_code == 200, committed.text
        artifact = client.post(
            f"/api/v1/projects/{project_id}/artifacts",
            files={"file": ("contract.txt", b"amount 5", "text/plain")},
        ).json()
        started = client.post(
            f"{url}/run",
            json={
                "inputs": {
                    "contract": _ref(
                        str(artifact["artifact_id"]), "contract.txt", "text/plain"
                    ),
                    "message": "please extract",
                }
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        settled = _await_workflow(client, url, started.json()["run_id"])
        assert settled["status"] == "verified", settled
        assert settled["version_id"] == committed.json()["version_id"]
        completed = [
            event["node_id"]
            for event in settled["events"]
            if event["kind"] == "node.completed"
        ]
        assert completed.index("persist") < completed.index("read_state")
    with sqlite3.connect(tmp_path / "app.sqlite3") as connection:
        assert connection.execute(
            "SELECT project_id, entity_type, revision FROM entity_records"
        ).fetchall() == [(project_id, "ContractRecord", 1)]


def test_agentless_workflow_updates_and_reads_entity_revisions(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/workflows", json={"name": "Entity state"}
        )
        assert created.status_code == 201, created.text
        url = f"/api/v1/projects/{project_id}/workflows/{created.json()['workflow_id']}"
        draft = client.get(f"{url}/draft")
        source = draft.json()["source"]
        tools = {
            item["resource_id"]: item
            for item in client.get("/api/v1/resources", params={"kind": "tool"}).json()[
                "resources"
            ]
        }
        write = tools["veyra.tool.entity.write"]
        read = tools["veyra.tool.entity.read"]
        source["inputs"] = {"message": {"type": "string", "description": "Message"}}
        source["outputs"] = {
            "revision": {"type": "integer", "description": "Stored revision"},
            "status": {"type": "string", "description": "Stored status"},
        }
        source["nodes"] = [
            {"id": "start", "component_type": "Start"},
            {
                "id": "seed",
                "component_type": "Transform",
                "mapping": {"entity_type": "Ticket", "status": "draft"},
            },
            {"id": "write_first", "component_type": "Tool", "uses": write["reference"]},
            {
                "id": "bump",
                "component_type": "Transform",
                "mapping": {"status": "final"},
            },
            {
                "id": "write_second",
                "component_type": "Tool",
                "uses": write["reference"],
            },
            {"id": "read_back", "component_type": "Tool", "uses": read["reference"]},
            {"id": "output", "component_type": "Output", "output_name": "revision"},
        ]
        order = [node["id"] for node in source["nodes"]]
        source["transitions"] = [
            {"from": first, "port": "next", "to": second}
            for first, second in zip(order, order[1:], strict=False)
        ]
        source["lock"] = {
            write["reference"]: write["content_hash"],
            read["reference"]: read["content_hash"],
        }
        source["extensions"]["veyra"]["permissions"]["tools"] = [
            "veyra.tool.entity.write",
            "veyra.tool.entity.read",
        ]
        saved = client.patch(
            f"{url}/draft",
            json={"source": source, "expected_revision": draft.json()["revision"]},
            headers={"If-Match": draft.headers["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert saved.status_code == 200, saved.text
        committed = client.post(
            f"{url}/commit",
            json={"expected_revision": saved.json()["revision"]},
            headers={
                "If-Match": saved.json()["etag"],
                "Idempotency-Key": new_uuid7(),
            },
        )
        assert committed.status_code == 200, committed.text
        started = client.post(
            f"{url}/run",
            json={"inputs": {"message": "track this"}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        settled = _await_workflow(client, url, started.json()["run_id"])
        assert settled["status"] in {"verified", "unverified"}, settled
        assert settled["result"]["revision"] == 2
        assert settled["result"]["status"] == "final"
    with sqlite3.connect(tmp_path / "app.sqlite3") as connection:
        records = connection.execute(
            "SELECT entity_id, entity_type, status, revision FROM entity_records"
        ).fetchall()
        assert [row[1:] for row in records] == [("Ticket", "final", 2)]
        assert connection.execute(
            "SELECT field, source FROM entity_events WHERE entity_id = ? "
            "ORDER BY created_at",
            (records[0][0],),
        ).fetchall() == [("create", "tool"), ("payload", "tool")]


def test_secondhand_partial_flow_pauses_for_human_input(tmp_path: Path) -> None:
    transport = ScriptedRuntimeTransport(
        [
            _final(
                {
                    "model-known": False,
                    "result": {"title": "unknown item"},
                    "amount": 0,
                }
            ),
            _final({"result": {"price": 99}}),
            _final({"result": {"listing": "ok"}}),
        ]
    )
    with _client(tmp_path, runtime=transport) as client:
        project_id = _project(client)
        session = _generate(client, project_id, SECONDHAND)
        assert session.get("product_shape") == "MULTI_AGENT_WORKFLOW"
        types = [node["component_type"] for node in session["blueprint"]["nodes"]]
        assert types.count("AgentCall") >= 2
        assert "Condition" in types
        applied = _apply(client, project_id, session)
        workflow_id = applied["workflow"]["workflow_id"]
        url = f"/api/v1/projects/{project_id}/workflows/{workflow_id}"
        first = client.post(
            f"/api/v1/projects/{project_id}/artifacts",
            files={"file": ("a.png", _PNG, "image/png")},
        )
        second = client.post(
            f"/api/v1/projects/{project_id}/artifacts",
            files={"file": ("b.png", _PNG, "image/png")},
        )
        assert first.status_code in {200, 201}, first.text
        assert second.status_code in {200, 201}, second.text
        started = client.post(
            f"{url}/run",
            json={
                "inputs": {
                    "productimages": [
                        _ref(str(first.json()["artifact_id"]), "a.png", "image/png"),
                        _ref(str(second.json()["artifact_id"]), "b.png", "image/png"),
                    ],
                    "message": "整理这些商品",
                }
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        waiting = _await_workflow(client, url, started.json()["run_id"])
        assert waiting["status"] == "waiting", waiting
        assert waiting["waiting"]["kind"] == "input", waiting["waiting"]
        replied = client.post(
            f"{url}/runs/{waiting['run_id']}/commands",
            json={
                "command": "reply",
                "inputs": {waiting["waiting"]["expected_fields"][0]: "ABC-1"},
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert replied.status_code == 200, replied.text
        resumed = _await_workflow(client, url, waiting["run_id"])
        assert resumed["status"] in {"waiting", "verified", "unverified"}, resumed
        counts = _started_counts(resumed)
        assert counts[waiting["waiting"]["node_id"]] == 1
        first_call = next(
            event["node_id"]
            for event in resumed["events"]
            if event["kind"] == "node.started"
            and event["payload"].get("component_type") == "AgentCall"
        )
        assert counts[first_call] == 1
        assert counts["start"] == 1
