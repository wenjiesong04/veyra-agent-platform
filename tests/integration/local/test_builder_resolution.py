from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tests.integration.local.test_edit_proposal_routes import _target
from tests.integration.local.test_factory_routes import (
    ScriptedKimiTransport,
    _client,
    _completion,
)


def intent(kind="agent", target_id=None, **changes):
    return {
        "intent": "edit",
        "create_kind": None,
        "multi_object": False,
        "targets": []
        if target_id is None
        else [
            {
                "kind": kind,
                "target_id": target_id,
                "basis": "mention",
                "mention": "Editable",
            }
        ],
        "instruction": "Update Editable's description.",
        "message": "I will propose a description change to Editable.",
        "plan": ["Update the description; preserve graph and permissions."],
        **changes,
    }


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_resolve_propose_confirm_apply(tmp_path: Path, kind: str):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project, url, draft = _target(client, kind)
        target_id = draft["source"][f"{kind}_id"]
        transport.completions.append(_completion(json.dumps(intent(kind, target_id))))
        response = client.post(
            f"/api/v1/projects/{project}/builder/resolve",
            json={
                "content": f"Update Editable {kind}'s description.",
            },
        )
        assert response.status_code == 200, response.text
        resolved = response.json()
        assert resolved["status"] == "resolved"
        assert resolved["targets"][0] == {
            "kind": kind,
            "target_id": target_id,
            "name": "Editable",
            "revision": draft["revision"],
            "etag": draft["etag"],
        }
        context = json.loads(transport.calls[0][0][1]["content"])
        assert context["operation"] == "resolve_intent"
        assert context["conversation"]["content"].startswith("Update Editable")
        item = context["inventory"][f"{kind}s"][0]
        assert item["draft"]["revision"] == draft["revision"]
        assert "nodes" in item and "versions" in item and "source_path" not in item
        assert context["authority"]["file_contents"] == "not_loaded"
        assert client.get(f"{url}/draft").json() == draft
        candidate = deepcopy(draft["source"])
        candidate["description"] = "Reviewed description"
        transport.completions.append(_completion(json.dumps(candidate)))
        proposal = client.post(
            f"/api/v1/projects/{project}/edit-proposals",
            json={
                "target_kind": kind,
                "target_id": target_id,
                "instruction": resolved["instruction"],
                "expected_revision": resolved["targets"][0]["revision"],
                "expected_etag": resolved["targets"][0]["etag"],
            },
        )
        assert proposal.status_code == 201, proposal.text
        assert client.get(f"{url}/draft").json() == draft
        applied = client.post(
            f"/api/v1/projects/{project}/edit-proposals/{proposal.json()['proposal_id']}/commands",
            json={"command": "apply", "confirm": True},
        )
        assert applied.status_code == 200
        assert client.get(f"{url}/draft").json()["source"] == candidate


def test_ambiguous_name_requires_chat_clarification_even_if_model_guesses(tmp_path):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project, url, draft = _target(client, "agent")
        workflow = client.post(
            f"/api/v1/projects/{project}/workflows", json={"name": "Editable"}
        ).json()
        target_id = draft["source"]["agent_id"]
        transport.completions.append(
            _completion(json.dumps(intent("agent", target_id)))
        )
        endpoint = f"/api/v1/projects/{project}/builder/resolve"
        response = client.post(
            endpoint, json={"content": "给 Editable 加质量检查"}
        ).json()
        assert response["status"] == "clarification"
        assert "agent" in response["message"] and "workflow" in response["message"]
        assert response["targets"] == []
        transport.completions.append(
            _completion(json.dumps(intent("workflow", workflow["workflow_id"])))
        )
        response = client.post(
            endpoint,
            json={
                "content": "我指的是 Workflow",
                "history": [
                    {"role": "user", "content": "给 Editable 加质量检查"},
                    {"role": "assistant", "content": response["message"]},
                ],
            },
        ).json()
        assert response["status"] == "resolved"
        assert response["targets"][0]["target_id"] == workflow["workflow_id"]
        assert client.get(f"{url}/draft").json() == draft


@pytest.mark.parametrize(
    "mode", ["discuss", "clarify", "multi", "foreign", "missing", "context"]
)
def test_no_guess_no_partial_mutation(tmp_path, mode):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project, url, draft = _target(client, "agent")
        target_id = draft["source"]["agent_id"]
        value = intent("agent", target_id)
        if mode in {"discuss", "clarify"}:
            value.update(intent=mode, targets=[])
        elif mode == "multi":
            value["multi_object"] = True
        elif mode == "foreign":
            _, _, foreign = _target(client, "agent")
            value["targets"][0]["target_id"] = foreign["source"]["agent_id"]
        elif mode == "missing":
            value["targets"][0]["mention"] = "nonexistent"
        else:
            value["targets"][0].update(basis="context", mention="")
        transport.completions.append(_completion(json.dumps(value)))
        response = client.post(
            f"/api/v1/projects/{project}/builder/resolve",
            json={"content": "What does Editable do?"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == (
            "unsupported"
            if mode == "multi"
            else "resolved"
            if mode == "discuss"
            else "clarification"
        )
        assert client.get(f"{url}/draft").json() == draft
        assert (
            client.get(
                f"/api/v1/projects/{project}/edit-proposals",
                params={"target_kind": "agent", "target_id": target_id},
            ).json()["proposals"]
            == []
        )


@pytest.mark.parametrize("kind", ["agent", "workflow", "resource"])
def test_creation_resolves_type_without_creating_objects(tmp_path, kind):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        before = client.get(f"/api/v1/projects/{project}").json()
        transport.completions.append(
            _completion(json.dumps(intent(intent="create", create_kind=kind)))
        )
        result = client.post(
            f"/api/v1/projects/{project}/builder/resolve",
            json={"content": f"帮我做一个翻译 {kind}"},
        ).json()
        if kind == "resource":
            assert result["create_kind"] == "resource"
            assert result["status"] == "unsupported"
        elif kind == "workflow":
            assert result["create_kind"] == "workflow"
            assert result["status"] == "resolved"
        else:
            assert result["create_kind"] == "agent"
            assert result["status"] == "resolved"
        assert client.get(f"/api/v1/projects/{project}").json() == before
        if kind == "agent":
            transport.completions.extend(
                [
                    _completion("Ready for a proposal."),
                ]
            )
            session = client.post(
                f"/api/v1/projects/{project}/factory/sessions",
                json={"goal": result["instruction"]},
            ).json()
            prefix = (
                f"/api/v1/projects/{project}/factory/sessions/{session['session_id']}"
            )
            proposal = client.post(f"{prefix}/generate").json()
            assert proposal["state"] == "review"
            assert client.get(f"/api/v1/projects/{project}").json() == before
            assert (
                client.post(f"{prefix}/apply-draft", json={"confirm": True}).status_code
                == 200
            )


def test_malformed_resolution_fails_closed(tmp_path):
    transport = ScriptedKimiTransport([_completion('{"intent":"apply"}')])
    with _client(tmp_path, transport) as client:
        project, url, draft = _target(client, "agent")
        response = client.post(
            f"/api/v1/projects/{project}/builder/resolve",
            json={"content": "Change Editable"},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "builder_resolution_invalid"
        assert client.get(f"{url}/draft").json() == draft


@pytest.mark.parametrize("mode", ["focus", "history", "substring", "type_substring"])
def test_current_ambiguity_cannot_be_bypassed_by_model_evidence(tmp_path, mode):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project, url, draft = _target(client, "agent")
        target_id = draft["source"]["agent_id"]
        workflow = client.post(
            f"/api/v1/projects/{project}/workflows", json={"name": "Editable"}
        ).json()
        value = intent("agent", target_id)
        request = {"content": "Change Editable"}
        if mode == "focus":
            value["targets"][0].update(basis="context", mention="")
            request["focus"] = {"kind": "agent", "target_id": target_id}
        elif mode == "history":
            request.update(
                content=f"Change workflow {workflow['workflow_id']}",
                history=[{"role": "user", "content": "Change Editable Agent"}],
            )
        elif mode == "substring":
            request["content"] = "Change EditableCopy Agent"
        else:
            request["content"] = "Change Editable for agentic research"
        transport.completions.append(_completion(json.dumps(value)))
        response = client.post(
            f"/api/v1/projects/{project}/builder/resolve", json=request
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "clarification"
        assert response.json()["targets"] == []
        assert client.get(f"{url}/draft").json() == draft


@pytest.mark.parametrize("mode", ["same_kind", "cross_kind", "history"])
def test_model_cannot_omit_an_explicitly_named_target(tmp_path, mode):
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project, url, draft = _target(client, "agent")
        kind = "workflow" if mode == "cross_kind" else "agent"
        other = client.post(
            f"/api/v1/projects/{project}/{kind}s",
            json={
                "name": "Publisher",
                **({"mode": "blank"} if kind == "agent" else {}),
            },
        ).json()
        other_url = f"/api/v1/projects/{project}/{kind}s/{other[f'{kind}_id']}"
        other_draft = client.get(f"{other_url}/draft").json()
        transport.completions.append(
            _completion(json.dumps(intent("agent", draft["source"]["agent_id"])))
        )
        request = {"content": "Update Editable Agent and Publisher descriptions."}
        if mode == "history":
            request = {
                "content": "Yes, both descriptions.",
                "history": [{"role": "user", "content": request["content"]}],
            }
        response = client.post(
            f"/api/v1/projects/{project}/builder/resolve", json=request
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "clarification"
        assert response.json()["targets"] == []
        assert client.get(f"{url}/draft").json() == draft
        assert client.get(f"{other_url}/draft").json() == other_draft
        for target_kind, target_id in (
            ("agent", draft["source"]["agent_id"]),
            (kind, other[f"{kind}_id"]),
        ):
            assert (
                client.get(
                    f"/api/v1/projects/{project}/edit-proposals",
                    params={"target_kind": target_kind, "target_id": target_id},
                ).json()["proposals"]
                == []
            )
