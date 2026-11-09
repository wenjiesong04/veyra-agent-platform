"""Canonical Chat-created Workflows bind companion Skills before commit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.unit.local.test_approval_control_routing import approval_task
from veyra_agent_platform.contracts.task_structure import TaskStructure
from veyra_agent_platform.local.builder.task_planner import normalize_task_structure
from veyra_agent_platform.local.builder.task_structure_schema import (
    task_structure_payload,
)
from veyra_agent_platform.local.projects.service import ProjectError

from .test_builder_conversations import _turn
from .test_builder_resolution import intent
from .test_factory_routes import (
    _client,
    _completion,
    _project,
    _provider_projection,
)
from .test_factory_task_structure_planner import PlanningTransport

SKILLS = (
    "veyra.skill.document-analyzer@1.0.0",
    "veyra.skill.evidence-ledger@1.0.0",
)
GOAL = (
    "Create one analysis and independent review Workflow. Both roles read the "
    "original material; the reviewer also reads the analysis. Use Document "
    "Analyzer for analysis and Evidence Ledger for independent review. "
    "Deliver only after human approval; rejection stops without delivery. "
    "Do not use network, files, or images."
)


@pytest.fixture(autouse=True)
def isolate_factory_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "MOONSHOT_API_KEY",
        "VEYRA_FACTORY_MODEL_BASE_URL",
        "VEYRA_FACTORY_MODEL_ID",
    ):
        monkeypatch.delenv(name, raising=False)


def _transport() -> PlanningTransport:
    task = approval_task()
    task.update(
        goal=GOAL, user_requested_surface="workflow", user_shape_override="WORKFLOW"
    )
    task["actors"][0]["capabilities"].append("document_analysis")
    task["actors"][1]["capabilities"].append("evidence_synthesis")
    task["skill_choices"] = [
        {
            "actor": actor,
            "capability": capability,
            "reference": reference,
            "reason": "Use the requested traceable analysis method",
        }
        for actor, capability, reference in (
            ("analyst", "document_analysis", SKILLS[0]),
            ("reviewer", "evidence_synthesis", SKILLS[1]),
        )
    ]
    payload = _provider_projection(
        normalize_task_structure(
            TaskStructure.from_dict(task_structure_payload(task))
        ).to_dict()
    )
    return PlanningTransport(
        [
            _completion(
                json.dumps(
                    intent(
                        intent="create",
                        create_kind="workflow",
                        creation_scope="single_product",
                        multi_object=True,
                        instruction=GOAL,
                    )
                )
            ),
            _completion(json.dumps(payload)),
            _completion(json.dumps(payload)),
            _completion(json.dumps({"verdict": "covered", "gaps": []})),
        ]
    )


def _resources(client: TestClient, project: str) -> list[dict[str, Any]]:
    return [
        item
        for item in client.get(f"/api/v1/projects/{project}/resources").json()[
            "resources"
        ]
        if item.get("scope") == "project"
    ]


def _assert_empty(client: TestClient, project: str) -> None:
    summary = client.get(f"/api/v1/projects/{project}").json()
    assert summary["agents"] == []
    assert summary["workflows"] == []


def _propose(
    client: TestClient, project: str, transport: PlanningTransport
) -> tuple[dict[str, Any], dict[str, Any], str]:
    assert _resources(client, project) == []
    _assert_empty(client, project)
    response = _turn(client, project, content=GOAL)
    assert response.status_code == 200, response.text
    snapshot = response.json()
    operation = snapshot["operations"][-1]
    assert operation["kind"] == "create_workflow"
    assert operation["status"] == "waiting", snapshot
    proposal = client.get(
        f"/api/v1/projects/{project}/edit-proposals/{operation['proposal_id']}"
    ).json()
    assert proposal["proposal_kind"] == "create_workflow"
    assert proposal["state"] == "review"
    assert len(proposal["candidate_companions"]) == 2
    assert {
        reference
        for companion in proposal["candidate_companions"]
        for reference in companion["extensions"]["veyra"]["skill_refs"]
    } == set(SKILLS)
    assert [receipt["output_contract"] for receipt in operation["receipts"]][
        -1
    ] == "TaskCoverageV1"
    assert len(transport.calls) == 4
    assert transport.responses == []
    assert _resources(client, project) == []
    _assert_empty(client, project)
    url = (
        f"/api/v1/projects/{project}/builder/conversations/{snapshot['conversation']['conversation_id']}"
        f"/operations/{operation['operation_id']}/agent-proposals/{proposal['proposal_id']}/commands"
    )
    return snapshot, proposal, url


def _apply(client: TestClient, url: str) -> dict[str, Any]:
    response = client.post(
        url, json={"command": "apply", "confirm": True, "locale": "en"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _assert_installed(
    client: TestClient, project: str, proposal: dict[str, Any]
) -> dict[str, Any]:
    summary = client.get(f"/api/v1/projects/{project}").json()
    assert len(summary["agents"]) == 2
    assert len(summary["workflows"]) == 1
    pinned = {
        item["reference"]: item["bound_content_hash"]
        for item in _resources(client, project)
    }
    assert set(pinned) == set(SKILLS)
    expected = {item["agent_id"]: item for item in proposal["candidate_companions"]}
    committed: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for agent in summary["agents"]:
        agent_id = agent["agent_id"]
        versions = client.get(
            f"/api/v1/projects/{project}/agents/{agent_id}/versions"
        ).json()["versions"]
        assert len(versions) == 1
        committed[agent_id] = versions[0]["version_id"]
        hashes[agent_id] = versions[0]["source_hash"]
        source = client.get(
            f"/api/v1/projects/{project}/agents/{agent_id}/draft"
        ).json()["source"]
        assert source == expected[agent_id]
        for reference in source["extensions"]["veyra"]["skill_refs"]:
            assert source["lock"][reference] == pinned[reference]
    workflow_id = summary["workflows"][0]["workflow_id"]
    workflow = client.get(
        f"/api/v1/projects/{project}/workflows/{workflow_id}/draft"
    ).json()["source"]
    calls = [
        node for node in workflow["nodes"] if node["component_type"] == "AgentCall"
    ]
    assert len(calls) == 2
    for call in calls:
        agent_id, version_id = call["agent_ref"].split("@", 1)
        assert version_id == committed[agent_id]
        assert workflow["lock"][call["agent_ref"]] == hashes[agent_id]
    return summary


def test_canonical_workflow_apply_binds_unbound_skills_before_companion_commit(
    tmp_path: Path,
) -> None:
    transport = _transport()
    with _client(tmp_path, transport) as client:
        project = _project(client)
        _, proposal, url = _propose(client, project, transport)
        applied = _apply(client, url)
        assert applied["operations"][-1]["status"] == "succeeded", applied
        installed = _assert_installed(client, project, proposal)
        assert len(transport.calls) == 4
        repeated = _apply(client, url)
        assert repeated["operations"][-1]["status"] == "succeeded"
        assert client.get(f"/api/v1/projects/{project}").json() == installed
        assert len(transport.calls) == 4


@pytest.mark.parametrize("decision,confirm", [("apply", False), ("reject", True)])
def test_unconfirmed_or_rejected_workflow_never_binds_skills(
    tmp_path: Path, decision: str, confirm: bool
) -> None:
    transport = _transport()
    with _client(tmp_path, transport) as client:
        project = _project(client)
        _, proposal, url = _propose(client, project, transport)
        response = client.post(
            url, json={"command": decision, "confirm": confirm, "locale": "en"}
        )
        assert response.status_code == (422 if not confirm else 200), response.text
        assert _resources(client, project) == []
        _assert_empty(client, project)
        stored = client.get(
            f"/api/v1/projects/{project}/edit-proposals/{proposal['proposal_id']}"
        ).json()
        assert stored["state"] == ("review" if not confirm else "rejected")
        assert len(transport.calls) == 4


def test_skill_drift_never_upgrades_or_creates_partial_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = _transport()
    with _client(tmp_path, transport) as client:
        project = _project(client)
        _, proposal, url = _propose(client, project, transport)
        catalog = client.app.state.resource_catalog
        original = catalog.by_reference

        def changed(reference: str):
            resource = original(reference)
            return (
                {**resource, "content_hash": "f" * 64}
                if reference == SKILLS[0]
                else resource
            )

        monkeypatch.setattr(catalog, "by_reference", changed)
        failed = _apply(client, url)
        assert failed["operations"][-1]["status"] == "failed", failed
        assert failed["operations"][-1]["error_code"] == "resource_identity_conflict"
        _assert_empty(client, project)
        assert _resources(client, project) == []
        stored = client.get(
            f"/api/v1/projects/{project}/edit-proposals/{proposal['proposal_id']}"
        ).json()
        assert stored["candidate_companions"] == proposal["candidate_companions"]
        assert stored["state"] == "review"
        assert len(transport.calls) == 4


def test_companion_commit_failure_reapplies_without_provider_or_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = _transport()
    with _client(tmp_path, transport) as client:
        project = _project(client)
        _, proposal, url = _propose(client, project, transport)
        library = client.app.state.library
        commit = library.commit
        attempts = 0

        def fail_once(**kwargs: Any):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ProjectError(
                    "Controlled first companion commit failure", code="resource_unbound"
                )
            return commit(**kwargs)

        monkeypatch.setattr(library, "commit", fail_once)
        failed = _apply(client, url)
        assert failed["operations"][-1]["status"] == "failed", failed
        assert failed["operations"][-1]["error_code"] == "resource_unbound"
        _assert_empty(client, project)
        stored = client.get(
            f"/api/v1/projects/{project}/edit-proposals/{proposal['proposal_id']}"
        ).json()
        assert stored["state"] == "review"
        assert stored["candidate_companions"] == proposal["candidate_companions"]
        failure_events = {
            event["event_id"]
            for event in failed["operations"][-1]["events"]
            if event["kind"] == "builder.operation.failed"
        }
        assert failure_events
        recovered = _apply(client, url)
        assert recovered["operations"][-1]["status"] == "succeeded", recovered
        assert failure_events <= {
            event["event_id"] for event in recovered["operations"][-1]["events"]
        }
        installed = _assert_installed(client, project, proposal)
        assert attempts == 3
        replay = _apply(client, url)
        assert replay["operations"][-1]["status"] == "succeeded"
        assert client.get(f"/api/v1/projects/{project}").json() == installed
        assert attempts == 3
        assert len(transport.calls) == 4
