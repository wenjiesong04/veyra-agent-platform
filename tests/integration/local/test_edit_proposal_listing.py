"""Draft-edit history never mixes Builder creation proposal contracts."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7

from .test_edit_proposal_routes import _propose, _target
from .test_factory_routes import ScriptedKimiTransport, _client


def _creation(
    client: TestClient, project_id: str, kind: str, draft: dict[str, Any]
) -> dict[str, Any]:
    common = {
        "conversation_id": new_uuid7(),
        "operation_id": new_uuid7(),
        "factory_session_id": new_uuid7(),
    }
    edits = client.app.state.edit_proposals
    if kind == "agent":
        return edits.create_agent_proposal(
            project_id, candidate={"source": draft["source"]}, **common
        )
    return edits.create_workflow_proposal(
        project_id,
        candidate={"workflow": draft["source"], "companions": []},
        **common,
    )


def _list(client: TestClient, project_id: str, kind: str, target_id: str) -> dict:
    response = client.get(
        f"/api/v1/projects/{project_id}/edit-proposals",
        params={"target_kind": kind, "target_id": target_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_edit_listing_keeps_edits_and_preserves_separate_creation_history(
    tmp_path: Path, kind: str
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        pid, _, draft = _target(client, kind)
        target_id = draft["source"][f"{kind}_id"]
        creation = _creation(client, pid, kind, draft)
        store = client.app.state.edit_proposals.store
        store.mark_applied(
            creation["proposal_id"], target_id, {f"{kind}_id": target_id}
        )
        _, edit = _propose(client, transport, pid, kind, draft)
        _creation(client, pid, kind, draft)
        before = deepcopy(store.get(pid, creation["proposal_id"]))

        listed = _list(client, pid, kind, target_id)
        assert listed["schema_version"] == "1.0"
        assert [item["proposal_id"] for item in listed["proposals"]] == [
            edit["proposal_id"]
        ]
        returned = listed["proposals"][0]
        assert returned["impact"]["scope"] == "single_draft"
        assert returned["validation"]["schema_version"] == "1.0"
        assert returned["base_revision"] == draft["revision"]
        assert returned["base_etag"] == draft["etag"]
        assert store.get(pid, creation["proposal_id"]) == before
        assert len(store.list(pid, kind, target_id)) == 3
        persisted_creation = client.get(
            f"/api/v1/projects/{pid}/edit-proposals/{creation['proposal_id']}"
        )
        assert persisted_creation.status_code == 200, persisted_creation.text
        assert persisted_creation.json()["proposal_kind"] == f"create_{kind}"
        assert persisted_creation.json()["state"] == "applied"
        assert len(transport.calls) == 1


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_creation_only_target_has_empty_draft_edit_history(
    tmp_path: Path, kind: str
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        pid, _, draft = _target(client, kind)
        target_id = draft["source"][f"{kind}_id"]
        _creation(client, pid, kind, draft)
        assert _list(client, pid, kind, target_id) == {
            "schema_version": "1.0",
            "proposals": [],
        }
        assert not transport.calls


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_draft_edit_listing_keeps_other_target_and_project_isolated(
    tmp_path: Path, kind: str
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        pid, _, first = _target(client, kind)
        first_id = first["source"][f"{kind}_id"]
        response = client.post(
            f"/api/v1/projects/{pid}/{kind}s",
            json={
                "name": "Other editable target",
                **({"mode": "blank"} if kind == "agent" else {}),
            },
        )
        assert response.status_code == 201, response.text
        second_id = response.json()[f"{kind}_id"]
        second = client.get(f"/api/v1/projects/{pid}/{kind}s/{second_id}/draft").json()
        _, first_edit = _propose(client, transport, pid, kind, first)
        _, second_edit = _propose(client, transport, pid, kind, second)
        _creation(client, pid, kind, first)
        _creation(client, pid, kind, second)
        assert [
            item["proposal_id"]
            for item in _list(client, pid, kind, first_id)["proposals"]
        ] == [first_edit["proposal_id"]]
        assert [
            item["proposal_id"]
            for item in _list(client, pid, kind, second_id)["proposals"]
        ] == [second_edit["proposal_id"]]
        other_pid, _, _ = _target(client, kind)
        wrong_project = client.get(
            f"/api/v1/projects/{other_pid}/edit-proposals",
            params={"target_kind": kind, "target_id": first_id},
        )
        assert wrong_project.status_code == 422
        assert wrong_project.json()["code"] == "project_invalid"
        assert len(transport.calls) == 2


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_creation_records_do_not_consume_the_draft_edit_history_limit(
    tmp_path: Path, kind: str
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        pid, _, draft = _target(client, kind)
        target_id = draft["source"][f"{kind}_id"]
        _, edit = _propose(client, transport, pid, kind, draft)
        for _ in range(21):
            _creation(client, pid, kind, draft)
        listed = _list(client, pid, kind, target_id)
        assert [item["proposal_id"] for item in listed["proposals"]] == [
            edit["proposal_id"]
        ]
        assert len(transport.calls) == 1
