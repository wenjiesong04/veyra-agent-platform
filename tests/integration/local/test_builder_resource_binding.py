"""Builder Phase 2 Slice 2: deterministic Project-owned Resource binding."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.local.test_edit_proposal_routes import _command, _target
from tests.integration.local.test_factory_routes import ScriptedKimiTransport, _client
from veyra_agent_platform.local.builder.resource_binding import resource_readiness

REFERENCE = "veyra.tool.filesystem.read@1.0.0"


def _bind_read(client: TestClient, project_id: str) -> dict[str, Any]:
    descriptor = client.get(
        "/api/v1/resources/veyra.tool.filesystem.read/versions/1.0.0"
    ).json()
    response = client.post(
        f"/api/v1/projects/{project_id}/resources",
        json={
            "reference": descriptor["reference"],
            "content_hash": descriptor["content_hash"],
        },
    )
    assert response.status_code == 201, response.text
    return next(
        resource
        for resource in response.json()["resources"]
        if resource.get("scope") == "project"
        and resource["reference"] == descriptor["reference"]
    )


def _propose(
    client: TestClient,
    project_id: str,
    agent_id: str,
    draft: dict[str, Any],
    instruction: str = "让这个 Agent 可以读取项目文件。",
):
    return client.post(
        f"/api/v1/projects/{project_id}/edit-proposals/resource-binding",
        json={
            "agent_id": agent_id,
            "instruction": instruction,
            "expected_revision": draft["revision"],
            "expected_etag": draft["etag"],
        },
    )


@pytest.mark.parametrize(
    ("binding_status", "availability", "runtime_status", "expected"),
    [
        ("current", "ready", "supported", "ready"),
        (
            "current",
            "requires_configuration",
            "runtime_not_configured",
            "requires_configuration",
        ),
        ("current", "design_only", "runtime_not_supported", "design_only"),
        ("current", "unavailable", "runtime_not_configured", "unavailable"),
        ("current", "quarantined", "runtime_not_supported", "quarantined"),
        ("current", "unavailable", "runtime_not_supported", "unsupported"),
        ("stale", "ready", "supported", "stale"),
    ],
)
def test_readiness_projection_never_collapses_non_ready_states(
    binding_status: str,
    availability: str,
    runtime_status: str,
    expected: str,
) -> None:
    plan = resource_readiness(
        {
            "reference": REFERENCE,
            "name": "Filesystem Read",
            "bound_content_hash": "a" * 64,
            "content_hash": "b" * 64 if binding_status == "stale" else "a" * 64,
            "binding_status": binding_status,
            "availability": availability,
            "runtime_status": runtime_status,
            "required_permissions": {
                "network_hosts": [],
                "tools": ["veyra.tool.filesystem.read"],
                "filesystem_read_roots": ["project"],
                "filesystem_write_roots": [],
                "shell_workspace_only": False,
            },
        }
    )
    assert plan["readiness"] == expected


@pytest.mark.parametrize(
    "instruction",
    [
        "让它读取项目文件。",
        "给这个 Agent 文件读取能力。",
        "让研究助手能读项目里的文件。",
        "给它 filesystem.read。",
        "Add the Read File capability.",
    ],
)
def test_single_project_resource_proposes_exact_pin_and_minimum_permission(
    tmp_path: Path, instruction: str
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        agent_id = draft["source"]["agent_id"]
        resource = _bind_read(client, project_id)

        response = _propose(client, project_id, agent_id, draft, instruction)
        assert response.status_code == 201, response.text
        proposal = response.json()
        plan = proposal["resource_binding"]
        assert plan == {
            "reference": REFERENCE,
            "name": "Filesystem Read",
            "bound_content_hash": resource["bound_content_hash"],
            "catalog_content_hash": resource["content_hash"],
            "binding_status": "current",
            "readiness": "ready",
            "availability": "ready",
            "runtime_status": "supported",
            "required_permissions": resource["required_permissions"],
            "blocking_reasons": [],
            "project_resource_changed": False,
            "automatic_upgrade": False,
        }

        candidate = proposal["candidate_source"]
        node = next(
            item for item in candidate["nodes"] if item.get("uses") == REFERENCE
        )
        assert node == {
            "id": "filesystem_read",
            "component_type": "Tool",
            "uses": REFERENCE,
            "input_mapping": {"path": "path"},
        }
        assert candidate["inputs"]["path"] == "string"
        assert candidate["lock"][REFERENCE] == resource["bound_content_hash"]
        assert candidate["extensions"]["veyra"]["permissions"] == {
            "network_hosts": [],
            "tools": ["veyra.tool.filesystem.read"],
            "filesystem_read_roots": ["project"],
            "filesystem_write_roots": [],
            "shell_workspace_only": False,
        }
        assert candidate["transitions"][:2] == [
            {"from": "start", "port": "next", "to": "filesystem_read"},
            {"from": "model", "port": "next", "to": "output"},
        ]
        assert candidate["transitions"][-1] == {
            "from": "filesystem_read",
            "port": "next",
            "to": "model",
        }
        assert proposal["permission_changes"]
        assert client.get(f"{target_url}/draft").json() == draft
        assert client.get(f"{target_url}/versions").json()["versions"] == []
        assert not transport.calls


def test_global_catalog_only_and_cross_project_binding_are_not_selectable(
    tmp_path: Path,
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        agent_id = draft["source"]["agent_id"]

        global_only = _propose(client, project_id, agent_id, draft)
        assert global_only.status_code == 422, global_only.text
        assert global_only.json()["code"] == "resource_mention_unbound"
        assert "has not been added to this Project" in global_only.json()["message"]

        _bind_read(client, project_id)
        wrong_version = _propose(
            client,
            project_id,
            agent_id,
            draft,
            "给它 veyra.tool.filesystem.read@2.0.0。",
        )
        assert wrong_version.status_code == 422, wrong_version.text
        assert wrong_version.json()["code"] == "resource_mention_unbound"
        assert client.get(f"{target_url}/draft").json() == draft

        other_project_id, _, _ = _target(client, "agent")
        _bind_read(client, other_project_id)
        unbound_project_id, unbound_url, unbound_draft = _target(client, "agent")
        cross_project = _propose(
            client,
            unbound_project_id,
            unbound_draft["source"]["agent_id"],
            unbound_draft,
        )
        assert cross_project.status_code == 422, cross_project.text
        assert cross_project.json()["code"] == "resource_mention_unbound"
        assert client.get(f"{unbound_url}/draft").json() == unbound_draft
        assert not transport.calls


def test_multiple_project_versions_require_an_exact_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        agent_id = draft["source"]["agent_id"]
        _bind_read(client, project_id)
        service = client.app.state.project_resources
        original = service.list

        def duplicated(selected_project_id: str) -> dict[str, Any]:
            result = deepcopy(original(selected_project_id))
            if selected_project_id != project_id:
                return result
            first = next(
                item
                for item in result["resources"]
                if item.get("scope") == "project" and item["reference"] == REFERENCE
            )
            result["resources"].append(
                {
                    **first,
                    "version": "1.1.0",
                    "reference": "veyra.tool.filesystem.read@1.1.0",
                    "bound_content_hash": "b" * 64,
                    "content_hash": "b" * 64,
                }
            )
            return result

        monkeypatch.setattr(service, "list", duplicated)
        response = _propose(client, project_id, agent_id, draft)
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "resource_mention_ambiguous"
        assert REFERENCE in response.json()["details"]["candidates"]
        assert (
            "veyra.tool.filesystem.read@1.1.0"
            in response.json()["details"]["candidates"]
        )
        assert client.get(f"{target_url}/draft").json() == draft


def test_apply_reload_validate_reject_and_undo_reuse_existing_draft_boundary(
    tmp_path: Path,
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        agent_id = draft["source"]["agent_id"]
        resource = _bind_read(client, project_id)

        rejected = _propose(client, project_id, agent_id, draft).json()
        rejected_url = (
            f"/api/v1/projects/{project_id}/edit-proposals/{rejected['proposal_id']}"
        )
        assert _command(client, rejected_url, "reject").status_code == 200
        assert client.get(f"{target_url}/draft").json() == draft

        proposal = _propose(
            client, project_id, agent_id, draft, "给这个 Agent 文件读取能力。"
        ).json()
        proposal_url = (
            f"/api/v1/projects/{project_id}/edit-proposals/{proposal['proposal_id']}"
        )
        applied_response = _command(client, proposal_url, "apply")
        assert applied_response.status_code == 200, applied_response.text
        applied = client.get(f"{target_url}/draft").json()
        assert applied["revision"] == draft["revision"] + 1
        node = next(
            item for item in applied["source"]["nodes"] if item.get("uses") == REFERENCE
        )
        assert node["component_type"] == "Tool"
        assert applied["source"]["lock"][REFERENCE] == resource["bound_content_hash"]

        # Studio mounts by GETting this exact Draft; no second source cache exists.
        reloaded = client.get(f"{target_url}/draft")
        assert reloaded.status_code == 200, reloaded.text
        assert reloaded.json()["source"] == applied["source"]
        validation = client.post(f"{target_url}/validate")
        assert validation.status_code == 200, validation.text
        dependency = next(
            item
            for item in validation.json()["dependencies"]
            if item["reference"] == REFERENCE
        )
        assert dependency["status"] == "ready"
        assert dependency["locked_hash"] == dependency["bound_content_hash"]
        assert client.get(f"{target_url}/versions").json()["versions"] == []
        assert client.get(f"{target_url}/runs").json()["runs"] == []

        assert _command(client, proposal_url, "undo").status_code == 200
        restored = client.get(f"{target_url}/draft").json()
        assert restored["source"] == draft["source"]


def test_catalog_drift_keeps_project_hash_and_never_silently_upgrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        agent_id = draft["source"]["agent_id"]
        bound = _bind_read(client, project_id)
        hash_a = bound["bound_content_hash"]
        hash_b = "b" * 64
        assert hash_a != hash_b
        catalog = client.app.state.resource_catalog
        original = catalog.by_reference

        def changed(reference: str) -> dict[str, Any]:
            descriptor = original(reference)
            return (
                {**descriptor, "content_hash": hash_b}
                if reference == REFERENCE
                else descriptor
            )

        monkeypatch.setattr(catalog, "by_reference", changed)
        response = _propose(client, project_id, agent_id, draft)
        assert response.status_code == 201, response.text
        proposal = response.json()
        plan = proposal["resource_binding"]
        assert plan["readiness"] == "stale"
        assert plan["binding_status"] == "stale"
        assert plan["bound_content_hash"] == hash_a
        assert plan["catalog_content_hash"] == hash_b
        assert proposal["candidate_source"]["lock"][REFERENCE] == hash_a
        assert hash_b not in proposal["candidate_source"]["lock"].values()

        proposal_url = (
            f"/api/v1/projects/{project_id}/edit-proposals/{proposal['proposal_id']}"
        )
        assert _command(client, proposal_url, "apply").status_code == 200
        applied = client.get(f"{target_url}/draft").json()
        assert applied["source"]["lock"][REFERENCE] == hash_a
        validation = client.post(f"{target_url}/validate").json()
        dependency = next(
            item
            for item in validation["dependencies"]
            if item["reference"] == REFERENCE
        )
        assert dependency["status"] == "project_binding_stale"
        assert dependency["locked_hash"] == dependency["bound_content_hash"] == hash_a
        assert not transport.calls


def test_requires_configuration_is_never_presented_as_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, _, draft = _target(client, "agent")
        agent_id = draft["source"]["agent_id"]
        _bind_read(client, project_id)
        readiness = client.app.state.resource_readiness
        original = readiness.project

        def configuration_required(descriptor: dict[str, Any]) -> dict[str, Any]:
            result = original(descriptor)
            if descriptor["reference"] == REFERENCE:
                result.update(
                    availability="requires_configuration",
                    runtime_status="runtime_not_configured",
                    blocking_reasons=[
                        {
                            "code": "resource_configuration",
                            "message": "Complete host configuration.",
                        }
                    ],
                )
            return result

        monkeypatch.setattr(readiness, "project", configuration_required)
        response = _propose(client, project_id, agent_id, draft)
        assert response.status_code == 201, response.text
        plan = response.json()["resource_binding"]
        assert plan["readiness"] == "requires_configuration"
        assert plan["availability"] == "requires_configuration"
        assert plan["runtime_status"] == "runtime_not_configured"
        assert plan["blocking_reasons"][0]["code"] == "resource_configuration"


def test_revision_conflict_preserves_user_work(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        agent_id = draft["source"]["agent_id"]
        _bind_read(client, project_id)
        stale_baseline = {**draft, "revision": draft["revision"] + 1}
        response = _propose(client, project_id, agent_id, stale_baseline)
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "draft_conflict"
        assert client.get(f"{target_url}/draft").json() == draft
        assert not transport.calls
