from __future__ import annotations

import json
from pathlib import Path

from tests.unit.local.test_semantic_composition import Planner, design_plan
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.builder.composite_apply import apply_composite
from veyra_agent_platform.local.builder.generate_product import generate_builder_product
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.resources import ResourceCatalog

from .test_runtime_routes import ScriptedRuntimeTransport
from .test_workflow_version_boundary import await_workflow
from .verified_runtime_model import verified_client


def test_generated_roles_pass_analysis_and_validated_selection_to_delivery(
    tmp_path: Path,
) -> None:
    plan = design_plan()
    plan["inputs"][0]["type"] = "string"
    plan["actors"][0]["inputs"][0]["type"] = "string"
    plan["actors"][0]["capabilities"] = ["text_generation"]
    plan["actors"][1]["capabilities"] = ["text_generation"]
    plan["actors"][1]["outputs"] = [
        item for item in plan["actors"][1]["outputs"] if item["name"] == "result"
    ]
    plan["outputs"] = [item for item in plan["outputs"] if item["name"] == "result"]
    plan["execution_boundaries"][0]["kind"] = "reasoning"
    plan["execution_boundaries"][2] = {
        "kind": "reasoning",
        "stage": "render",
        "reason": "Deliver selected option",
    }
    requirement = (
        "Create three proposals, wait for my choice, "
        "then deliver only that option within the stated constraints."
    )
    transport = ScriptedRuntimeTransport(
        [
            json.dumps(
                {
                    "action": "final",
                    "outputs": {"options": {"choices": ["A", "OPTION_B_DATA", "C"]}},
                }
            ),
            json.dumps(
                {
                    "action": "final",
                    "outputs": {"result": {"chosen": "B", "analysis": "OPTION_B_DATA"}},
                }
            ),
        ]
    )
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'db.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with verified_client(settings, transport) as client:
        pid = client.post("/api/v1/projects", json={"name": "Typed handoff"}).json()[
            "project_id"
        ]
        product = generate_builder_product(
            requirement, ResourceCatalog(), planner_provider=Planner(plan)
        )
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
                "inputs": {"image": "Fixture brief"},
                "source": "committed",
                "version_id": committed.json()["version_id"],
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        rid = started.json()["run_id"]
        waiting = await_workflow(client, url, rid)
        assert waiting["status"] == "waiting", waiting
        assert len(transport.calls) == 1
        assert len(waiting["children"]) == 1
        field = waiting["waiting"]["expected_fields"][0]
        commands = f"{url}/runs/{rid}/commands"
        for payload in [
            {"command": "approve"},
            {"command": "reply", "inputs": {}},
            {"command": "reply", "inputs": {field: 3}},
            {"command": "reply", "inputs": {field: "B", "unknown": "injected"}},
        ]:
            rejected = client.post(
                commands, json=payload, headers={"Idempotency-Key": new_uuid7()}
            )
            assert rejected.status_code >= 400, rejected.text
            assert len(transport.calls) == 1
        resumed = client.post(
            commands,
            json={"command": "reply", "inputs": {field: "B"}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert resumed.status_code == 200, resumed.text
        finished = await_workflow(client, url, rid)
        assert finished["status"] == "verified", finished
        assert finished["result"]["result"] == {
            "chosen": "B",
            "analysis": "OPTION_B_DATA",
        }
        assert len(transport.calls) == 2
        assert "OPTION_B_DATA" in json.dumps(transport.calls[1], ensure_ascii=False)
        assert any(
            "selection: B" in str(message.get("content", ""))
            for message in transport.calls[1]
        )
