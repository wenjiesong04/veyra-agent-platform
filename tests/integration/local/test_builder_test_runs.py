"""Builder Phase 2 Slice 4: explicit Test Run → Observe → Repair."""

from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.integration.local.test_builder_conversations import InspectingTransport
from tests.integration.local.test_builder_resource_binding import _bind_read
from tests.integration.local.test_runtime_routes import (
    ScriptedRuntimeTransport,
    _agent_source,
    _source,
    _write_source,
)
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.runtime.client import RuntimeProviderError

REFERENCE = "veyra.tool.filesystem.read@1.0.0"


def _client(
    tmp_path: Path,
    *,
    factory_transport: Any | None = None,
    runtime_transport: Any | None = None,
) -> TestClient:
    return TestClient(
        create_app(
            LocalSettings(
                database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
                project_storage_root=tmp_path / "projects",
            ),
            factory_transport=factory_transport,
            runtime_transport=runtime_transport,
        )
    )


def _transform_source() -> dict[str, object]:
    source = _source(
        [
            {"id": "start", "component_type": "Start"},
            {
                "id": "transform",
                "component_type": "Transform",
                "mapping": {"result": "你好，{{text}}"},
            },
            {"id": "output", "component_type": "Output", "output_name": "result"},
        ],
        [
            {"from": "start", "port": "next", "to": "transform"},
            {"from": "transform", "port": "next", "to": "output"},
        ],
        {"text": "string"},
    )
    source["outputs"] = {"result": "string"}
    return source


def _permission_source(client: TestClient, *, allow: bool) -> dict[str, object]:
    resource = client.app.state.resource_catalog.by_reference(REFERENCE)
    source = _source(
        [
            {"id": "start", "component_type": "Start"},
            {"id": "read", "component_type": "Tool", "uses": REFERENCE},
            {"id": "output", "component_type": "Output", "output_name": "content"},
        ],
        [
            {"from": "start", "port": "next", "to": "read"},
            {"from": "read", "port": "next", "to": "output"},
        ],
        {"path": "string"},
    )
    source["outputs"] = {"content": "string"}
    permissions = deepcopy(resource["required_permissions"])
    if not allow:
        permissions["filesystem_read_roots"] = []
    source["extensions"]["veyra"]["permissions"] = permissions
    source["lock"] = {REFERENCE: resource["content_hash"]}
    return source


def _create_agent(client: TestClient, source: dict[str, object]) -> tuple[str, str]:
    created = client.post("/api/v1/projects", json={"agents": [source]})
    assert created.status_code == 201, created.text
    project = created.json()
    return project["project_id"], project["agents"][0]["agent_id"]


def _conversation(client: TestClient, project_id: str) -> str:
    response = client.post(
        f"/api/v1/projects/{project_id}/builder/turns",
        json={"content": "keep this conversation", "locale": "en", "focus": None},
    )
    assert response.status_code == 200, response.text
    return response.json()["conversation"]["conversation_id"]


def _test_run(
    client: TestClient,
    project_id: str,
    conversation_id: str,
    agent_id: str,
    inputs: dict[str, object],
    locale: str = "en",
    workspace_id: str | None = None,
) -> dict[str, Any]:
    body: dict[str, object] = {"agent_id": agent_id, "inputs": inputs, "locale": locale}
    if workspace_id is not None:
        body["workspace_id"] = workspace_id
    response = client.post(
        f"/api/v1/projects/{project_id}/builder/conversations/{conversation_id}/test-runs",
        json=body,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _await_test(
    client: TestClient,
    project_id: str,
    conversation_id: str,
    *,
    timeout: float = 8,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    payload: dict[str, Any] = {}
    while time.monotonic() < deadline:
        payload = client.get(
            f"/api/v1/projects/{project_id}/builder/conversations/{conversation_id}"
        ).json()
        operation = _test_op(payload)
        if operation and operation["status"] not in {"in_progress"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"test operation stayed in progress: {payload}")


def _test_op(payload: dict[str, Any]) -> dict[str, Any]:
    operations = [
        item for item in payload.get("operations") or [] if item["kind"] == "test_agent"
    ]
    assert operations, payload
    return operations[-1]


def _runs(client: TestClient, project_id: str, agent_id: str) -> list[dict[str, Any]]:
    return client.get(f"/api/v1/projects/{project_id}/agents/{agent_id}/runs").json()[
        "runs"
    ]


def test_explicit_test_required_and_canonical_run_linked(tmp_path: Path) -> None:
    factory = InspectingTransport([])
    with _client(tmp_path, factory_transport=factory) as client:
        factory.client = client
        project_id, agent_id = _create_agent(client, _transform_source())
        conversation_id = _conversation(client, project_id)
        assert _runs(client, project_id, agent_id) == []
        started = _test_run(
            client,
            project_id,
            conversation_id,
            agent_id,
            {"text": "世界"},
            workspace_id="workspace-card-1",
        )
        operation = _test_op(started)
        assert operation["kind"] == "test_agent"
        assert operation["workspace_id"] == "workspace-card-1"
        assert operation["run_id"]
        snapshot = _await_test(client, project_id, conversation_id)
        operation = _test_op(snapshot)
        observation = operation["run_observation"]
        assert operation["status"] == "succeeded"
        assert observation["status"] in {"verified", "unverified"}
        assert observation["run_id"] == operation["run_id"]
        assert observation["version_id"]
        assert "你好" in str(observation["output_summary"])
        runs = _runs(client, project_id, agent_id)
        assert [item["run_id"] for item in runs] == [operation["run_id"]]
        detail = client.get(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/runs/{operation['run_id']}"
        ).json()
        assert detail["version_id"] == observation["version_id"]
        assert detail["run_id"] == operation["run_id"]
        kinds = [event["kind"] for event in operation["events"]]
        assert "run.created" not in kinds
        assert "builder.test_run.started" in kinds
        assert "builder.test_run.completed" in kinds
        messages = [item["kind"] for item in snapshot["messages"]]
        assert "user" in messages
        assert not any(
            "run.created" in json.dumps(item, ensure_ascii=False)
            for item in snapshot["messages"]
        )
        receipts = client.get(
            f"/api/v1/projects/{project_id}/builder/conversations/{conversation_id}"
            f"/operations/{operation['operation_id']}/receipts"
        ).json()
        assert receipts["receipts"] == []
        refreshed = client.get(
            f"/api/v1/projects/{project_id}/builder/conversations/{conversation_id}"
        ).json()
        assert _test_op(refreshed)["run_id"] == operation["run_id"]
        assert _test_op(refreshed)["workspace_id"] == "workspace-card-1"
        assert _test_op(refreshed)["status"] == "succeeded"


def test_no_automatic_run_after_apply_and_repair(tmp_path: Path) -> None:
    factory = InspectingTransport([])
    with _client(tmp_path, factory_transport=factory) as client:
        factory.client = client
        source = _permission_source(client, allow=False)
        project_id, agent_id = _create_agent(client, source)
        _bind_read(client, project_id)
        conversation_id = _conversation(client, project_id)
        _test_run(
            client,
            project_id,
            conversation_id,
            agent_id,
            {"path": "resources/readme.md"},
            locale="zh",
        )
        snapshot = _await_test(client, project_id, conversation_id)
        operation = _test_op(snapshot)
        observation = operation["run_observation"]
        assert operation["status"] == "failed"
        assert observation["failure_code"] == "tool_permission_denied"
        assert observation["classification"] == "repairable"
        assert "权限" in observation["explanation"]
        before = len(_runs(client, project_id, agent_id))
        repaired = client.post(
            f"/api/v1/projects/{project_id}/builder/conversations/{conversation_id}"
            f"/operations/{operation['operation_id']}/test-repair",
            json={"locale": "zh"},
        )
        assert repaired.status_code == 200, repaired.text
        proposal_id = _test_op(repaired.json())["proposal_id"]
        assert proposal_id
        listed = client.get(
            f"/api/v1/projects/{project_id}/edit-proposals",
            params={"target_kind": "agent", "target_id": agent_id},
        ).json()["proposals"]
        assert listed[0]["proposal_id"] == proposal_id
        assert listed[0]["state"] == "review"
        applied = client.post(
            f"/api/v1/projects/{project_id}/edit-proposals/{proposal_id}/commands",
            json={"command": "apply", "confirm": True},
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["state"] == "applied"
        validated = client.post(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/validate"
        )
        assert validated.status_code == 200
        assert len(_runs(client, project_id, agent_id)) == before
        after = client.get(
            f"/api/v1/projects/{project_id}/builder/conversations/{conversation_id}"
        ).json()
        assert _test_op(after)["run_id"] == operation["run_id"]
        assert _test_op(after)["status"] == "failed"


def test_runtime_not_configured_does_not_bind_builder_model(tmp_path: Path) -> None:
    factory = InspectingTransport([])
    with _client(tmp_path, factory_transport=factory) as client:
        factory.client = client
        project_id, agent_id = _create_agent(client, _agent_source())
        conversation_id = _conversation(client, project_id)
        snapshot = _test_run(
            client, project_id, conversation_id, agent_id, {"request": "Hello"}
        )
        operation = _test_op(snapshot)
        observation = operation["run_observation"]
        assert operation["run_id"] is None
        assert operation["status"] == "failed"
        assert operation["error_code"] == "runtime_not_configured"
        assert observation["failure_code"] == "runtime_not_configured"
        assert observation["classification"] == "user_action"
        assert observation["next_action"] == "open_runtime_settings"
        assert _runs(client, project_id, agent_id) == []
        assert (
            "Kimi" in observation["explanation"]
            or "运行模型" in observation["explanation"]
        )


def test_resource_readiness_and_knowledge_stale_observations(tmp_path: Path) -> None:
    factory = InspectingTransport([])
    runtime = ScriptedRuntimeTransport("must not run")
    with _client(
        tmp_path, factory_transport=factory, runtime_transport=runtime
    ) as client:
        factory.client = client
        project_id, agent_id = _create_agent(client, _agent_source())
        conversation_id = _conversation(client, project_id)
        knowledge = client.post(
            f"/api/v1/projects/{project_id}/knowledge",
            json={"text": "The acceptance marker is ORBIT-731."},
        ).json()
        detail = f"/api/v1/projects/{project_id}/knowledge/{knowledge['knowledge_id']}"
        assert client.post(f"{detail}/index").status_code == 200
        changed = client.patch(detail, json={"text": "CHANGED"}).json()
        draft = client.get(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/draft"
        ).json()
        source = draft["source"]
        ref = f"{changed['knowledge_id']}@{changed['version']}"
        source["extensions"]["veyra"]["knowledge_refs"] = [ref]
        source["lock"][ref] = changed["source_file_hash"]
        saved = client.patch(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/draft",
            json={"source": source, "expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert saved.status_code == 200, saved.text
        _test_run(client, project_id, conversation_id, agent_id, {"request": "marker"})
        snapshot = _await_test(client, project_id, conversation_id)
        observation = _test_op(snapshot)["run_observation"]
        assert observation["failure_code"] == "knowledge_index_stale"
        assert observation["classification"] == "user_action"
        assert observation["knowledge_failure"]
        assert runtime.calls == []

        unbound = _permission_source(client, allow=True)
        project_u, agent_u = _create_agent(client, unbound)
        conv_u = _conversation(client, project_u)
        _test_run(client, project_u, conv_u, agent_u, {"path": "resources/a.txt"})
        snapshot = _await_test(client, project_u, conv_u)
        observation = _test_op(snapshot)["run_observation"]
        assert observation["failure_code"] == "resource_unbound"
        assert observation["classification"] == "user_action"
        repaired = client.post(
            f"/api/v1/projects/{project_u}/builder/conversations/{conv_u}"
            f"/operations/{_test_op(snapshot)['operation_id']}/test-repair",
            json={"locale": "en"},
        )
        assert repaired.status_code == 422
        assert repaired.json()["code"] == "builder_test_not_repairable"


def test_approval_stop_and_runtime_429_stay_in_runtime_domain(
    tmp_path: Path,
) -> None:
    factory = InspectingTransport([])
    with _client(tmp_path, factory_transport=factory) as client:
        factory.client = client
        source = _write_source(client)
        project_id, agent_id = _create_agent(client, source)
        client.app.state.project_resources.add(
            project_id, "veyra.tool.filesystem.write@1.0.0"
        )
        conversation_id = _conversation(client, project_id)
        _test_run(
            client,
            project_id,
            conversation_id,
            agent_id,
            {"path": "resources/out.txt", "content": "saved"},
        )
        snapshot = _await_test(client, project_id, conversation_id)
        operation = _test_op(snapshot)
        assert operation["status"] == "waiting"
        assert operation["run_observation"]["approval_required"] is True
        assert operation["run_observation"]["classification"] == "none"
        assert operation["error_code"] is None
        stopped = client.post(
            f"/api/v1/projects/{project_id}/builder/conversations/{conversation_id}"
            f"/operations/{operation['operation_id']}/test-commands",
            json={"command": "stop", "locale": "en"},
        )
        assert stopped.status_code == 200, stopped.text
        snapshot = _await_test(client, project_id, conversation_id)
        operation = _test_op(snapshot)
        assert operation["status"] == "succeeded"
        kinds = [event["kind"] for event in operation["events"]]
        assert "builder.test_run.stopped" in kinds
        assert "builder.operation.failed" not in kinds
        assert operation["run_observation"]["status"] == "cancelled"

    factory = InspectingTransport([])
    runtime = _RateLimitedTransport()
    rate_root = tmp_path / "rate"
    rate_root.mkdir()
    with _client(
        rate_root, factory_transport=factory, runtime_transport=runtime
    ) as client:
        factory.client = client
        before_profile = client.get("/api/v1/factory/status").json()[
            "capability_profile"
        ]
        project_id, agent_id = _create_agent(client, _agent_source())
        conversation_id = _conversation(client, project_id)
        _test_run(client, project_id, conversation_id, agent_id, {"request": "Hello"})
        snapshot = _await_test(client, project_id, conversation_id)
        operation = _test_op(snapshot)
        assert operation["run_observation"]["failure_code"] == "runtime_rate_limited"
        assert operation["run_observation"]["classification"] == "environment"
        receipts = client.get(
            f"/api/v1/projects/{project_id}/builder/conversations/{conversation_id}"
            f"/operations/{operation['operation_id']}/receipts"
        ).json()["receipts"]
        assert receipts == []
        after_profile = client.get("/api/v1/factory/status").json()[
            "capability_profile"
        ]
        assert after_profile == before_profile


def test_cross_project_agent_cannot_start_test_run(tmp_path: Path) -> None:
    factory = InspectingTransport([])
    with _client(tmp_path, factory_transport=factory) as client:
        factory.client = client
        project_a, _agent_a = _create_agent(client, _transform_source())
        project_b, agent_b = _create_agent(client, _transform_source())
        conversation_a = _conversation(client, project_a)
        response = client.post(
            f"/api/v1/projects/{project_a}/builder/conversations/{conversation_a}/test-runs",
            json={"agent_id": agent_b, "inputs": {"text": "no"}, "locale": "en"},
        )
        assert response.status_code in {404, 422}
        assert _runs(client, project_b, agent_b) == []


class _RateLimitedTransport:
    def models(self) -> tuple[str, ...]:
        return ("kimi-k3",)

    def complete(self, messages: object) -> Any:
        del messages
        raise RuntimeProviderError(
            "runtime_rate_limited", "Runtime model service is rate limited"
        )
