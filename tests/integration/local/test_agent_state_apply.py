from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.integration.local.test_factory_routes import _client, _project
from tests.integration.local.test_runtime_routes import (
    ScriptedRuntimeTransport,
    _await_run,
)
from tests.integration.local.verified_runtime_model import verified_client
from tests.unit.local.test_semantic_composition import Planner, field
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.builder.generate_product import generate_builder_product
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.factory.service import FactoryError
from veyra_agent_platform.local.resources import ResourceCatalog


def _product() -> Any:
    requirement = "保存任务，下次先找到同一任务再更新，不能重复创建，周总结前先问我。"
    payload = {
        "schema_version": "1.0",
        "goal": "Manage retained tasks",
        "summary": requirement,
        "actors": [
            {
                "id": "manager",
                "role": "任务管理助手",
                "capabilities": ["text_generation", "entity_read", "entity_write"],
            }
        ],
        "stages": [{"id": "manage", "actor": "manager", "summary": requirement}],
        "inputs": [field("request", "string")],
        "outputs": [field("result", "object")],
        "execution_boundaries": [],
        "uncertainty": [],
        "lifecycle": {"persistent": True, "interaction": "persistent_task"},
        "state": {
            "entity": "tasks",
            "identity": "title",
            "scope": "project",
            "fields": {"title": "string", "owner": "string", "status": "string"},
            "statuses": ["open", "done"],
            "revision": True,
        },
    }
    product = generate_builder_product(
        requirement, ResourceCatalog(), planner_provider=Planner(payload)
    )
    assert product.status == "review", product.diagnostics
    assert product.source is not None and product.source.is_loop
    assert "veyra.tool.entity.query" in product.source.permissions.tools
    assert "Persistent state contract" in product.source.instructions
    return product


def test_reviewed_agent_state_contract_is_installed_once_and_conflicts_fail_closed(
    tmp_path: Path,
) -> None:
    product = _product()
    with _client(tmp_path) as client:
        pid = _project(client)
        edits = client.app.state.edit_proposals
        store = client.app.state.entity_store
        proposal = edits.create_agent_proposal(
            pid,
            candidate={
                "source": product.source.to_dict(),
                "execution_plan": product.plan.to_dict(),
            },
            conversation_id="state-test-conversation",
            operation_id="state-test-operation",
            factory_session_id="state-test-factory",
        )
        assert store.read_type_schema(pid, "tasks") is None
        applied = edits.apply_agent_creation_proposal(
            pid, proposal["proposal_id"], confirm=True
        )
        assert applied["state"] == "applied"
        assert store.read_type_schema(pid, "tasks") == product.plan.state.to_dict()
        replay = edits.apply_agent_creation_proposal(
            pid, proposal["proposal_id"], confirm=True
        )
        assert replay["state"] == "applied"
        assert len(client.app.state.projects.project_summary(pid)["agents"]) == 1

        other = _project(client)
        existing = {"entity": "tasks", "fields": {"unrelated": "number"}}
        store.define_type(other, "tasks", existing)
        conflict = edits.create_agent_proposal(
            other,
            candidate={
                "source": product.source.to_dict(),
                "execution_plan": product.plan.to_dict(),
            },
            conversation_id="state-test-other",
            operation_id="state-test-operation-other",
            factory_session_id="state-test-factory-other",
        )
        with pytest.raises(FactoryError, match="conflicts"):
            edits.apply_agent_creation_proposal(
                other, conflict["proposal_id"], confirm=True
            )
        assert not client.app.state.projects.project_summary(other)["agents"]
        assert store.read_type_schema(other, "tasks") == existing


def test_state_scope_rejection_is_repaired_before_write_and_query_finds_the_record(
    tmp_path: Path,
) -> None:
    product = _product()
    transport = ScriptedRuntimeTransport(
        [
            json.dumps(
                {
                    "action": "tool",
                    "tool": "veyra.tool.entity.write@1.0.0",
                    "arguments": {
                        "entity_type": "OtherType",
                        "payload": {"title": "海报"},
                        "status": "open",
                    },
                }
            ),
            json.dumps(
                {
                    "action": "tool",
                    "tool": "veyra.tool.entity.query@1.0.0",
                    "arguments": {"entity_type": "tasks", "filters": {"title": "海报"}},
                }
            ),
            json.dumps(
                {
                    "action": "tool",
                    "tool": "veyra.tool.entity.write@1.0.0",
                    "arguments": {
                        "entity_type": "tasks",
                        "payload": {"title": "海报", "owner": "小夏", "status": "open"},
                        "status": "open",
                    },
                }
            ),
            json.dumps({"action": "final", "outputs": {"result": {"saved": True}}}),
        ]
    )
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'db.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with verified_client(settings, transport) as client:
        pid = _project(client)
        edits = client.app.state.edit_proposals
        proposal = edits.create_agent_proposal(
            pid,
            candidate={"source": product.source.to_dict()},
            conversation_id="guard-conversation",
            operation_id="guard-operation",
            factory_session_id="guard-factory",
        )
        edits.apply_agent_creation_proposal(pid, proposal["proposal_id"], confirm=True)
        aid = product.source.agent_id
        url = f"/api/v1/projects/{pid}/agents/{aid}"
        draft = client.get(url + "/draft").json()
        response = client.post(
            url + "/commit",
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
            json={"expected_revision": draft["revision"]},
        )
        assert response.status_code == 200, response.text
        committed = response.json()
        started = client.post(
            url + "/run",
            json={
                "inputs": {"request": "记录海报任务"},
                "source": "committed",
                "version_id": committed["version_id"],
            },
            headers={"Idempotency-Key": new_uuid7()},
        ).json()
        run = _await_run(client, url + "/run", started["run_id"])
        assert run["status"] in {"verified", "unverified"}, run.get("error")
        rejected = [e for e in run["events"] if e["kind"] == "tool.input_rejected"]
        assert len(rejected) == 1 and rejected[0]["payload"]["effect_started"] is False
        store = client.app.state.entity_store
        assert not store.query(project_id=pid, entity_type="OtherType")["records"]
        rows = store.query(
            project_id=pid, entity_type="tasks", filters={"title": "海报"}
        )["records"]
        assert len(rows) == 1 and rows[0]["data"]["owner"] == "小夏"
        assert rows[0]["revision"] == 1
