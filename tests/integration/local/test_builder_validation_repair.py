"""Builder Phase 2 Slice 3: typed validation feedback and deterministic repair."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.integration.local.test_builder_resource_binding import _bind_read
from tests.integration.local.test_edit_proposal_routes import _command, _target
from tests.integration.local.test_factory_routes import ScriptedKimiTransport, _client
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.builder.validation_repair import (
    project_issues,
    repair_agent_source,
)

REFERENCE = "veyra.tool.filesystem.read@1.0.0"
TOOL_ID = "veyra.tool.filesystem.read"
EMPTY_PERMISSIONS = {
    "network_hosts": [],
    "tools": [],
    "filesystem_read_roots": [],
    "filesystem_write_roots": [],
    "shell_workspace_only": False,
}


def _save(client: TestClient, url: str, draft: dict[str, Any], source: dict[str, Any]):
    return client.patch(
        f"{url}/draft",
        json={"source": source, "expected_revision": draft["revision"]},
        headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
    )


def _repair(client: TestClient, project_id: str, draft: dict[str, Any], **fields: Any):
    return client.post(
        f"/api/v1/projects/{project_id}/edit-proposals/validation-repair",
        json={
            "agent_id": draft["source"]["agent_id"],
            "expected_revision": draft["revision"],
            "expected_etag": draft["etag"],
            **fields,
        },
    )


def _tool_source(
    draft: dict[str, Any], resource: dict[str, Any], lock: str
) -> dict[str, Any]:
    source = deepcopy(draft["source"])
    source["nodes"].append(
        {"id": "bound_tool", "component_type": "Tool", "uses": resource["reference"]}
    )
    edge = source["transitions"][0]
    source["transitions"].append(
        {"from": "bound_tool", "port": "next", "to": edge["to"]}
    )
    edge["to"] = "bound_tool"
    source["lock"][resource["reference"]] = lock
    permissions = deepcopy(EMPTY_PERMISSIONS)
    permissions["tools"] = [TOOL_ID]
    source["extensions"]["veyra"]["permissions"] = permissions
    return source


def _reload_lock(
    client: TestClient,
    project: dict[str, Any],
    agent_id: str,
    url: str,
    reference: str,
    digest: str,
) -> dict[str, Any]:
    agent = next(item for item in project["agents"] if item["agent_id"] == agent_id)
    path = Path(project["root_path"]) / agent["source_path"]
    source = client.get(f"{url}/draft").json()["source"]
    source["lock"][reference] = digest
    path.write_text(json.dumps(source), encoding="utf-8")
    reloaded = client.post(f"{url}/draft/reload")
    assert reloaded.status_code == 200, reloaded.text
    return reloaded.json()


def test_projection_marks_only_server_known_issues_repairable() -> None:
    pin = "a" * 64
    issues = project_issues(
        {
            "dependencies": [
                {
                    "reference": REFERENCE,
                    "kind": "tool",
                    "name": "Read File",
                    "status": "lock_mismatch",
                    "detail": (
                        "Agent lock does not match the Project pinned content hash."
                    ),
                    "bound_content_hash": pin,
                    "locked_hash": "b" * 64,
                    "required_permissions": {"tools": ["veyra.tool.filesystem.read"]},
                },
                {
                    "reference": REFERENCE,
                    "kind": "tool",
                    "name": "Read File",
                    "status": "resource_unbound",
                    "detail": "Tool is not bound to this Project.",
                },
                {
                    "reference": "veyra.tool.github.read@1.0.0",
                    "kind": "tool",
                    "name": "GitHub",
                    "status": "configuration_required",
                    "detail": "Resource requires host configuration before it can run.",
                },
                {
                    "reference": REFERENCE,
                    "kind": "tool",
                    "name": "Read File",
                    "status": "permission_denied",
                    "detail": "Missing required Tool permission.",
                    "required_permissions": {"tools": ["veyra.tool.filesystem.read"]},
                },
            ]
        }
    )
    assert [item["repairable"] for item in issues] == [True, False, False, True]
    repaired = repair_agent_source(
        {
            "lock": {REFERENCE: "b" * 64},
            "extensions": {"veyra": {"permissions": EMPTY_PERMISSIONS}},
        },
        issues[0],
    )
    assert repaired["lock"][REFERENCE] == pin


def test_valid_false_is_not_needed_for_dependency_failure_contract(
    tmp_path: Path,
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        resource = _bind_read(client, project_id)
        source = _tool_source(draft, resource, resource["bound_content_hash"])
        saved = _save(client, target_url, draft, source)
        assert saved.status_code == 200, saved.text
        validation = client.post(f"{target_url}/validate").json()
        assert validation["valid"] is True
        assert validation["runtime_ready"] is False
        assert validation["dependencies"][0]["status"] == "permission_denied"
        assert not transport.calls


def test_lock_mismatch_repair_uses_project_pin_and_apply_revalidates(
    tmp_path: Path,
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        agent_id = draft["source"]["agent_id"]
        resource = _bind_read(client, project_id)
        source = _tool_source(draft, resource, resource["bound_content_hash"])
        source["extensions"]["veyra"]["permissions"] = resource["required_permissions"]
        saved = _save(client, target_url, draft, source)
        assert saved.status_code == 200, saved.text
        project = client.get(f"/api/v1/projects/{project_id}").json()
        wrong = "b" * 64
        drifted = _reload_lock(client, project, agent_id, target_url, REFERENCE, wrong)
        validation = client.post(f"{target_url}/validate").json()
        assert validation["dependencies"][0]["status"] == "lock_mismatch"
        assert validation["dependencies"][0]["locked_hash"] == wrong
        assert (
            validation["dependencies"][0]["bound_content_hash"]
            == resource["bound_content_hash"]
        )

        before = client.get(f"{target_url}/draft").json()
        response = _repair(
            client, project_id, drifted, reference=REFERENCE, code="lock_mismatch"
        )
        assert response.status_code == 201, response.text
        proposal = response.json()
        assert (
            proposal["validation_repair"]["bound_content_hash"]
            == resource["bound_content_hash"]
        )
        assert (
            proposal["candidate_source"]["lock"][REFERENCE]
            == resource["bound_content_hash"]
        )
        assert proposal["candidate_source"]["lock"][REFERENCE] != wrong
        assert client.get(f"{target_url}/draft").json() == before
        assert not transport.calls

        proposal_url = (
            f"/api/v1/projects/{project_id}/edit-proposals/{proposal['proposal_id']}"
        )
        assert _command(client, proposal_url, "apply").status_code == 200
        applied = client.get(f"{target_url}/draft").json()
        assert applied["source"]["lock"][REFERENCE] == resource["bound_content_hash"]
        checked = client.post(f"{target_url}/validate").json()
        assert checked["runtime_ready"] is True
        assert checked["dependencies"][0]["status"] == "ready"

        undo = _command(client, proposal_url, "undo")
        assert undo.status_code == 422, undo.text
        assert undo.json()["code"] == "resource_lock_mismatch"
        assert (
            client.get(f"{target_url}/draft").json()["source"]["lock"][REFERENCE]
            == resource["bound_content_hash"]
        )


def test_missing_permission_repair_grants_only_required_values(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        resource = _bind_read(client, project_id)
        source = _tool_source(draft, resource, resource["bound_content_hash"])
        source["extensions"]["veyra"]["permissions"]["network_hosts"] = ["example.com"]
        saved = _save(client, target_url, draft, source)
        assert saved.status_code == 200, saved.text
        draft = saved.json()
        validation = client.post(f"{target_url}/validate").json()
        assert validation["dependencies"][0]["status"] == "permission_denied"
        response = _repair(
            client, project_id, draft, reference=REFERENCE, code="permission_denied"
        )
        assert response.status_code == 201, response.text
        proposal = response.json()
        granted = proposal["candidate_source"]["extensions"]["veyra"]["permissions"]
        required = resource["required_permissions"]
        assert set(required["tools"]).issubset(granted["tools"])
        assert set(required["filesystem_read_roots"]).issubset(
            granted["filesystem_read_roots"]
        )
        assert granted["network_hosts"] == ["example.com"]
        assert granted["filesystem_write_roots"] == []
        assert (
            client.get(f"{target_url}/draft").json()["source"]["extensions"]["veyra"][
                "permissions"
            ]
            == source["extensions"]["veyra"]["permissions"]
        )

        proposal_url = (
            f"/api/v1/projects/{project_id}/edit-proposals/{proposal['proposal_id']}"
        )
        assert _command(client, proposal_url, "reject").status_code == 200
        assert (
            client.get(f"{target_url}/draft").json()["source"]["extensions"]["veyra"][
                "permissions"
            ]
            == source["extensions"]["veyra"]["permissions"]
        )

        current = client.get(f"{target_url}/draft").json()
        second = _repair(
            client, project_id, current, reference=REFERENCE, code="permission_denied"
        )
        assert second.status_code == 201, second.text
        applied_url = (
            f"/api/v1/projects/{project_id}/edit-proposals/"
            f"{second.json()['proposal_id']}"
        )
        assert _command(client, applied_url, "apply").status_code == 200
        after = client.get(f"{target_url}/draft").json()["source"]["extensions"][
            "veyra"
        ]["permissions"]
        assert set(required["tools"]).issubset(after["tools"])
        assert set(required["filesystem_read_roots"]).issubset(
            after["filesystem_read_roots"]
        )
        assert after["network_hosts"] == ["example.com"]
        assert after["filesystem_write_roots"] == []
        assert _command(client, applied_url, "undo").status_code == 200
        restored = client.get(f"{target_url}/draft").json()["source"]["extensions"][
            "veyra"
        ]["permissions"]
        assert restored == source["extensions"]["veyra"]["permissions"]
        assert not transport.calls


def test_unbound_and_configuration_required_do_not_invent_repairs(
    tmp_path: Path,
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        catalog = client.get(
            "/api/v1/resources/veyra.tool.filesystem.read/versions/1.0.0"
        ).json()
        source = _tool_source(draft, catalog, catalog["content_hash"])
        project = client.get(f"/api/v1/projects/{project_id}").json()
        agent = next(
            item
            for item in project["agents"]
            if item["agent_id"] == draft["source"]["agent_id"]
        )
        path = Path(project["root_path"]) / agent["source_path"]
        path.write_text(json.dumps(source), encoding="utf-8")
        drifted = client.post(f"{target_url}/draft/reload").json()
        validation = client.post(f"{target_url}/validate").json()
        assert validation["dependencies"][0]["status"] == "resource_unbound"
        refused = _repair(
            client, project_id, drifted, reference=REFERENCE, code="resource_unbound"
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["code"] == "validation_repair_not_repairable"
        listed = client.get(f"/api/v1/projects/{project_id}/resources").json()[
            "resources"
        ]
        assert not any(item.get("scope") == "project" for item in listed)
        assert not transport.calls


def test_configuration_required_does_not_invent_a_repair(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        github = client.get(
            "/api/v1/resources/veyra.tool.github.read/versions/1.0.0"
        ).json()
        bind = client.post(
            f"/api/v1/projects/{project_id}/resources",
            json={
                "reference": github["reference"],
                "content_hash": github["content_hash"],
            },
        )
        assert bind.status_code == 201, bind.text
        source = _tool_source(draft, github, github["content_hash"])
        source["extensions"]["veyra"]["permissions"] = github["required_permissions"]
        saved = _save(client, target_url, draft, source)
        assert saved.status_code == 200, saved.text
        configured = saved.json()
        status = client.post(f"{target_url}/validate").json()["dependencies"][0][
            "status"
        ]
        assert status == "configuration_required"
        blocked = _repair(
            client,
            project_id,
            configured,
            reference=github["reference"],
            code="configuration_required",
        )
        assert blocked.status_code == 422, blocked.text
        assert blocked.json()["code"] == "validation_repair_not_repairable"
        assert not transport.calls


def test_stale_repair_proposal_cannot_overwrite_later_edits(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        resource = _bind_read(client, project_id)
        source = _tool_source(draft, resource, resource["bound_content_hash"])
        saved = _save(client, target_url, draft, source)
        assert saved.status_code == 200, saved.text
        draft = saved.json()
        proposal = _repair(
            client, project_id, draft, reference=REFERENCE, code="permission_denied"
        ).json()
        later = deepcopy(draft["source"])
        later["description"] = "User edited after the failure."
        assert _save(client, target_url, draft, later).status_code == 200
        proposal_url = (
            f"/api/v1/projects/{project_id}/edit-proposals/{proposal['proposal_id']}"
        )
        conflict = _command(client, proposal_url, "apply")
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "draft_conflict"
        current = client.get(f"{target_url}/draft").json()
        assert current["source"]["description"] == "User edited after the failure."
        assert not transport.calls


def test_unknown_validation_issue_is_not_guessed(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        refused = _repair(
            client,
            project_id,
            draft,
            reference=REFERENCE,
            code="lock_mismatch",
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["code"] == "validation_repair_not_found"
        assert not transport.calls


def test_knowledge_lock_repair_is_an_explicit_rebind(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        knowledge = client.post(
            f"/api/v1/projects/{project_id}/knowledge/ingest",
            files={"file": ("thesis.txt", b"ORBIT-731")},
        ).json()
        reference = f"{knowledge['knowledge_id']}@{knowledge['version']}"
        source = deepcopy(draft["source"])
        source["extensions"]["veyra"]["knowledge_refs"] = [reference]
        source["lock"][reference] = knowledge["source_file_hash"]
        saved = _save(client, target_url, draft, source)
        assert saved.status_code == 200, saved.text
        changed = client.patch(
            f"/api/v1/projects/{project_id}/knowledge/{knowledge['knowledge_id']}",
            json={"text": "Changed thesis"},
        )
        assert changed.status_code == 200, changed.text
        draft = saved.json()
        validation = client.post(f"{target_url}/validate").json()
        issue = next(
            item for item in validation["dependencies"] if item["kind"] == "knowledge"
        )
        assert issue["status"] == "lock_mismatch"
        response = _repair(
            client, project_id, draft, reference=reference, code="lock_mismatch"
        )
        assert response.status_code == 201, response.text
        proposal = response.json()
        assert proposal["validation_repair"]["automatic_upgrade"] is False
        assert (
            proposal["candidate_source"]["lock"][reference]
            == changed.json()["source_file_hash"]
        )
        assert (
            proposal["candidate_source"]["lock"][reference]
            != knowledge["source_file_hash"]
        )
        assert (
            client.get(f"{target_url}/draft").json()["source"]["lock"][reference]
            == knowledge["source_file_hash"]
        )
        assert not transport.calls
