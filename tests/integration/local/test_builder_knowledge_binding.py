"""Builder Phase 2 Slice 1: natural-language Project Knowledge binding.

These tests never call a provider. Knowledge resolution and the lock digest are
server-owned, so the scripted transport stays empty on purpose.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.integration.local.test_edit_proposal_routes import _command, _target
from tests.integration.local.test_factory_routes import ScriptedKimiTransport, _client


def _knowledge(client: TestClient, project_id: str, name: str, text: str) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/knowledge", json={"name": name, "text": text}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _propose_binding(
    client: TestClient, project_id: str, agent_id: str, draft: dict, instruction: str
):
    return client.post(
        f"/api/v1/projects/{project_id}/edit-proposals/knowledge-binding",
        json={
            "agent_id": agent_id,
            "instruction": instruction,
            "expected_revision": draft["revision"],
            "expected_etag": draft["etag"],
        },
    )


def test_single_match_proposes_identity_lock_and_readiness(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        agent_id = draft["source"]["agent_id"]
        document = _knowledge(client, project_id, "毕业论文", "ORBIT marker\n")

        response = _propose_binding(
            client, project_id, agent_id, draft, "让这个 Agent 使用毕业论文资料。"
        )
        assert response.status_code == 201, response.text
        proposal = response.json()
        reference = f"{document['knowledge_id']}@{document['version']}"

        binding = proposal["knowledge_binding"]
        assert binding["reference"] == reference
        assert binding["source_file_hash"] == document["source_file_hash"]
        assert binding["index_status"] == "not_indexed"
        assert binding["runnable"] is False
        assert binding["required_action"] == "build_index"

        candidate = proposal["candidate_source"]
        assert candidate["extensions"]["veyra"]["knowledge_refs"] == [reference]
        assert candidate["lock"][reference] == document["source_file_hash"]
        card = next(
            item
            for item in candidate["ui"]["bindings"].values()
            if item["kind"] == "knowledge"
        )
        assert card["reference"] == reference

        # Nothing is written before confirmation.
        assert client.get(f"{target_url}/draft").json() == draft
        assert not transport.calls


def test_ambiguous_mention_requires_clarification_and_changes_nothing(
    tmp_path: Path,
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        agent_id = draft["source"]["agent_id"]
        _knowledge(client, project_id, "毕业论文", "current\n")
        _knowledge(client, project_id, "毕业论文-旧版", "older\n")

        response = _propose_binding(
            client, project_id, agent_id, draft, "让这个 Agent 使用毕业论文资料。"
        )
        assert response.status_code == 422, response.text
        body = response.json()
        assert body["code"] == "knowledge_mention_ambiguous"
        assert "毕业论文" in body["details"]["candidates"]
        assert "毕业论文-旧版" in body["details"]["candidates"]
        assert client.get(f"{target_url}/draft").json() == draft

        # A more specific mention resolves without guessing.
        specific = _propose_binding(
            client, project_id, agent_id, draft, "使用毕业论文-旧版资料。"
        )
        assert specific.status_code == 201, specific.text
        assert "毕业论文-旧版" in specific.json()["knowledge_binding"]["name"]


def test_unmatched_mention_reports_unresolved_without_mutation(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        agent_id = draft["source"]["agent_id"]
        _knowledge(client, project_id, "毕业论文", "current\n")

        response = _propose_binding(
            client, project_id, agent_id, draft, "让它读取季度财报。"
        )
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "knowledge_mention_unresolved"
        assert client.get(f"{target_url}/draft").json() == draft


def test_other_project_knowledge_is_never_reachable(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        agent_id = draft["source"]["agent_id"]
        other_project_id, _, _ = _target(client, "agent")
        _knowledge(client, other_project_id, "毕业论文", "foreign\n")

        response = _propose_binding(
            client, project_id, agent_id, draft, "使用毕业论文资料。"
        )
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "knowledge_mention_unresolved"
        assert client.get(f"{target_url}/draft").json() == draft


def test_apply_writes_refs_and_lock_then_validates(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        agent_id = draft["source"]["agent_id"]
        document = _knowledge(client, project_id, "毕业论文", "ORBIT marker\n")
        reference = f"{document['knowledge_id']}@{document['version']}"

        proposal = _propose_binding(
            client, project_id, agent_id, draft, "使用毕业论文资料。"
        ).json()
        url = f"/api/v1/projects/{project_id}/edit-proposals/{proposal['proposal_id']}"
        assert _command(client, url, "apply").status_code == 200

        applied = client.get(f"{target_url}/draft").json()
        assert applied["revision"] == draft["revision"] + 1
        assert applied["source"]["extensions"]["veyra"]["knowledge_refs"] == [reference]
        assert applied["source"]["lock"][reference] == document["source_file_hash"]

        checked = client.post(f"{target_url}/validate")
        assert checked.status_code == 200, checked.text
        knowledge_check = next(
            item
            for item in checked.json()["dependencies"]
            if item["kind"] == "knowledge"
        )
        assert knowledge_check["status"] == "ready"

        # Immutable history is untouched by a Draft-scoped binding.
        assert client.get(f"{target_url}/versions").json()["versions"] == []
        assert client.get(f"{target_url}/runs").json()["runs"] == []


def test_reject_and_undo_leave_no_binding(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        agent_id = draft["source"]["agent_id"]
        _knowledge(client, project_id, "毕业论文", "ORBIT marker\n")

        rejected = _propose_binding(
            client, project_id, agent_id, draft, "使用毕业论文资料。"
        ).json()
        rejected_url = (
            f"/api/v1/projects/{project_id}/edit-proposals/{rejected['proposal_id']}"
        )
        assert _command(client, rejected_url, "reject").status_code == 200
        assert client.get(f"{target_url}/draft").json() == draft

        applied = _propose_binding(
            client, project_id, agent_id, draft, "使用毕业论文资料。"
        ).json()
        applied_url = (
            f"/api/v1/projects/{project_id}/edit-proposals/{applied['proposal_id']}"
        )
        assert _command(client, applied_url, "apply").status_code == 200
        assert _command(client, applied_url, "undo").status_code == 200
        restored = client.get(f"{target_url}/draft").json()
        assert restored["source"] == draft["source"]
        assert not restored["source"]["extensions"]["veyra"].get("knowledge_refs")


def test_stale_index_is_shown_and_never_rebuilt(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, _, draft = _target(client, "agent")
        agent_id = draft["source"]["agent_id"]
        document = _knowledge(client, project_id, "毕业论文", "ORBIT marker\n")
        knowledge_url = (
            f"/api/v1/projects/{project_id}/knowledge/{document['knowledge_id']}"
        )
        assert client.post(f"{knowledge_url}/index").status_code == 200
        indexed = _propose_binding(
            client, project_id, agent_id, draft, "使用毕业论文资料。"
        ).json()["knowledge_binding"]
        assert indexed["index_status"] == "indexed"
        assert indexed["runnable"] is True
        assert indexed["chunk_count"] == 1

        edited = client.patch(knowledge_url, json={"text": "changed\n"})
        assert edited.status_code == 200, edited.text
        current = client.get(f"/api/v1/projects/{project_id}").json()
        latest = client.get(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/draft"
        ).json()
        assert current["knowledge"][0]["processing"]["index_status"] == "stale"

        stale = _propose_binding(
            client, project_id, agent_id, latest, "使用毕业论文资料。"
        ).json()["knowledge_binding"]
        assert stale["index_status"] == "stale"
        assert stale["runnable"] is False
        assert stale["required_action"] == "rebuild_index"
        # Proposing never rebuilds the index on the user's behalf.
        after = client.get(f"/api/v1/projects/{project_id}").json()
        assert after["knowledge"][0]["processing"]["index_status"] == "stale"


def test_revision_conflict_preserves_user_work(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id, target_url, draft = _target(client, "agent")
        agent_id = draft["source"]["agent_id"]
        _knowledge(client, project_id, "毕业论文", "ORBIT marker\n")

        response = _propose_binding(
            client,
            project_id,
            agent_id,
            {"revision": draft["revision"] + 5, "etag": draft["etag"]},
            "使用毕业论文资料。",
        )
        assert response.status_code == 409, response.text
        assert client.get(f"{target_url}/draft").json() == draft
