"""Formal Builder edits finish server-side and wait for an explicit Apply."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from veyra_agent_platform.local.factory.client import FactoryProviderError

from .test_builder_knowledge_binding import _knowledge
from .test_builder_resolution import intent
from .test_builder_resource_binding import _bind_read
from .test_edit_proposal_routes import _target
from .test_factory_routes import ScriptedKimiTransport, _client, _completion


def _turn(client, pid: str, content: str, **options):
    response = client.post(
        f"/api/v1/projects/{pid}/builder/turns",
        json={"content": content, **options},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_formal_edit_turn_persists_proposal_without_a_browser_follow_up(
    tmp_path: Path, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        pid, target_url, draft = _target(client, kind)
        target_id = draft["source"][f"{kind}_id"]
        model = client.app.state.edit_proposals.client
        original = model.complete
        timeouts = []

        def observe_timeout(*args: Any, **kwargs: Any):
            if "read_timeout" in kwargs:
                timeouts.append(kwargs["read_timeout"])
            return original(*args, **kwargs)

        monkeypatch.setattr(model, "complete", observe_timeout)
        instruction = (
            "Preserve all existing constraints.\n" * 30 + "Change description."
        )
        candidate = deepcopy(draft["source"])
        candidate["description"] = "Reviewed description change"
        transport.completions.extend(
            [
                _completion(
                    json.dumps(intent(kind, target_id, instruction=instruction))
                ),
                _completion(json.dumps(candidate)),
            ]
        )
        snapshot = _turn(client, pid, f"Update Editable {kind}'s description.")
        operation = snapshot["operations"][-1]
        assert operation["kind"] == "edit"
        assert operation["status"] == "waiting"
        assert operation["proposal_id"]
        assert operation["target_kind"] == kind
        assert operation["diagnostic"]["target_id"] == target_id
        assert operation["diagnostic"][f"{kind}_id"] == target_id
        assert [receipt["output_contract"] for receipt in operation["receipts"]] == [
            "BuilderIntentV1",
            "WorkflowSourceV1" if kind == "workflow" else "AgentSourceV1",
        ]
        assert all(row["status"] == "success" for row in operation["receipts"])
        stored = client.app.state.builder_conversations.store.operation(
            operation["operation_id"], snapshot["conversation"]["conversation_id"]
        )
        saved = json.loads(json.loads(stored["diagnostic_json"])["resolution_json"])
        assert saved["instruction"] == instruction
        assert saved["targets"][0]["revision"] == draft["revision"]
        assert saved["targets"][0]["etag"] == draft["etag"]
        assert saved["targets"][0]["target_id"] == target_id
        reference = next(
            row for row in snapshot["messages"] if row["kind"] == "proposal_reference"
        )
        assert reference["operation_id"] == operation["operation_id"]
        assert reference["payload"]["proposal_id"] == operation["proposal_id"]
        assert reference["payload"]["target_id"] == target_id
        assert reference["payload"]["target_kind"] == kind
        cid = snapshot["conversation"]["conversation_id"]
        for _ in range(2):
            resumed = client.get(
                f"/api/v1/projects/{pid}/builder/conversations/{cid}"
            ).json()
            assert resumed["operations"][-1]["proposal_id"] == operation["proposal_id"]
        assert len(transport.calls) == 2
        assert len(timeouts) == 1
        assert 0 < timeouts[0] <= model.settings.timeout_seconds
        assert client.get(f"{target_url}/draft").json() == draft
        assert client.get(f"{target_url}/versions").json()["versions"] == []
        assert client.get(f"{target_url}/runs").json()["runs"] == []
        confirmed = client.post(
            f"/api/v1/projects/{pid}/builder/conversations/{cid}/records",
            json={
                "kind": "confirm",
                "content": "Apply the reviewed edit",
                "operation_id": operation["operation_id"],
                "proposal_id": operation["proposal_id"],
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        assert client.get(f"{target_url}/draft").json() == draft
        applied = client.post(
            f"/api/v1/projects/{pid}/edit-proposals/{operation['proposal_id']}/commands",
            json={"command": "apply", "confirm": True},
        )
        assert applied.status_code == 200, applied.text
        assert client.get(f"{target_url}/draft").json()["source"] == candidate


class _TimedOutEdit(ScriptedKimiTransport):
    def complete(self, messages: object, *, response_format: object = None):
        if self.calls:
            self.calls.append((messages, response_format))
            raise FactoryProviderError(
                "factory_timeout", "Factory model request timed out"
            )
        return super().complete(messages, response_format=response_format)


def test_edit_provider_failure_belongs_to_the_operation_and_does_not_retry(
    tmp_path: Path,
) -> None:
    transport = _TimedOutEdit([])
    with _client(tmp_path, transport) as client:
        pid, target_url, draft = _target(client, "agent")
        aid = draft["source"]["agent_id"]
        transport.completions.append(_completion(json.dumps(intent("agent", aid))))
        snapshot = _turn(client, pid, "Update Editable agent's description.")
        operation = snapshot["operations"][-1]
        assert operation["status"] == "failed"
        assert operation["error_code"] == "factory_timeout"
        assert operation["diagnostic"]["stage"] == "edit_proposal"
        assert operation["diagnostic"]["agent_id"] == aid
        assert operation["proposal_id"] is None
        assert [row["status"] for row in operation["receipts"]] == ["success", "failed"]
        assert operation["receipts"][-1]["harness_mode"] == "edit_source"
        assert len(transport.calls) == 2
        cid = snapshot["conversation"]["conversation_id"]
        refreshed = client.get(
            f"/api/v1/projects/{pid}/builder/conversations/{cid}"
        ).json()
        assert refreshed["operations"][-1]["status"] == "failed"
        assert len(transport.calls) == 2
        assert client.get(f"{target_url}/draft").json() == draft


def test_edit_generation_uses_the_same_operation_request_admission(
    tmp_path: Path,
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        pid, target_url, draft = _target(client, "agent")
        aid = draft["source"]["agent_id"]
        transport.completions.append(_completion(json.dumps(intent("agent", aid))))
        snapshot = _turn(
            client, pid, "Update Editable agent's description.", request_limit=1
        )
        operation = snapshot["operations"][-1]
        assert operation["status"] == "failed"
        assert operation["error_code"] == "factory_generation_budget_exhausted"
        assert operation["diagnostic"]["stage"] == "edit_proposal"
        assert len(operation["receipts"]) == len(transport.calls) == 1
        assert operation["proposal_id"] is None
        assert client.get(f"{target_url}/draft").json() == draft


@pytest.mark.parametrize("binding", ["resource", "knowledge"])
def test_formal_edit_prefers_existing_deterministic_binding_routes(
    tmp_path: Path, binding: str
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        pid, target_url, draft = _target(client, "agent")
        aid = draft["source"]["agent_id"]
        if binding == "resource":
            _bind_read(client, pid)
            request = "让 Editable Agent 可以读取项目文件。"
        else:
            _knowledge(client, pid, "Project Reference", "Known task facts")
            request = "Let Editable agent use Project Reference."
        transport.completions.append(
            _completion(json.dumps(intent("agent", aid, instruction=request)))
        )
        snapshot = _turn(client, pid, request)
        operation = snapshot["operations"][-1]
        assert operation["status"] == "waiting", operation
        proposal = client.get(
            f"/api/v1/projects/{pid}/edit-proposals/{operation['proposal_id']}"
        ).json()
        assert f"{binding}_binding" in proposal
        assert len(operation["receipts"]) == len(transport.calls) == 1
        assert client.get(f"{target_url}/draft").json() == draft


def test_ambiguous_knowledge_stops_before_a_generic_model_edit(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        pid, target_url, draft = _target(client, "agent")
        aid = draft["source"]["agent_id"]
        _knowledge(client, pid, "Project Reference", "Current")
        _knowledge(client, pid, "Project Reference old", "Old")
        request = "Let Editable agent use Project Reference."
        transport.completions.append(
            _completion(json.dumps(intent("agent", aid, instruction=request)))
        )
        snapshot = _turn(client, pid, request)
        operation = snapshot["operations"][-1]
        assert operation["status"] == "failed"
        assert operation["error_code"] == "knowledge_mention_ambiguous"
        assert operation["proposal_id"] is None
        assert len(transport.calls) == 1
        assert client.get(f"{target_url}/draft").json() == draft


def test_unvalidated_resolution_fields_never_enter_the_saved_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        pid, _, draft = _target(client, "agent")
        aid = draft["source"]["agent_id"]
        transport.completions.append(_completion(json.dumps(intent("agent", aid))))
        resolution = client.app.state.builder_conversations.resolution
        original = resolution.resolve

        def injected(*args: Any, **kwargs: Any):
            return {**original(*args, **kwargs), "raw": "PRIVATE_UNVALIDATED_MARKER"}

        monkeypatch.setattr(resolution, "resolve", injected)
        snapshot = _turn(client, pid, "Update Editable agent's description.")
        operation = snapshot["operations"][-1]
        assert operation["status"] == "failed"
        assert operation["error_code"] == "builder_resolution_invalid"
        stored = client.app.state.builder_conversations.store.operation(
            operation["operation_id"], snapshot["conversation"]["conversation_id"]
        )
        assert "PRIVATE_UNVALIDATED_MARKER" not in stored["diagnostic_json"]
        assert len(transport.calls) == 1
