"""Actual API/SQLite/effects with scripted models; never a real Provider."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tests.unit.local.test_agent_loop_runtime import _tool_loop_source
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.wire import RunEvent
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.client import (
    RuntimeCompletion,
    RuntimeProviderError,
)
from veyra_agent_platform.local.runtime.service import _RunAbandoned
from veyra_agent_platform.local.runtime.tools import ToolRuntimeError

from .test_agent_finalization_runtime import _DeliveryTransport, _review, _source
from .test_agent_state_apply import _product
from .test_loop_resource_truth import _client, _create_project, _set_io
from .test_runtime_model_capability_preflight import ImageRuntimeTransport
from .test_runtime_resume import _resume
from .test_runtime_routes import (
    ScriptedRuntimeTransport,
    _await_run,
    _bind_write_resource,
    _run_until_settled,
)
from .test_workflow_version_boundary import await_workflow, save
from .verified_runtime_model import RUNTIME_TEXT_CAPABILITIES, MemorySecretStore


def _budget_request(detail: dict) -> dict:
    request = next(
        event["payload"]
        for event in reversed(detail["events"])
        if event["kind"] == "approval.requested"
    )
    assert request["kind"] == "budget"
    return request


def _command(client, url: str, run_id: str, payload: dict, *, key: str | None = None):
    return client.post(
        f"{url}s/{run_id}/commands",
        json=payload,
        headers={"Idempotency-Key": key or new_uuid7()},
    )


def _create(client, source: dict) -> tuple[str, dict]:
    project = _create_project(client, source)
    return (
        f"/api/v1/projects/{project['project_id']}/agents/{project['agents'][0]['agent_id']}/run",
        project,
    )


def test_budget_continuation_reuses_prepared_candidate_and_committed_identity(
    tmp_path: Path,
) -> None:
    source = _source()
    source["extensions"]["veyra"]["max_turns"] = 1
    transport = ScriptedRuntimeTransport(
        [
            json.dumps({"action": "final", "outputs": {"result": "accepted facts"}}),
            _review("pass"),
        ]
    )
    with _client(tmp_path, transport) as client:
        url, _ = _create(client, source)
        paused = _run_until_settled(client, url, {"request": "Use facts"})
        request = _budget_request(paused)
        assert len(transport.calls) == 1 and paused["result"] is None
        for wrong in (
            {"command": "approve"},
            {"command": "reply", "inputs": {"reply": "continue"}},
            {"command": "extend_budget", "additional_turns": 1},
        ):
            response = _command(client, url, paused["run_id"], wrong)
            assert response.status_code >= 400
        assert len(transport.calls) == 1
        key = new_uuid7()
        payload = {
            "command": "extend_budget",
            "additional_turns": 1,
            "expected_request_id": request["request_id"],
        }
        accepted = _command(client, url, paused["run_id"], payload, key=key)
        assert accepted.status_code == 200, accepted.text
        final = _await_run(client, url, paused["run_id"])
        assert final["status"] == "unverified" and final["result"] == {
            "result": "accepted facts"
        }
        assert (
            final["run_id"] == paused["run_id"]
            and final["version_id"] == paused["version_id"]
        )
        assert len(transport.calls) == 2
        assert (
            _command(client, url, paused["run_id"], payload, key=key).status_code == 200
        )
        assert len(transport.calls) == 2
        assert (
            _command(
                client,
                url,
                paused["run_id"],
                {**payload, "additional_turns": 2},
                key=key,
            ).status_code
            == 409
        )
        assert not any(event["kind"] == "tool.started" for event in final["events"])
        for event in final["events"]:
            RunEvent.from_dict(event)
        stored = client.app.state.repository.version(final["version_id"])
        assert (
            json.loads(stored["source_json"])["extensions"]["veyra"]["max_turns"] == 1
        )


def test_budget_stop_and_invalid_extensions_never_submit_another_request(
    tmp_path: Path,
) -> None:
    source = _source()
    source["extensions"]["veyra"]["max_turns"] = 1
    transport = ScriptedRuntimeTransport(
        [json.dumps({"action": "final", "outputs": {"result": "candidate"}})]
    )
    with _client(tmp_path, transport) as client:
        url, _ = _create(client, source)
        paused = _run_until_settled(client, url, {"request": "Use facts"})
        request = _budget_request(paused)
        for amount in (True, 0, 65):
            response = _command(
                client,
                url,
                paused["run_id"],
                {
                    "command": "extend_budget",
                    "additional_turns": amount,
                    "expected_request_id": request["request_id"],
                },
            )
            assert response.status_code >= 400
        stale = _command(
            client,
            url,
            paused["run_id"],
            {"command": "stop", "expected_request_id": new_uuid7()},
        )
        assert stale.status_code >= 400
        stopped = _command(
            client,
            url,
            paused["run_id"],
            {"command": "stop", "expected_request_id": request["request_id"]},
        )
        assert stopped.status_code == 200 and stopped.json()["status"] == "cancelled"
        assert len(transport.calls) == 1
        assert (
            _command(
                client,
                url,
                paused["run_id"],
                {
                    "command": "extend_budget",
                    "additional_turns": 1,
                    "expected_request_id": request["request_id"],
                },
            ).status_code
            >= 400
        )
        assert len(transport.calls) == 1


def test_concurrent_grants_consume_the_request_only_once(tmp_path: Path) -> None:
    source = _source()
    source["extensions"]["veyra"]["max_turns"] = 1
    transport = ScriptedRuntimeTransport(
        [
            json.dumps({"action": "final", "outputs": {"result": "accepted"}}),
            _review("pass"),
        ]
    )
    with _client(tmp_path, transport) as client:
        url, _ = _create(client, source)
        paused = _run_until_settled(client, url, {"request": "Use facts"})
        payload = {
            "command": "extend_budget",
            "additional_turns": 1,
            "expected_request_id": _budget_request(paused)["request_id"],
        }
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _: _command(client, url, paused["run_id"], payload), range(2)
                )
            )
        assert sum(response.status_code == 200 for response in responses) == 1
        final = _await_run(client, url, paused["run_id"])
        assert final["status"] == "unverified" and len(transport.calls) == 2
        with client.app.state.repository.transaction() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM runtime_run_commands WHERE run_id = ? "
                    "AND command_type = 'extend_budget'",
                    (paused["run_id"],),
                ).fetchone()[0]
                == 1
            )


class _WriteReviewTransport:
    def __init__(self) -> None:
        self.calls = []
        self.actors = 0
        self.reviews = 0

    def models(self):
        return ("kimi-k3",)

    def complete(self, messages, *, response_format=None):
        self.calls.append(messages)
        if "read-only delivery reviewer" in messages[0]["content"]:
            self.reviews += 1
            if self.reviews == 1:
                raise RuntimeProviderError(
                    "runtime_timeout", "Synthetic review timeout"
                )
            return RuntimeCompletion(content=_review("pass"), finish_reason="stop")
        self.actors += 1
        action = (
            {
                "action": "tool",
                "tool": "veyra.tool.filesystem.write@1.0.0",
                "arguments": {"path": "report.txt", "content": "original result"},
            }
            if self.actors == 1
            else {"action": "final", "outputs": {"result": "original result"}}
        )
        return RuntimeCompletion(content=json.dumps(action), finish_reason="stop")


def _writer_source() -> dict:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.write", "1.0.0")
    source = _set_io(
        _tool_loop_source(tool).to_dict(), {"request": "string"}, {"result": "string"}
    )
    source["extensions"]["veyra"]["finalization"] = _source()["extensions"]["veyra"][
        "finalization"
    ]
    return source


def test_review_timeout_recovers_after_successful_write_without_replaying_it(
    tmp_path: Path,
) -> None:
    transport = _WriteReviewTransport()
    with _client(tmp_path, transport) as client:
        url, project = _create(client, _writer_source())
        _bind_write_resource(client, project)
        waiting = _run_until_settled(client, url, {"request": "Write and review"})
        request = next(
            event["payload"]
            for event in reversed(waiting["events"])
            if event["kind"] == "approval.requested"
        )
        approved = _command(
            client,
            url,
            waiting["run_id"],
            {"command": "approve", "expected_request_id": request["request_id"]},
        )
        assert approved.status_code == 200, approved.text
        failed = _await_run(client, url, waiting["run_id"])
        assert failed["error"]["code"] == "runtime_timeout"
        path = Path(project["root_path"]) / "report.txt"
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        assert transport.actors == 2 and transport.reviews == 1
        recovered = _resume(client, url, failed)
        assert recovered.status_code == 200, recovered.text
        child = _await_run(client, url, recovered.json()["run_id"])
        assert child["status"] == "unverified" and child["result"] == {
            "result": "original result"
        }
        assert (
            child["run_id"] != failed["run_id"]
            and child["version_id"] == failed["version_id"]
        )
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before
        assert transport.actors == 2 and transport.reviews == 2
        assert not any(event["kind"] == "tool.started" for event in child["events"])
        assert client.get(f"{url}s/{failed['run_id']}").json()["status"] == "failed"
        with client.app.state.repository.transaction() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM runtime_tool_calls WHERE run_id = ? "
                    "AND receipt_json IS NOT NULL",
                    (failed["run_id"],),
                ).fetchone()[0]
                == 1
            )


def test_unknown_write_effect_after_checkpoint_is_not_replayed(tmp_path: Path) -> None:
    effects = []

    def uncertain_write(**kwargs):
        effects.append(kwargs["values"])
        raise ToolRuntimeError(
            "tool_unavailable",
            "Outcome cannot be established",
            receipt={"outcome": "failed"},
        )

    transport = _WriteReviewTransport()
    with _client(
        tmp_path,
        transport,
        tool_adapters={"veyra.runtime.filesystem.write": uncertain_write},
    ) as client:
        url, project = _create(client, _writer_source())
        _bind_write_resource(client, project)
        waiting = _run_until_settled(client, url, {"request": "Write and review"})
        assert (
            _command(client, url, waiting["run_id"], {"command": "approve"}).status_code
            == 200
        )
        failed = _await_run(client, url, waiting["run_id"])
        assert failed["status"] == "failed" and len(effects) == 1
        rejected = _resume(client, url, failed)
        assert (
            rejected.status_code >= 400
            and rejected.json()["code"] == "resume_effect_unsafe"
        )
        assert len(effects) == 1 and transport.actors == 1


def test_initial_inputs_cannot_inject_a_run_budget(tmp_path: Path) -> None:
    transport = ScriptedRuntimeTransport([])
    with _client(tmp_path, transport) as client:
        url, _ = _create(client, _source())
        response = client.post(
            url,
            json={
                "inputs": {
                    "request": "Facts",
                    "$agent_loop": {"budget": {"limit": 999}},
                }
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert response.status_code >= 400 and not transport.calls


def test_budget_extension_never_approves_a_later_write(tmp_path: Path) -> None:
    source = _writer_source()
    source["extensions"]["veyra"]["max_turns"] = 1
    actions = [
        {
            "action": "tool",
            "tool": "veyra.tool.filesystem.write@1.0.0",
            "arguments": {"path": name, "content": "allowed only after approval"},
        }
        for name in ("first.txt", "second.txt")
    ]
    transport = ScriptedRuntimeTransport([json.dumps(action) for action in actions])
    with _client(tmp_path, transport) as client:
        url, project = _create(client, source)
        _bind_write_resource(client, project)
        first = _run_until_settled(client, url, {"request": "Write after approval"})
        assert (
            _command(client, url, first["run_id"], {"command": "approve"}).status_code
            == 200
        )
        paused = _await_run(client, url, first["run_id"])
        request = _budget_request(paused)
        response = _command(
            client,
            url,
            first["run_id"],
            {
                "command": "extend_budget",
                "additional_turns": 1,
                "expected_request_id": request["request_id"],
            },
        )
        assert response.status_code == 200, response.text
        second = _await_run(client, url, first["run_id"])
        request = next(
            event["payload"]
            for event in reversed(second["events"])
            if event["kind"] == "approval.requested"
        )
        assert request["kind"] == "tool_permission"
        root = Path(project["root_path"])
        assert (root / "first.txt").is_file() and not (root / "second.txt").exists()
        assert len(transport.calls) == 2


def _commit(client, url: str) -> dict:
    draft = client.get(url + "/draft").json()
    response = client.post(
        url + "/commit",
        json={"expected_revision": draft["revision"]},
        headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_parent_workflow_budget_forwarding_and_atomic_rollback(
    tmp_path: Path, monkeypatch
) -> None:
    source = _source()
    source["extensions"]["veyra"]["max_turns"] = 1
    transport = ScriptedRuntimeTransport(
        [
            json.dumps({"action": "final", "outputs": {"result": "accepted"}}),
            _review("pass"),
        ]
    )
    with _client(tmp_path, transport) as client:
        agent_run_url, project = _create(client, source)
        agent_url = agent_run_url.removesuffix("/run")
        version = _commit(client, agent_url)
        p, a = project["project_id"], project["agents"][0]["agent_id"]
        created = client.post(
            f"/api/v1/projects/{p}/workflows", json={"name": "Budget workflow"}
        ).json()
        url = f"/api/v1/projects/{p}/workflows/{created['workflow_id']}"
        draft = client.get(url + "/draft").json()
        ref = f"{a}@{version['version_id']}"
        draft["source"].update(
            inputs={"request": "string"},
            outputs={"result": "string"},
            nodes=[
                {"id": "start", "component_type": "Start"},
                {
                    "id": "call",
                    "component_type": "AgentCall",
                    "agent_ref": ref,
                    "input_mapping": {"request": "request"},
                    "output_mapping": {"result": "result"},
                },
                {"id": "output", "component_type": "Output", "output_name": "result"},
            ],
            transitions=[
                {"from": "start", "port": "next", "to": "call"},
                {"from": "call", "port": "next", "to": "output"},
            ],
            lock={ref: version["source_hash"]},
            ui={
                "positions": {
                    "start": {"x": 0, "y": 0},
                    "call": {"x": 100, "y": 0},
                    "output": {"x": 200, "y": 0},
                }
            },
        )
        save(client, url, draft)
        started = client.post(
            url + "/run",
            json={"inputs": {"request": "Facts"}},
            headers={"Idempotency-Key": new_uuid7()},
        ).json()
        paused = await_workflow(client, url, started["run_id"])
        assert paused["waiting"]["kind"] == "budget"
        wait = paused["waiting"]
        assert wait["context"]["budget"]["remaining"] == 0
        payload = {
            "command": "extend_budget",
            "additional_turns": 1,
            "expected_request_id": wait["request_id"],
        }
        runtime = client.app.state.workflow_runtime
        consume = runtime._consume_wait

        def rollback(*args, **kwargs):
            from veyra_agent_platform.local.runtime.service import RuntimeError

            consume(*args, **kwargs)
            raise RuntimeError("test_rollback", "Synthetic atomic rollback")

        monkeypatch.setattr(runtime, "_consume_wait", rollback)
        response = client.post(
            f"{url}/runs/{paused['run_id']}/commands",
            json=payload,
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert response.status_code >= 400 and len(transport.calls) == 1
        assert (
            client.get(f"{agent_url}/runs/{wait['child_run_id']}").json()["status"]
            == "waiting"
        )
        monkeypatch.setattr(runtime, "_consume_wait", consume)
        assert (
            client.post(
                f"{url}/runs/{paused['run_id']}/commands",
                json={"command": "approve", "expected_request_id": wait["request_id"]},
                headers={"Idempotency-Key": new_uuid7()},
            ).status_code
            >= 400
        )
        response = client.post(
            f"{url}/runs/{paused['run_id']}/commands",
            json=payload,
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert response.status_code == 200, response.text
        final = await_workflow(client, url, paused["run_id"])
        assert final["status"] == "unverified" and final["result"] == {
            "result": "accepted"
        }
        assert len(transport.calls) == 2
        assert (
            len(final["children"]) == 1
            and final["children"][0]["child_run_id"] == wait["child_run_id"]
        )


def test_image_review_recovery_retains_four_artifacts_and_entity_revision(
    tmp_path: Path,
) -> None:
    class Transport(_DeliveryTransport):
        failed = False

        def complete(self, messages, *, response_format=None):
            if (
                "read-only delivery reviewer" in str(messages[0]["content"])
                and self.image_calls
                and not self.failed
            ):
                self.failed = True
                self.review_index += 1
                self.completion_calls.append((messages, response_format))
                raise RuntimeProviderError(
                    "runtime_timeout", "Synthetic image review timeout"
                )
            return super().complete(messages, response_format=response_format)

    product = _product(image_outputs=True)
    source = product.source.to_dict()
    source["extensions"]["veyra"]["max_turns"] = 16
    source["extensions"]["veyra"]["finalization"] = {
        "version": "1",
        "checks": ["required_fields:result"],
        "criteria": ["Confirmed design and actual views"],
        "review_images": True,
        "pre_render_review": True,
    }
    transport = Transport()
    with _client(
        tmp_path,
        transport,
        capabilities=(*RUNTIME_TEXT_CAPABILITIES, "image_generation"),
    ) as client:
        project = client.post(
            "/api/v1/projects", json={"name": "Recovery delivery"}
        ).json()
        p = project["project_id"]
        edits = client.app.state.edit_proposals
        proposal = edits.create_agent_proposal(
            p,
            candidate={"source": source},
            conversation_id="synthetic",
            operation_id="synthetic",
            factory_session_id="synthetic",
        )
        edits.apply_agent_creation_proposal(p, proposal["proposal_id"], confirm=True)
        registry = client.app.state.model_registry
        registry.set_default(
            "image_generation", registry.list_profiles()[0].model_profile_id
        )
        url = f"/api/v1/projects/{p}/agents/{product.source.agent_id}/run"
        waiting = _run_until_settled(client, url, {"request": "Retain images"})
        request = next(
            event["payload"]
            for event in reversed(waiting["events"])
            if event["kind"] == "approval.requested"
        )
        assert (
            _command(
                client,
                url,
                waiting["run_id"],
                {
                    "command": "reply",
                    "inputs": {"reply": "Blue confirmed"},
                    "expected_request_id": request["request_id"],
                },
            ).status_code
            == 200
        )
        failed = _await_run(client, url, waiting["run_id"])
        assert failed["status"] == "failed" and len(transport.image_calls) == 4
        actor_count = transport.action_index
        assert transport.entity_id is not None
        before = client.app.state.entity_store.read(p, transport.entity_id)
        resumed = _resume(client, url, failed)
        assert resumed.status_code == 200, resumed.text
        final = _await_run(client, url, resumed.json()["run_id"])
        assert final["status"] == "unverified" and final["result"]
        assert transport.action_index == actor_count and len(transport.image_calls) == 4
        after = client.app.state.entity_store.read(p, transport.entity_id)
        assert dict(before) == dict(after)


def test_committed_budget_grant_survives_restart_before_worker_scheduling(
    tmp_path: Path, monkeypatch
) -> None:
    source = _source()
    source["extensions"]["veyra"]["max_turns"] = 1
    transport = ScriptedRuntimeTransport(
        [
            json.dumps({"action": "final", "outputs": {"result": "accepted"}}),
            _review("pass"),
        ]
    )
    secrets = MemorySecretStore()
    with _client(tmp_path, transport, secret_store=secrets) as client:
        url, _ = _create(client, source)
        paused = _run_until_settled(client, url, {"request": "Facts"})
        request = _budget_request(paused)
        monkeypatch.setattr(
            client.app.state.runtime, "_schedule_execution", lambda *args: None
        )
        accepted = _command(
            client,
            url,
            paused["run_id"],
            {
                "command": "extend_budget",
                "additional_turns": 1,
                "expected_request_id": request["request_id"],
            },
        )
        assert accepted.status_code == 200 and len(transport.calls) == 1
    with _client(tmp_path, transport, secret_store=secrets) as restarted:
        interrupted = restarted.get(f"{url}s/{paused['run_id']}").json()
        assert interrupted["status"] == "interrupted"
        resumed = _resume(restarted, url, interrupted)
        assert resumed.status_code == 200, resumed.text
        final = _await_run(restarted, url, resumed.json()["run_id"])
        assert final["status"] == "unverified" and len(transport.calls) == 2
        latest = next(
            event["payload"]["budget"]
            for event in reversed(final["events"])
            if "budget" in event["payload"]
        )
        assert latest["used"] == latest["limit"] == 2


def test_completed_image_checkpoint_without_finalization_never_regenerates(
    tmp_path: Path, monkeypatch
) -> None:
    class Transport(ImageRuntimeTransport):
        def models(self):
            return ("kimi-k3",)

        def complete(self, messages, *, response_format=None):
            self.completion_calls.append((messages, response_format))
            return RuntimeCompletion(
                content=json.dumps({"action": "final", "outputs": {"result": "blue"}}),
                finish_reason="stop",
            )

    source = _source()
    source["extensions"]["veyra"].pop("finalization")
    source["outputs"]["view"] = {"type": "artifact", "artifact_kind": "image"}
    transport, secrets = Transport(), MemorySecretStore()
    capabilities = (*RUNTIME_TEXT_CAPABILITIES, "image_generation")
    with _client(
        tmp_path, transport, secret_store=secrets, capabilities=capabilities
    ) as client:
        registry = client.app.state.model_registry
        registry.set_default(
            "image_generation", registry.list_profiles()[0].model_profile_id
        )
        url, _ = _create(client, source)
        runtime = client.app.state.runtime
        save_checkpoint = runtime._checkpoint_execution
        checkpointed = threading.Event()

        def interrupt(*args, **kwargs):
            save_checkpoint(*args, **kwargs)
            state = args[4].get("$agent_loop") or {}
            if state.get("render_cache", {}).get("view") and not state.get(
                "completed_outputs"
            ):
                checkpointed.set()
                raise _RunAbandoned()

        monkeypatch.setattr(runtime, "_checkpoint_execution", interrupt)
        started = client.post(
            url,
            json={"inputs": {"request": "One image"}},
            headers={"Idempotency-Key": new_uuid7()},
        ).json()
        assert checkpointed.wait(5)
        assert len(transport.image_calls) == 1
    with _client(
        tmp_path, transport, secret_store=secrets, capabilities=capabilities
    ) as restarted:
        interrupted = restarted.get(f"{url}s/{started['run_id']}").json()
        assert interrupted["status"] == "interrupted"
        resumed = _resume(restarted, url, interrupted)
        assert resumed.status_code == 200, resumed.text
        final = _await_run(restarted, url, resumed.json()["run_id"])
        assert (
            final["status"] == "unverified"
            and final["result"]["view"]["kind"] == "artifact"
        )
        assert len(transport.image_calls) == len(transport.completion_calls) == 1
