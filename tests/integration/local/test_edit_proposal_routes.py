from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.integration.local.test_factory_routes import (
    ScriptedKimiTransport,
    _client,
    _completion,
    _project,
)
from tests.integration.local.test_workflow_version_boundary import save, setup_call
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.builder.prompt import BUILDER_SYSTEM_PROMPT


def _target(client: TestClient, kind: str) -> tuple[str, str, dict]:
    project_id = _project(client)
    response = client.post(
        f"/api/v1/projects/{project_id}/{kind}s",
        json={"name": "Editable", **({"mode": "blank"} if kind == "agent" else {})},
    )
    assert response.status_code == 201, response.text
    target_id = response.json()[f"{kind}_id"]
    url = f"/api/v1/projects/{project_id}/{kind}s/{target_id}"
    draft = client.get(f"{url}/draft")
    assert draft.status_code == 200, draft.text
    return project_id, url, draft.json()


def _propose(
    client: TestClient,
    transport: ScriptedKimiTransport,
    project_id: str,
    kind: str,
    draft: dict,
) -> tuple[str, dict]:
    candidate = deepcopy(draft["source"])
    candidate["description"] = "A reviewed change."
    transport.completions.append(_completion(json.dumps(candidate)))
    url = f"/api/v1/projects/{project_id}/edit-proposals"
    response = client.post(
        url,
        json={
            "target_kind": kind,
            "target_id": candidate[f"{kind}_id"],
            "instruction": "Update the description.",
            "expected_revision": draft["revision"],
            "expected_etag": draft["etag"],
        },
    )
    assert response.status_code == 201, response.text
    return f"{url}/{response.json()['proposal_id']}", response.json()


def _command(client: TestClient, url: str, command: str):
    return client.post(f"{url}/commands", json={"command": command, "confirm": True})


def _save(client: TestClient, url: str, draft: dict) -> dict:
    source = deepcopy(draft["source"])
    source["description"] = "An independent edit."
    response = client.patch(
        f"{url}/draft",
        json={"source": source, "expected_revision": draft["revision"]},
        headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_review_apply_restart_undo_and_idempotency(tmp_path: Path, kind: str) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, kind)
        url, proposal = _propose(client, transport, project_id, kind, draft)
        assert proposal["state"] == "review"
        assert proposal["stale"] is False
        assert proposal["changes"] == [
            {
                "path": "/description",
                "operation": "replace",
                "before": draft["source"]["description"],
                "after": "A reviewed change.",
            }
        ]
        assert proposal["permission_changes"] == []
        assert proposal["impact"]["runs_started"] is False
        assert not {"previous_source", "undo_key", "apply_key"} & proposal.keys()
        assert client.get(f"{target_url}/draft").json() == draft
        for confirm in (False, "true", 1):
            denied = client.post(
                f"{url}/commands",
                json={
                    "command": "apply",
                    "confirm": confirm,
                },
            )
            assert denied.status_code == 422
        assert client.get(f"{target_url}/draft").json() == draft
        applied = _command(client, url, "apply")
        assert applied.status_code == 200, applied.text
        assert applied.json()["state"] == "applied"
        assert applied.json()["stale"] is False
        assert _command(client, url, "apply").json() == applied.json()
        assert (
            client.get(f"{target_url}/draft").json()["revision"]
            == draft["revision"] + 1
        )
        assert client.get(f"{target_url}/versions").json()["versions"] == []
        assert client.get(f"{target_url}/runs").json()["runs"] == []

    with _client(tmp_path, ScriptedKimiTransport([])) as client:
        assert client.get(url).json()["state"] == "applied"
        undone = _command(client, url, "undo")
        assert undone.status_code == 200, undone.text
        assert undone.json()["state"] == "undone"
        assert undone.json()["stale"] is False
        assert _command(client, url, "undo").json() == undone.json()
        current = client.get(f"{target_url}/draft").json()
        assert current["source"] == draft["source"]
        assert current["revision"] == draft["revision"] + 2
        assert _command(client, url, "apply").status_code == 422
        assert _command(client, url, "reject").status_code == 422

    with _client(tmp_path, ScriptedKimiTransport([])) as client:
        assert client.get(url).json()["state"] == "undone"


@pytest.mark.parametrize("kind", ["agent", "workflow"])
@pytest.mark.parametrize("applied", [False, True])
def test_newer_draft_blocks_apply_and_undo(tmp_path: Path, kind: str, applied: bool):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, kind)
        url, _ = _propose(client, transport, project_id, kind, draft)
        if applied:
            assert _command(client, url, "apply").status_code == 200
        current = client.get(f"{target_url}/draft").json()
        saved = _save(client, target_url, current)
        assert client.get(url).json()["stale"] is True
        response = _command(client, url, "undo" if applied else "apply")
        assert response.status_code == 409, response.text
        assert client.get(f"{target_url}/draft").json()["source"] == saved["source"]
        if not applied:
            assert _command(client, url, "reject").json()["state"] == "rejected"
            assert _command(client, url, "reject").json()["state"] == "rejected"
            assert _command(client, url, "apply").status_code == 422


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_external_edit_keeps_proposal_reviewable_and_rejectable(
    tmp_path: Path, kind: str
):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, _, draft = _target(client, kind)
        url, _ = _propose(client, transport, project_id, kind, draft)
        project = client.get(f"/api/v1/projects/{project_id}").json()
        path = Path(project["root_path"]) / project[f"{kind}s"][0]["source_path"]
        source = deepcopy(draft["source"])
        source["description"] = "Changed by an external editor."
        text = json.dumps(source)
        path.write_text(text)
        view = client.get(url)
        assert view.status_code == 200, view.text
        assert view.json()["stale"] is True
        listed = client.get(
            f"/api/v1/projects/{project_id}/edit-proposals",
            params={"target_kind": kind, "target_id": source[f"{kind}_id"]},
        )
        assert listed.status_code == 200, listed.text
        assert listed.json()["proposals"][0]["stale"] is True
        assert _command(client, url, "apply").status_code == 409
        assert _command(client, url, "reject").json()["state"] == "rejected"
        assert path.read_text() == text


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_invalid_output_is_bounded_and_never_changes_draft(tmp_path: Path, kind: str):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, kind)
        candidate = deepcopy(draft["source"])
        candidate[f"{kind}_id"] = new_uuid7()
        transport.completions.extend(
            [
                _completion("{"),
                _completion(json.dumps(candidate)),
                _completion(json.dumps(draft["source"])),
            ]
        )
        url = f"/api/v1/projects/{project_id}/edit-proposals"
        payload = {
            "target_kind": kind,
            "target_id": draft["source"][f"{kind}_id"],
            "instruction": "Change the description.",
            "expected_revision": draft["revision"],
            "expected_etag": "stale",
        }
        assert client.post(url, json=payload).status_code == 409
        assert not transport.calls
        payload["expected_etag"] = draft["etag"]
        failed = client.post(url, json=payload)
        assert failed.status_code == 422, failed.text
        assert failed.json()["code"] == "edit_generation_invalid"
        assert len(transport.calls) == 3
        assert client.get(f"{target_url}/draft").json() == draft
        assert (
            client.get(
                url,
                params={
                    "target_kind": kind,
                    "target_id": payload["target_id"],
                },
            ).json()["proposals"]
            == []
        )


def test_concurrent_confirmation_writes_one_revision(tmp_path: Path):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        url, _ = _propose(client, transport, project_id, "agent", draft)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(lambda _: _command(client, url, "apply"), range(2))
            )
        assert [response.status_code for response in responses] == [200, 200]
        assert (
            client.get(f"{target_url}/draft").json()["revision"]
            == draft["revision"] + 1
        )
        other_project = _project(client)
        other_url = url.replace(project_id, other_project)
        assert client.get(other_url).status_code == 404
        assert _command(client, other_url, "undo").status_code == 404


def test_dependency_drift_requires_new_review(tmp_path: Path):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        response = client.post(
            f"/api/v1/projects/{project_id}/knowledge",
            json={"name": "Brief", "text": "Original reference."},
        )
        assert response.status_code == 201, response.text
        knowledge = response.json()
        reference = f"{knowledge['knowledge_id']}@{knowledge['version']}"
        draft["source"]["extensions"]["veyra"]["knowledge_refs"] = [reference]
        draft["source"]["lock"][reference] = knowledge["source_file_hash"]
        saved = _save(client, target_url, draft)
        url, proposal = _propose(client, transport, project_id, "agent", saved)
        assert proposal["validation"]["dependencies"][0]["status"] == "ready"
        changed = client.patch(
            f"/api/v1/projects/{project_id}/knowledge/{knowledge['knowledge_id']}",
            json={"text": "Changed reference."},
        )
        assert changed.status_code == 200, changed.text
        denied = _command(client, url, "apply")
        assert denied.status_code == 409, denied.text
        assert denied.json()["code"] == "draft_conflict"
        assert client.get(f"{target_url}/draft").json()["source"] == saved["source"]


def test_unknown_dependency_is_repaired_and_permission_diff_is_real(tmp_path: Path):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        invalid = deepcopy(draft["source"])
        reference = "veyra.skill.invented@1.0.0"
        invalid["extensions"]["veyra"]["skill_refs"] = [reference]
        invalid["lock"][reference] = "0" * 64
        candidate = deepcopy(draft["source"])
        candidate["extensions"]["veyra"]["permissions"]["network_hosts"] = [
            "example.com"
        ]
        transport.completions.extend(
            [
                _completion(json.dumps(invalid)),
                _completion(json.dumps(candidate)),
            ]
        )
        response = client.post(
            f"/api/v1/projects/{project_id}/edit-proposals",
            json={
                "target_kind": "agent",
                "target_id": candidate["agent_id"],
                "instruction": "Propose access to example.com.",
                "expected_revision": draft["revision"],
                "expected_etag": draft["etag"],
            },
        )
        assert response.status_code == 201, response.text
        proposal = response.json()
        assert len(transport.calls) == 2
        assert proposal["candidate_source"] == candidate
        assert proposal["permission_changes"] == [
            {
                "path": "/network_hosts",
                "operation": "replace",
                "before": [],
                "after": ["example.com"],
            }
        ]
        assert client.get(f"{target_url}/draft").json() == draft


def test_workflow_proposal_reviews_pinned_calls_and_repairs_wrong_lock(tmp_path: Path):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, agent_id, version, target_url, draft = setup_call(client)
        save(client, target_url, draft)
        draft = client.get(f"{target_url}/draft").json()
        candidate = deepcopy(draft["source"])
        candidate["description"] = "Keep the reviewed immutable Agent call."
        invalid = deepcopy(candidate)
        invalid["lock"][f"{agent_id}@{version['version_id']}"] = "0" * 64
        transport.completions.extend(
            [_completion(json.dumps(invalid)), _completion(json.dumps(candidate))]
        )
        response = client.post(
            f"/api/v1/projects/{project_id}/edit-proposals",
            json={
                "target_kind": "workflow",
                "target_id": candidate["workflow_id"],
                "instruction": "Update the description, preserving the Agent call.",
                "expected_revision": draft["revision"],
                "expected_etag": draft["etag"],
            },
        )
        assert response.status_code == 201, response.text
        proposal = response.json()
        assert len(transport.calls) == 2
        assert proposal["validation"]["agent_calls"] == [
            {
                "node_id": "call",
                "agent_id": agent_id,
                "version_id": version["version_id"],
            }
        ]
        assert client.get(f"{target_url}/draft").json() == draft
        url = f"/api/v1/projects/{project_id}/edit-proposals/{proposal['proposal_id']}"
        assert _command(client, url, "apply").status_code == 200
        current = client.get(f"{target_url}/draft").json()
        assert current["source"] == candidate
        assert client.post(f"{target_url}/validate").status_code == 200
        assert _command(client, url, "undo").status_code == 200
        assert client.get(f"{target_url}/draft").json()["source"] == draft["source"]
        assert client.get(f"{target_url}/versions").json()["versions"] == []
        assert client.get(f"{target_url}/runs").json()["runs"] == []


def test_builder_project_context_reuses_resource_and_changes_real_graph(tmp_path: Path):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        project_url = f"/api/v1/projects/{project_id}"
        knowledge = client.post(
            f"{project_url}/knowledge",
            json={"name": "Private reference", "text": "CONTENT_NOT_FOR_BUILDER"},
        )
        assert knowledge.status_code == 201
        reference = "veyra.skill.research-brief@1.0.0"
        descriptor = next(
            item
            for item in client.get("/api/v1/resources").json()["resources"]
            if item["reference"] == reference
        )
        bound = client.post(f"{project_url}/resources", json={"reference": reference})
        assert bound.status_code == 201, bound.text
        candidate = deepcopy(draft["source"])
        candidate["name"] = "Research Builder"
        candidate["inputs"] = {"question": "string"}
        candidate["outputs"] = {"brief": "string"}
        candidate["nodes"] = [
            {"id": "start", "component_type": "Start"},
            {
                "id": "research",
                "component_type": "Agent",
                "model_ref": "model.primary",
                "system_prompt": "Write a research brief.",
            },
            {"id": "output", "component_type": "Output", "output_name": "brief"},
        ]
        candidate["transitions"] = [
            {"from": "start", "port": "next", "to": "research"},
            {"from": "research", "port": "next", "to": "output"},
        ]
        candidate["ui"]["positions"] = {
            "start": {"x": 0, "y": 0},
            "research": {"x": 200, "y": 0},
            "output": {"x": 400, "y": 0},
        }
        candidate["extensions"]["veyra"]["skill_refs"] = [reference]
        candidate["lock"][reference] = descriptor["content_hash"]
        transport.completions.append(_completion(json.dumps(candidate)))
        response = client.post(
            f"{project_url}/edit-proposals",
            json={
                "target_kind": "agent",
                "target_id": candidate["agent_id"],
                "instruction": (
                    "把这个 Agent 改成研究助手，优先复用项目的 research-brief Skill。"
                ),
                "expected_revision": draft["revision"],
                "expected_etag": draft["etag"],
            },
        )
        assert response.status_code == 201, response.text
        messages, _ = transport.calls[0]
        assert messages[0]["content"].startswith(BUILDER_SYSTEM_PROMPT)
        context = json.loads(messages[1]["content"])
        assert context["project"]["project_id"] == project_id
        assert context["target"]["revision"] == draft["revision"]
        assert context["target"]["etag"] == draft["etag"]
        assert context["target"]["source"] == draft["source"]
        assert context["project_bindings"][0]["reference"] == reference
        assert context["inventory"]["knowledge"][0]["name"] == "Private reference"
        assert "CONTENT_NOT_FOR_BUILDER" not in json.dumps(context)
        assert str(tmp_path) not in json.dumps(context)
        assert context["authority"]["runtime_execution"] == "not_performed"
        assert client.get(f"{target_url}/draft").json() == draft
        proposal = response.json()
        assert any(item["path"] == "/nodes" for item in proposal["changes"])
        url = f"{project_url}/edit-proposals/{proposal['proposal_id']}"
        assert _command(client, url, "apply").status_code == 200
        actual = client.get(f"{target_url}/draft").json()
        assert actual["source"] == candidate
        assert actual["revision"] == draft["revision"] + 1
        assert client.get(project_url).json()["agents"][0]["name"] == "Research Builder"
        checked = client.post(f"{target_url}/validate")
        assert checked.status_code == 200, checked.text
        assert checked.json()["source_hash"] == proposal["validation"]["source_hash"]
        assert client.get(f"{target_url}/versions").json()["versions"] == []
        assert client.get(f"{target_url}/runs").json()["runs"] == []


@pytest.mark.parametrize("kind", ["agent", "workflow"])
@pytest.mark.parametrize(
    "root", ["/private/local-documents", r"C:\Users\local\documents"]
)
def test_absolute_permission_roots_never_reach_provider(tmp_path, kind, root):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, kind)
        for field in ("filesystem_read_roots", "filesystem_write_roots"):
            draft["source"]["extensions"]["veyra"]["permissions"][field] = [root]
        _save(client, target_url, draft)
        saved = client.get(f"{target_url}/draft").json()
        response = client.post(
            f"/api/v1/projects/{project_id}/edit-proposals",
            json={
                "target_kind": kind,
                "target_id": saved["source"][f"{kind}_id"],
                "instruction": "Update the description.",
                "expected_revision": saved["revision"],
                "expected_etag": saved["etag"],
            },
        )
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "edit_source_host_paths"
        assert not transport.calls
        assert root not in response.text
        assert client.get(f"{target_url}/draft").json() == saved


@pytest.mark.parametrize("kind", ["agent", "workflow"])
@pytest.mark.parametrize("mode", ["public_id", "legacy_apply", "undo"])
def test_ordinary_draft_receipt_cannot_close_proposal(tmp_path, kind, mode):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, kind)
        url, proposal = _propose(client, transport, project_id, kind, draft)
        store = client.app.state.edit_proposals.store
        private = store.get(project_id, proposal["proposal_id"])
        if mode == "legacy_apply":
            private.pop("apply_key")
            with store.repository.transaction() as connection:
                connection.execute(
                    "UPDATE edit_proposals SET payload_json = ? WHERE proposal_id = ?",
                    (json.dumps(private), proposal["proposal_id"]),
                )
        elif mode == "undo":
            assert _command(client, url, "apply").status_code == 200
            draft = client.get(f"{target_url}/draft").json()
        source = deepcopy(draft["source"])
        source["description"] = "An unrelated ordinary Draft write."
        if mode == "public_id":
            source = proposal["candidate_source"]
        response = client.patch(
            f"{target_url}/draft",
            json={"source": source, "expected_revision": draft["revision"]},
            headers={
                "If-Match": draft["etag"],
                "Idempotency-Key": private["undo_key"]
                if mode == "undo"
                else proposal["proposal_id"],
            },
        )
        assert response.status_code == 200, response.text
        saved = client.get(f"{target_url}/draft").json()
        view = client.get(url).json()
        assert view["state"] == ("applied" if mode == "undo" else "review")
        assert view["stale"] is True
        assert (
            _command(client, url, "undo" if mode == "undo" else "apply").status_code
            == 409
        )
        assert client.get(f"{target_url}/draft").json() == saved
