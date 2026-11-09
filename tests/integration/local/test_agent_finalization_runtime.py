from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.wire import RunEvent
from veyra_agent_platform.local.runtime.client import RuntimeCompletion

from .test_agent_state_apply import _product
from .test_loop_resource_truth import _client, _create_project, _loop_source, _set_io
from .test_runtime_model_capability_preflight import ImageRuntimeTransport
from .test_runtime_routes import (
    ScriptedRuntimeTransport,
    _await_run,
    _run_until_settled,
)
from .verified_runtime_model import RUNTIME_TEXT_CAPABILITIES


def _source() -> dict:
    source = _set_io(
        _loop_source("Summarize supplied facts"),
        {"request": "string"},
        {"result": "string"},
    )
    source["extensions"]["veyra"].update(
        max_turns=8,
        finalization={
            "version": "1",
            "checks": ["required_fields:result"],
            "criteria": ["The result uses supplied evidence"],
            "review_images": False,
        },
    )
    return source


def _review(status: str) -> str:
    return json.dumps(
        {
            "status": status,
            "findings": [
                {
                    "criterion": 0,
                    "status": status,
                    "reason": "Public review feedback",
                    "evidence": "The supplied result",
                }
            ],
            "question": "",
            "invalidate_images": [],
        }
    )


def test_api_candidate_review_revises_and_replays_real_wire_events(
    tmp_path: Path,
) -> None:
    transport = ScriptedRuntimeTransport(
        [
            json.dumps({"action": "final", "outputs": {"result": "unsupported draft"}}),
            _review("revise"),
            json.dumps({"action": "final", "outputs": {"result": "supported result"}}),
            _review("pass"),
        ]
    )
    with _client(tmp_path, transport) as client:
        project = _create_project(client, _source())
        agent_id = project["agents"][0]["agent_id"]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent_id}/run"
        result = _run_until_settled(client, url, {"request": "Use the supplied facts"})
        assert result["status"] == "unverified", result
        assert result["result"] == {"result": "supported result"}
        assert len(transport.calls) == 4
        replay = client.get(f"{url}s/{result['run_id']}").json()
        kinds = [event["kind"] for event in replay["events"]]
        assert kinds.count("finalization.rejected") == 1
        assert kinds.count("finalization.accepted") == 1
        assert kinds.index("finalization.accepted") < kinds.index("run.completed")
        for event in replay["events"]:
            RunEvent.from_dict(event)
        accepted = next(
            event
            for event in replay["events"]
            if event["kind"] == "finalization.accepted"
        )
        assert accepted["payload"]["independent_verification"] is False


def test_api_review_failure_preserves_feedback_and_never_publishes(
    tmp_path: Path,
) -> None:
    transport = ScriptedRuntimeTransport(
        [
            json.dumps({"action": "final", "outputs": {"result": "untested"}}),
            _review("uncertain"),
            json.dumps({"action": "final", "outputs": {"result": "untested"}}),
            _review("uncertain"),
        ]
    )
    with _client(tmp_path, transport) as client:
        project = _create_project(client, _source())
        agent_id = project["agents"][0]["agent_id"]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent_id}/run"
        result = _run_until_settled(client, url, {"request": "Require actual evidence"})
        assert result["status"] == "failed", result
        assert result["error"]["code"] == "agent_finalization_uncertain"
        assert result["result"] is None
        detail = client.get(f"{url}s/{result['run_id']}").json()
        rejected = next(
            event
            for event in detail["events"]
            if event["kind"] == "finalization.rejected"
        )
        assert rejected["payload"]["findings"][0]["reason"] == "Public review feedback"
        assert not any(event["kind"] == "run.completed" for event in detail["events"])


class _DeliveryTransport(ImageRuntimeTransport):
    """Use actual native observations, not invented Entity or Artifact IDs."""

    def __init__(self) -> None:
        super().__init__()
        self.action_index = 0
        self.review_index = 0
        self.artifacts: dict[str, Any] = {}
        self.entity_id: str | None = None

    def models(self) -> tuple[str, ...]:
        return ("kimi-k3",)

    def complete(
        self, messages: Any, *, response_format: Any = None
    ) -> RuntimeCompletion:
        self.completion_calls.append((messages, response_format))
        if "read-only delivery reviewer" in str(messages[0]["content"]):
            status = "revise" if self.review_index == 1 else "pass"
            self.review_index += 1
            review = json.loads(_review(status))
            review["invalidate_images"] = (
                ["view-front"] if status == "revise" or self.review_index == 1 else []
            )
            return RuntimeCompletion(content=json.dumps(review), finish_reason="stop")

        for message in messages:
            content = message.get("content")
            if not isinstance(content, str):
                continue
            if content.startswith("Native image results."):
                self.artifacts.update(json.loads(content.partition("\n")[2]))
            elif content.startswith("Tool result for veyra.tool.entity."):
                output = json.loads(content.partition("\n")[2])
                records = output.get("records", [])
                if records:
                    self.entity_id = records[0]["entity_id"]
                elif output.get("entity_id"):
                    self.entity_id = output["entity_id"]

        index = self.action_index
        self.action_index += 1
        if index == 0:
            action = {
                "action": "ask_user",
                "question": "Choose the blue design or request a change.",
                "context": {"options": ["blue", "green", "white"]},
            }
        elif index in {1, 5}:
            names = ("view-front", "view-side", "view-open", "view-inside")
            action = {
                "action": "render_images",
                "images": {
                    name: {"prompt": f"Blue design, {name}", "regenerate": index == 5}
                    for name in (names if index == 1 else names[:1])
                },
                "outputs": {"result": {"design": "blue"}},
            }
        elif index in {2, 6}:
            action = {
                "action": "tool",
                "tool": "veyra.tool.entity.query@1.0.0",
                "arguments": {"entity_type": "tasks", "filters": {"title": "design"}},
            }
        elif index in {3, 7}:
            arguments = {
                "entity_type": "tasks",
                "payload": {
                    "title": "design",
                    "owner": "user",
                    "status": "open" if index == 3 else "done",
                    "generated_images": list(self.artifacts.values()),
                },
                "status": "open" if index == 3 else "done",
            }
            if index == 7:
                assert self.entity_id is not None
                arguments["entity_id"] = self.entity_id
            action = {
                "action": "tool",
                "tool": "veyra.tool.entity.write@1.0.0",
                "arguments": arguments,
            }
        elif index in {4, 8}:
            action = {
                "action": "final",
                "outputs": {"result": {"design": "blue"}, **self.artifacts},
            }
        else:
            raise AssertionError(f"Unexpected actor action {index}")
        return RuntimeCompletion(content=json.dumps(action), finish_reason="stop")


def test_committed_image_rework_retains_real_state_history_in_the_same_run(
    tmp_path: Path,
) -> None:
    product = _product(image_outputs=True)
    source = product.source.to_dict()
    views = ("view-front", "view-side", "view-open", "view-inside")
    veyra = source["extensions"]["veyra"]
    veyra["max_turns"] = 16
    veyra["finalization"] = {
        "version": "1",
        "checks": ["required_fields:result"],
        "criteria": ["The confirmed design and actual views support the result."],
        "review_images": True,
        "pre_render_review": True,
    }
    transport = _DeliveryTransport()
    with _client(
        tmp_path,
        transport,
        capabilities=(*RUNTIME_TEXT_CAPABILITIES, "image_generation"),
    ) as client:
        created = client.post("/api/v1/projects", json={"name": "Delivery acceptance"})
        assert created.status_code == 201, created.text
        pid = created.json()["project_id"]
        edits = client.app.state.edit_proposals
        proposal = edits.create_agent_proposal(
            pid,
            candidate={"source": source},
            conversation_id="delivery-conversation",
            operation_id="delivery-operation",
            factory_session_id="delivery-factory",
        )
        edits.apply_agent_creation_proposal(pid, proposal["proposal_id"], confirm=True)
        registry = client.app.state.model_registry
        registry.set_default(
            "image_generation", registry.list_profiles()[0].model_profile_id
        )
        url = f"/api/v1/projects/{pid}/agents/{product.source.agent_id}"
        draft = client.get(url + "/draft").json()
        committed = client.post(
            url + "/commit",
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
            json={"expected_revision": draft["revision"]},
        )
        assert committed.status_code == 200, committed.text
        version = committed.json()["version_id"]
        assert client.get(url + f"/runtime-readiness?version_id={version}").json()[
            "ready"
        ]
        started = client.post(
            url + "/run",
            json={
                "inputs": {"request": "Design and retain its image versions"},
                "source": "committed",
                "version_id": version,
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        waiting = _await_run(client, url + "/run", started.json()["run_id"])
        assert waiting["status"] == "waiting", waiting
        assert waiting["result"] is None and not transport.image_calls
        request = next(
            event
            for event in reversed(waiting["events"])
            if event["kind"] == "approval.requested"
        )
        reply = client.post(
            url + f"/runs/{waiting['run_id']}/commands",
            json={
                "command": "reply",
                "inputs": {"reply": "Use blue"},
                "expected_request_id": request["payload"]["request_id"],
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert reply.status_code == 200, reply.text
        completed = _await_run(client, url + "/run", waiting["run_id"])
        assert completed["status"] == "unverified", completed
        assert completed["version_id"] == version
        assert len(transport.image_calls) == 5
        assert [count for _, count in transport.image_calls] == [1] * 5
        assert transport.review_index == 4
        ready = next(
            event["payload"]
            for event in completed["events"]
            if event["kind"] == "finalization.completed"
            and event["payload"]["phase"] == "pre_render"
        )
        assert ready["status"] == "pass"
        assert ready["applied_image_invalidations"] == ["view-front"]
        assert [
            event["payload"]["phase"]
            for event in completed["events"]
            if event["kind"] == "finalization.started"
        ] == ["pre_render", "images", "pre_render", "images"]
        store = client.app.state.entity_store
        records = store.query(project_id=pid, entity_type="tasks")["records"]
        assert len(records) == 1 and records[0]["revision"] == 2
        history = store.history(
            project_id=pid, entity_type="tasks", entity_id=records[0]["entity_id"]
        )
        assert [entry["revision"] for entry in history["revisions"]] == [2, 1]
        actual_ids = {completed["result"][name]["artifact_id"] for name in views}
        assert {
            ref["artifact_id"] for ref in records[0]["data"]["generated_images"]
        } == actual_ids
        previous_ids = {
            ref["artifact_id"]
            for ref in history["revisions"][1]["data"]["generated_images"]
        }
        assert len(actual_ids & previous_ids) == 3
        for name in views:
            artifact = completed["result"][name]
            row, contents = client.app.state.artifacts.read_bytes(
                pid, artifact["artifact_id"]
            )
            assert row.run_id == waiting["run_id"] and contents.startswith(b"\x89PNG")
        kinds = [event["kind"] for event in completed["events"]]
        assert kinds.count("finalization.rejected") == 1
        assert kinds.count("finalization.accepted") == 1
        assert kinds.index("finalization.accepted") < kinds.index("run.completed")
        for event in completed["events"]:
            RunEvent.from_dict(event)
