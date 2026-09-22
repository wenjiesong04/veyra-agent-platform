from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.integration.local.test_builder_resolution import intent
from tests.integration.local.test_edit_proposal_routes import _target
from tests.integration.local.test_factory_routes import (
    VALID_SEMANTIC_PLAN,
    ScriptedKimiTransport,
    _client,
    _completion,
)
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.builder.prompt import BUILDER_SYSTEM_PROMPT
from veyra_agent_platform.local.factory.client import (
    FactoryProviderError,
    KimiCompletion,
)
from veyra_agent_platform.local.factory.compiler import agent_candidate_identity
from veyra_agent_platform.local.factory.service import FactoryError


class InspectingTransport:
    def __init__(self, seen: list[list[str]]) -> None:
        self.seen = seen
        self.client: Any = None

    def models(self) -> tuple[str, ...]:
        return ("kimi-k3",)

    def complete(
        self, messages: object, *, response_format: object = None
    ) -> KimiCompletion:
        del messages, response_format
        repository = self.client.app.state.repository
        with repository.transaction() as connection:
            rows = connection.execute(
                "SELECT kind, content FROM builder_messages ORDER BY sequence"
            ).fetchall()
        self.seen.append([f"{row['kind']}:{row['content']}" for row in rows])
        raise FactoryProviderError(
            "factory_provider_error",
            "Factory model service failed",
            details={"http_status": "500"},
        )


class ResolveThenProviderError:
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, str],
        payload: dict[str, Any],
    ) -> None:
        self.code = code
        self.message = message
        self.details = details
        self.payload = payload
        self.intent_sent = False

    def models(self) -> tuple[str, ...]:
        return ("kimi-k3",)

    def complete(
        self, messages: object, *, response_format: object = None
    ) -> KimiCompletion:
        del messages
        schema = isinstance(response_format, dict)
        if schema and response_format.get("type") == "json_schema":
            raise FactoryProviderError(self.code, self.message, details=self.details)
        if not self.intent_sent:
            self.intent_sent = True
            return _completion(json.dumps(self.payload))
        return _completion("Ready for a proposal.")


def _turn(client: Any, project_id: str, **body: Any) -> Any:
    return client.post(f"/api/v1/projects/{project_id}/builder/turns", json=body)


def _messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return list(payload["messages"])


def _kinds(payload: dict[str, Any]) -> list[str]:
    return [item["kind"] for item in _messages(payload)]


def _event_kinds(payload: dict[str, Any]) -> list[str]:
    events = payload["operations"][0].get("events") or []
    return [item["kind"] for item in events]


def _assert_no_secrets(payload: dict[str, Any]) -> None:
    blob = json.dumps(payload, ensure_ascii=False)
    assert "sk-" not in blob
    assert "Authorization" not in blob
    assert BUILDER_SYSTEM_PROMPT not in blob
    assert "You are Veyra Builder" not in blob
    for message in payload["messages"]:
        assert "hidden" not in message["content"].casefold()
        for key in message["payload"]:
            assert key not in {"prompt", "system", "raw", "reasoning", "authorization"}
    for operation in payload.get("operations") or []:
        for event in operation.get("events") or []:
            dumped = json.dumps(event, ensure_ascii=False).casefold()
            assert "sk-" not in dumped
            assert "chain-of-thought" not in dumped
            assert "reasoning_content" not in dumped
            for key in event.get("facts") or {}:
                assert key not in {
                    "prompt",
                    "system",
                    "raw",
                    "reasoning",
                    "authorization",
                }
        for operation in payload.get("operations") or []:
            for receipt in operation.get("receipts") or []:
                dumped = json.dumps(receipt, ensure_ascii=False)
                assert "sk-" not in dumped
                assert "Authorization" not in dumped
                assert BUILDER_SYSTEM_PROMPT not in dumped
                assert "reasoning_content" not in dumped.casefold()
                assert "You are Veyra Builder" not in dumped


def _assert_chat_kinds(payload: dict[str, Any]) -> None:
    allowed = {"user", "assistant", "clarification", "failure", "result"}
    for kind in _kinds(payload):
        assert kind in allowed


def test_user_message_persists_before_model_call(tmp_path: Path) -> None:
    seen: list[list[str]] = []
    transport = InspectingTransport(seen)
    with _client(tmp_path, transport) as client:
        transport.client = client
        project, _, _ = _target(client, "agent")
        response = _turn(
            client,
            project,
            content="帮我生成礼物包装 Agent",
            locale="zh",
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert seen and seen[0][0].startswith("user:帮我生成礼物包装 Agent")
        assert "user" in _kinds(payload)
        assert "failure" in _kinds(payload)
        assert payload["operations"][0]["status"] == "failed"
        assert payload["conversation"]["title"] == "礼物包装 Agent"
        assert payload["conversation"]["title"] != "Chat"
        assert "builder.operation.failed" in _event_kinds(payload)
        _assert_chat_kinds(payload)
        _assert_no_secrets(payload)


def test_successful_assistant_reply_persists(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport(
        [_completion(json.dumps(intent(intent="discuss", targets=[])))]
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        payload = _turn(client, project, content="这个项目现在有什么？").json()
        assert payload["resolution"]["intent"] == "discuss"
        assert _kinds(payload)[:2] == ["user", "assistant"]
        _assert_chat_kinds(payload)
        restored = client.get(
            f"/api/v1/projects/{project}/builder/conversations/"
            f"{payload['conversation']['conversation_id']}"
        ).json()
        assert [item["content"] for item in restored["messages"]] == [
            item["content"] for item in payload["messages"]
        ]


def test_resolve_failure_keeps_user_message(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([_completion('{"intent":"apply"}')])
    with _client(tmp_path, transport) as client:
        project, _, draft = _target(client, "agent")
        payload = _turn(client, project, content="Change Editable").json()
        assert "user" in _kinds(payload)
        assert "failure" in _kinds(payload)
        assert payload["operations"][0]["status"] == "failed"
        assert payload["operations"][0]["error_code"] == "builder_resolution_invalid"
        assert (
            client.get(
                f"/api/v1/projects/{project}/agents/{draft['source']['agent_id']}/draft"
            ).json()
            == draft
        )


def test_factory_provider_failures_keep_conversation(tmp_path: Path) -> None:
    cases = (
        (
            "factory_request_invalid",
            "Factory model request was rejected",
            {"http_status": "400", "provider_error_type": "invalid_request_error"},
        ),
        (
            "factory_unauthorized",
            "Factory model credentials were rejected",
            {"http_status": "401"},
        ),
        (
            "factory_rate_limited",
            "Factory model service is rate limited",
            {"http_status": "429"},
        ),
        (
            "factory_provider_error",
            "Factory model service failed",
            {"http_status": "500"},
        ),
    )
    for code, message, details in cases:
        transport = ResolveThenProviderError(
            code,
            message,
            details,
            intent(intent="create", create_kind="agent"),
        )
        with _client(tmp_path / code, transport) as client:
            project, _, _ = _target(client, "agent")
            payload = _turn(
                client, project, content="帮我生成礼物包装 Agent", locale="zh"
            ).json()
            assert payload["messages"][0]["content"] == "帮我生成礼物包装 Agent"
            assert "failure" in _kinds(payload)
            failure = next(
                item for item in payload["messages"] if item["kind"] == "failure"
            )
            assert details["http_status"] in failure["content"]
            assert payload["operations"][0]["status"] == "failed"
            assert payload["operations"][0]["error_code"] == code
            assert payload["conversation"]["title"] == "礼物包装 Agent"
            assert payload["conversation"]["title"] != "Chat"
            assert "builder.operation.failed" in _event_kinds(payload)
            assert "proposal_reference" not in _kinds(payload)
            restored = client.get(
                f"/api/v1/projects/{project}/builder/conversations/"
                f"{payload['conversation']['conversation_id']}"
            ).json()
            assert _kinds(restored) == _kinds(payload)
            _assert_no_secrets(restored)


def test_retry_creates_new_operation_without_rewriting_failure(tmp_path: Path) -> None:
    first = ResolveThenProviderError(
        "factory_request_invalid",
        "Factory model request was rejected",
        {"http_status": "400", "provider_error_type": "invalid_request_error"},
        intent(intent="create", create_kind="agent"),
    )
    with _client(tmp_path, first) as client:
        project, _, _ = _target(client, "agent")
        failed = _turn(client, project, content="帮我生成礼物包装 Agent").json()
        conversation_id = failed["conversation"]["conversation_id"]
        failed_op = failed["operations"][0]["operation_id"]
        client.app.state.factory.client.transport = ScriptedKimiTransport(
            [
                _completion(json.dumps(intent(intent="create", create_kind="agent"))),
                _completion("Ready for a proposal."),
                _completion(json.dumps(VALID_SEMANTIC_PLAN)),
            ]
        )
        retried = _turn(
            client,
            project,
            conversation_id=conversation_id,
            retry_of=failed_op,
        ).json()
        assert retried["conversation"]["conversation_id"] == conversation_id
        assert len(retried["operations"]) == 2
        assert retried["operations"][0]["operation_id"] == failed_op
        assert retried["operations"][0]["status"] == "failed"
        assert retried["operations"][1]["retry_of"] == failed_op
        assert retried["operations"][1]["status"] == "waiting"
        assert "failure" in _kinds(retried)
        assert "proposal_reference" not in _kinds(retried)
        assert "builder.proposal.ready" in [
            item["kind"] for item in retried["operations"][1]["events"]
        ]
        assert retried["conversation"]["title"] == "礼物包装 Agent"
        assert [item["kind"] for item in retried["messages"]].count("user") == 1
        _assert_chat_kinds(retried)
        before = client.get(f"/api/v1/projects/{project}").json()
        assert before["agent_count"] == 1


def test_retry_waiting_create_agent_does_not_rewrite_review(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport(
        [
            _completion(json.dumps(intent(intent="create", create_kind="agent"))),
            _completion("Ready for a proposal."),
            _completion(json.dumps(VALID_SEMANTIC_PLAN)),
        ]
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        reviewed = _turn(client, project, content="帮我生成礼物包装 Agent").json()
        conversation_id = reviewed["conversation"]["conversation_id"]
        waiting_op = reviewed["operations"][0]["operation_id"]
        assert reviewed["operations"][0]["status"] == "waiting"
        client.app.state.factory.client.transport = ScriptedKimiTransport(
            [
                _completion(json.dumps(intent(intent="create", create_kind="agent"))),
                _completion("Ready for a proposal."),
                _completion(json.dumps(VALID_SEMANTIC_PLAN)),
            ]
        )
        retried = _turn(
            client,
            project,
            conversation_id=conversation_id,
            retry_of=waiting_op,
        )
        assert retried.status_code == 422
        assert retried.json()["code"] == "builder_retry_invalid"
        restored = client.get(
            f"/api/v1/projects/{project}/builder/conversations/{conversation_id}"
        ).json()
        assert restored["operations"][0]["operation_id"] == waiting_op
        assert restored["operations"][0]["status"] == "waiting"
        assert len(restored["operations"]) == 1
        assert client.get(f"/api/v1/projects/{project}").json()["agent_count"] == 1


def test_reject_does_not_create_an_agent(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport(
        [
            _completion(json.dumps(intent(intent="create", create_kind="agent"))),
            _completion("Ready for a proposal."),
            _completion(json.dumps(VALID_SEMANTIC_PLAN)),
        ]
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        created = _turn(client, project, content="帮我生成礼物包装 Agent").json()
        conversation_id = created["conversation"]["conversation_id"]
        rejected = client.post(
            f"/api/v1/projects/{project}/builder/conversations/{conversation_id}/records",
            json={
                "kind": "reject",
                "content": "Rejected the Blueprint. No Agent was created.",
                "operation_id": created["operations"][0]["operation_id"],
            },
        ).json()
        assert "reject" not in _kinds(rejected)
        assert rejected["operations"][0]["status"] == "rejected"
        assert "builder.proposal.rejected" in _event_kinds(rejected)
        _assert_chat_kinds(rejected)
        assert client.get(f"/api/v1/projects/{project}").json()["agent_count"] == 1
        restored = client.get(
            f"/api/v1/projects/{project}/builder/conversations/{conversation_id}"
        ).json()
        assert "reject" not in _kinds(restored)
        assert restored["operations"][0]["status"] == "rejected"


def test_confirm_apply_and_validation_records_persist(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport(
        [
            _completion(json.dumps(intent(intent="create", create_kind="agent"))),
            _completion("Ready for a proposal."),
            _completion(json.dumps(VALID_SEMANTIC_PLAN)),
        ]
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        created = _turn(client, project, content="帮我生成礼物包装 Agent").json()
        conversation_id = created["conversation"]["conversation_id"]
        operation_id = created["operations"][0]["operation_id"]
        session_id = created["operations"][0]["factory_session_id"]
        prefix = f"/api/v1/projects/{project}/builder/conversations/{conversation_id}"
        confirmed = client.post(
            f"{prefix}/records",
            json={
                "kind": "confirm",
                "content": "Confirmed the Blueprint review.",
                "operation_id": operation_id,
            },
        ).json()
        assert "confirm" not in _kinds(confirmed)
        assert "builder.proposal.confirmed" in _event_kinds(confirmed)
        assert "builder.apply.started" in _event_kinds(confirmed)
        applied = client.post(
            f"/api/v1/projects/{project}/factory/sessions/{session_id}/apply-draft",
            json={"confirm": True},
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["agent"]["name"] == "礼物包装 Agent"
        _name, expected_slug = agent_candidate_identity("礼物包装 Agent")
        assert applied.json()["agent"]["slug"] == expected_slug
        assert "Generated Agent" not in applied.json()["agent"]["name"]
        summary = client.post(
            f"{prefix}/records",
            json={
                "kind": "apply_summary",
                "content": "Draft created. Studio can open the Agent.",
                "operation_id": operation_id,
                "details": {
                    "agent_id": applied.json()["agent"]["agent_id"],
                    "agent_name": applied.json()["agent"]["name"],
                },
            },
        ).json()
        assert "apply_summary" not in _kinds(summary)
        assert summary["operations"][0]["status"] == "in_progress"
        assert "builder.apply.completed" in _event_kinds(summary)
        validation = client.post(
            f"{prefix}/records",
            json={
                "kind": "validation_summary",
                "content": "已验证。",
                "operation_id": operation_id,
                "details": {
                    "valid": "true",
                    "agent_id": applied.json()["agent"]["agent_id"],
                    "agent_name": applied.json()["agent"]["name"],
                },
            },
        ).json()
        assert "validation_summary" not in _kinds(validation)
        assert "result" in _kinds(validation)
        assert validation["messages"][-1]["kind"] == "result"
        assert "礼物包装 Agent已经创建" in validation["messages"][-1]["content"]
        assert "builder.operation.completed" in _event_kinds(validation)
        assert validation["operations"][0]["status"] == "succeeded"
        restored = client.get(prefix).json()
        assert _kinds(restored)[-1] == "result"
        _assert_chat_kinds(restored)
        immutable = client.post(
            f"{prefix}/records",
            json={
                "kind": "confirm",
                "content": "Confirmed again.",
                "operation_id": operation_id,
            },
        ).json()
        assert _event_kinds(immutable) == _event_kinds(restored)


def test_project_isolation_and_recent_activity(tmp_path: Path) -> None:
    transport = ResolveThenProviderError(
        "factory_request_invalid",
        "Factory model request was rejected",
        {"http_status": "400"},
        intent(intent="create", create_kind="agent"),
    )
    with _client(tmp_path, transport) as client:
        project_a, _, _ = _target(client, "agent")
        project_b, _, _ = _target(client, "agent")
        payload = _turn(client, project_a, content="帮我生成礼物包装 Agent").json()
        conversation_id = payload["conversation"]["conversation_id"]
        missing = client.get(
            f"/api/v1/projects/{project_b}/builder/conversations/{conversation_id}"
        )
        assert missing.status_code == 404
        assert missing.json()["code"] == "builder_conversation_not_found"
        foreign = _turn(
            client,
            project_b,
            conversation_id=conversation_id,
            content="steal this thread",
        )
        assert foreign.status_code == 404
        recent = client.get(f"/api/v1/projects/{project_a}/builder/activity").json()
        assert recent["items"][0]["kind"] == "conversation"
        assert recent["items"][0]["conversation_id"] == conversation_id
        assert recent["items"][0]["status"] == "failed"
        assert all(item["kind"] == "conversation" for item in recent["items"])
        assert "run_id" not in recent["items"][0]
        assert "run_kind" not in recent["items"][0]
        empty = client.get(f"/api/v1/projects/{project_b}/builder/activity").json()
        assert empty["items"] == []
        _assert_no_secrets(payload)


def test_builder_activity_lists_more_than_five_conversations(tmp_path: Path) -> None:
    transport = InspectingTransport([])
    with _client(tmp_path, transport) as client:
        transport.client = client
        project, _, _ = _target(client, "agent")
        ids: list[str] = []
        for index in range(6):
            payload = _turn(
                client,
                project,
                content=f"创建第 {index} 个日程提醒 Agent。",
                locale="zh",
            ).json()
            ids.append(payload["conversation"]["conversation_id"])
        recent = client.get(f"/api/v1/projects/{project}/builder/activity").json()
        assert len(recent["items"]) == 6
        assert {item["conversation_id"] for item in recent["items"]} == set(ids)
        assert all(item["kind"] == "conversation" for item in recent["items"])
        still_capped = client.get(
            f"/api/v1/projects/{project}/builder/activity?limit=2"
        ).json()
        assert len(still_capped["items"]) == 2


def test_workspace_activity_lists_chats_across_projects(tmp_path: Path) -> None:
    transport = InspectingTransport([])
    with _client(tmp_path, transport) as client:
        transport.client = client
        project_a, _, _ = _target(client, "agent")
        project_b, _, _ = _target(client, "agent")
        first = _turn(
            client, project_a, content="创建项目 A 的聊天。", locale="zh"
        ).json()
        second = _turn(
            client, project_b, content="创建项目 B 的聊天。", locale="zh"
        ).json()
        recent = client.get("/api/v1/builder/activity").json()
        ids = {item["conversation_id"] for item in recent["items"]}
        assert first["conversation"]["conversation_id"] in ids
        assert second["conversation"]["conversation_id"] in ids
        assert {item["project_id"] for item in recent["items"]} >= {
            project_a,
            project_b,
        }


def test_proposal_reference_persists_without_creating_agent(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport(
        [
            _completion(json.dumps(intent(intent="create", create_kind="agent"))),
            _completion("Ready for a proposal."),
            _completion(json.dumps(VALID_SEMANTIC_PLAN)),
        ]
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        before = client.get(f"/api/v1/projects/{project}").json()
        payload = _turn(client, project, content="帮我生成礼物包装 Agent").json()
        assert payload["factory_session"]["state"] == "review"
        assert payload["factory_session"]["candidate"]["name"] == "礼物包装 Agent"
        assert payload["conversation"]["title"] == "礼物包装 Agent"
        assert all(
            "方案已准备好" not in item["content"] for item in payload["messages"]
        )
        assert [item["kind"] for item in payload["messages"]].count("assistant") == 1
        assert "proposal_reference" not in _kinds(payload)
        assert "builder.operation.started" in _event_kinds(payload)
        events = payload["operations"][0]["events"]
        assert [item["sequence"] for item in events] == list(range(len(events)))
        kinds = _event_kinds(payload)
        assert kinds.index("builder.intent.started") < kinds.index(
            "builder.intent.resolved"
        )
        assert kinds.index("builder.semantic_plan.started") < kinds.index(
            "builder.semantic_plan.completed"
        )
        assert kinds.index("builder.capabilities.started") < kinds.index(
            "builder.capabilities.resolved"
        )
        assert kinds.index("builder.capabilities.resolved") < kinds.index(
            "builder.compile.started"
        )
        assert kinds.index("builder.compile.started") < kinds.index(
            "builder.compile.completed"
        )
        assert kinds[-1] == "builder.proposal.ready"
        assert payload["operations"][0]["target_kind"] == "agent"
        assert payload["operations"][0]["status"] == "waiting"
        _assert_chat_kinds(payload)
        assert client.get(f"/api/v1/projects/{project}").json() == before
        recorded = client.post(
            f"/api/v1/projects/{project}/builder/conversations/"
            f"{payload['conversation']['conversation_id']}/records",
            json={
                "kind": "proposal_reference",
                "content": f"Proposal {new_uuid7()}",
                "operation_id": payload["operations"][0]["operation_id"],
                "proposal_id": new_uuid7(),
            },
        )
        assert recorded.status_code == 200
        assert _event_kinds(recorded.json()).count("builder.proposal.ready") == 1
        _assert_chat_kinds(recorded.json())
        _assert_no_secrets(recorded.json())


def test_turn_sse_emits_real_operation_events(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport(
        [
            _completion(json.dumps(intent(intent="create", create_kind="agent"))),
            _completion("Ready for a proposal."),
            _completion(json.dumps(VALID_SEMANTIC_PLAN)),
        ]
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        response = client.post(
            f"/api/v1/projects/{project}/builder/turns",
            json={"content": "创建一个中英文翻译 Agent。", "locale": "zh"},
            headers={"Accept": "text/event-stream"},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        body = response.text
        assert "event: builder.event" in body
        assert "builder.semantic_plan.started" in body
        assert "event: builder.snapshot" in body
        assert "chain-of-thought" not in body.casefold()
        assert "reasoning_content" not in body


def test_failed_operation_keeps_events_and_retry_is_a_new_row(
    tmp_path: Path,
) -> None:
    transport = ResolveThenProviderError(
        "factory_provider_error",
        "Factory model service failed",
        {"http_status": "500"},
        intent(intent="create", create_kind="agent"),
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        failed = _turn(
            client, project, content="创建一个会议纪要整理 Agent。", locale="zh"
        ).json()
        failed_events = list(failed["operations"][0]["events"])
        assert failed_events[-1]["kind"] == "builder.operation.failed"
        conversation_id = failed["conversation"]["conversation_id"]
        blocked = client.post(
            f"/api/v1/projects/{project}/builder/conversations/{conversation_id}/records",
            json={
                "kind": "confirm",
                "content": "Confirmed",
                "operation_id": failed["operations"][0]["operation_id"],
            },
        ).json()
        assert [item["kind"] for item in blocked["operations"][0]["events"]] == [
            item["kind"] for item in failed_events
        ]
        client.app.state.factory.client.transport = ScriptedKimiTransport(
            [
                _completion(json.dumps(intent(intent="create", create_kind="agent"))),
                _completion("Ready for a proposal."),
                _completion(json.dumps(VALID_SEMANTIC_PLAN)),
            ]
        )
        retried = _turn(
            client,
            project,
            conversation_id=conversation_id,
            retry_of=failed["operations"][0]["operation_id"],
        ).json()
        assert retried["operations"][0]["events"][-1]["kind"] == (
            "builder.operation.failed"
        )
        assert (
            retried["operations"][1]["retry_of"]
            == failed["operations"][0]["operation_id"]
        )
        assert retried["operations"][1]["status"] == "waiting"


def test_missing_capability_keeps_failed_operation_without_creating_agent(
    tmp_path: Path,
) -> None:
    plan = json.loads(json.dumps(VALID_SEMANTIC_PLAN))
    plan["capability_intents"] = ["read GitHub issues"]
    plan["suggested_name"] = "会议纪要整理 Agent"
    transport = ScriptedKimiTransport(
        [
            _completion(json.dumps(intent(intent="create", create_kind="agent"))),
            _completion("Ready for a proposal."),
            _completion(json.dumps(plan)),
        ]
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        before = client.get(f"/api/v1/projects/{project}").json()
        payload = _turn(
            client,
            project,
            content="创建一个可以读取 GitHub 的 Agent。",
            locale="zh",
        ).json()
        assert payload["factory_session"]["state"] == "missing_capability"
        assert payload["operations"][0]["status"] == "failed"
        assert payload["operations"][0]["error_code"] == "factory_missing_capability"
        assert "builder.capabilities.resolved" in _event_kinds(payload)
        assert "builder.compile.completed" not in _event_kinds(payload)
        assert _event_kinds(payload)[-1] == "builder.operation.failed"
        assert "result" not in _kinds(payload)
        _assert_chat_kinds(payload)
        restored = client.get(
            f"/api/v1/projects/{project}/builder/conversations/"
            f"{payload['conversation']['conversation_id']}"
        ).json()
        assert _event_kinds(restored) == _event_kinds(payload)
        assert restored["operations"][0]["status"] == "failed"
        after = client.get(f"/api/v1/projects/{project}").json()
        assert after["agent_count"] == before["agent_count"]
        assert payload["conversation"]["title"] != "Chat"
        assert (
            payload["factory_session"]["missing_capabilities"][0]["proposal"][
                "executable"
            ]
            is False
        )


def test_direct_component_proposal_requires_confirmation_and_never_creates_agent(
    tmp_path: Path,
) -> None:
    direct_component_intent = intent(
        intent="create_component",
        create_kind="custom_component",
        instruction="Create a reusable text normalization component.",
        message="I can propose a reusable text normalization component.",
        plan=["Normalize the supplied string."],
        component_plan={
            "capability_requirement": "Text normalization",
            "purpose": "normalized: {{text}}",
            "operation_kind": "transform",
            "dependency_requirement": "",
            "inputs": [{"name": "text", "type": "string"}],
            "outputs": [{"name": "normalized", "type": "string"}],
        },
    )
    transport = ScriptedKimiTransport(
        [_completion(json.dumps(direct_component_intent))]
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        before = client.get(f"/api/v1/projects/{project}").json()
        snapshot = _turn(
            client,
            project,
            content="创建一个可复用的文本规范化组件。",
            locale="zh",
        ).json()
        operation = snapshot["operations"][0]
        assert operation["kind"] == "create_component"
        assert operation["status"] == "waiting"
        assert operation["proposal_id"]
        assert operation["events"][-1]["facts"]["proposal_kind"] == (
            "create_custom_component"
        )
        proposal_url = (
            f"/api/v1/projects/{project}/edit-proposals/{operation['proposal_id']}"
        )
        proposal = client.get(proposal_url)
        assert proposal.status_code == 200, proposal.text
        assert proposal.json()["state"] == "review"
        assert proposal.json()["continuation"] == "direct_component"
        assert proposal.json()["component_plan"]["implementation"]["kind"] == (
            "transform"
        )
        assert (
            client.get(f"/api/v1/projects/{project}/custom-components").json()[
                "components"
            ]
            == []
        )

        command_url = (
            f"/api/v1/projects/{project}/builder/conversations/"
            f"{snapshot['conversation']['conversation_id']}/operations/"
            f"{operation['operation_id']}/component-proposals/"
            f"{operation['proposal_id']}/commands"
        )
        denied = client.post(
            command_url,
            json={"command": "apply", "confirm": False, "locale": "zh"},
        )
        assert denied.status_code == 422
        assert client.get(proposal_url).json()["state"] == "review"

        applied = client.post(
            command_url,
            json={"command": "apply", "confirm": True, "locale": "zh"},
        )
        assert applied.status_code == 200, applied.text
        final = applied.json()
        assert final["operations"][0]["status"] == "succeeded"
        assert final["factory_session"] is None
        created = client.get(proposal_url).json()["created_component"]
        assert created["reference"].endswith("@1.0.0")
        components = client.get(f"/api/v1/projects/{project}/custom-components").json()[
            "components"
        ]
        assert len(components) == 1
        builder_version = components[0]["versions"][0]
        assert builder_version["content_hash"] == created["content_hash"]
        builder_component = client.get(
            f"/api/v1/projects/{project}/custom-components/"
            f"{created['component_id']}?version=1.0.0"
        ).json()
        assert builder_component["provenance"] == "builder"
        assert builder_component["metadata"] == {
            "builder.conversation_id": snapshot["conversation"]["conversation_id"],
            "builder.operation_id": operation["operation_id"],
            "builder.proposal_id": operation["proposal_id"],
        }
        library = client.get(f"/api/v1/projects/{project}/resources").json()
        assert any(
            resource["reference"] == created["reference"]
            and resource["availability"] == "ready"
            for resource in library["resources"]
        )
        retried = client.post(
            command_url,
            json={"command": "apply", "confirm": True, "locale": "zh"},
        )
        assert retried.status_code == 200, retried.text
        retry_component = client.get(proposal_url).json()["created_component"]
        assert retry_component["reference"] == created["reference"]
        assert (
            len(
                client.get(f"/api/v1/projects/{project}/custom-components").json()[
                    "components"
                ]
            )
            == 1
        )
        after = client.get(f"/api/v1/projects/{project}").json()
        assert after["agent_count"] == before["agent_count"]


def test_rejecting_component_proposal_creates_nothing_and_does_not_downgrade(
    tmp_path: Path,
) -> None:
    component_intent = intent(
        intent="create_component",
        create_kind="custom_component",
        instruction="Create a reusable text normalization component.",
        message="I can propose a reusable text normalization component.",
        plan=["Normalize the supplied string."],
        component_plan={
            "capability_requirement": "Text normalization",
            "purpose": "normalized: {{text}}",
            "operation_kind": "transform",
            "dependency_requirement": "",
            "inputs": [{"name": "text", "type": "string"}],
            "outputs": [{"name": "normalized", "type": "string"}],
        },
    )
    transport = ScriptedKimiTransport([_completion(json.dumps(component_intent))])
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        before = client.get(f"/api/v1/projects/{project}").json()
        snapshot = _turn(
            client, project, content="创建一个可复用的文本规范化组件。", locale="zh"
        ).json()
        operation = snapshot["operations"][0]
        command_url = (
            f"/api/v1/projects/{project}/builder/conversations/"
            f"{snapshot['conversation']['conversation_id']}/operations/"
            f"{operation['operation_id']}/component-proposals/"
            f"{operation['proposal_id']}/commands"
        )

        rejected = client.post(
            command_url,
            json={"command": "reject", "confirm": True, "locale": "zh"},
        )

        assert rejected.status_code == 200, rejected.text
        payload = rejected.json()
        assert payload["operations"][0]["status"] == "rejected"
        assert "builder.proposal.rejected" in _event_kinds(payload)
        assert (
            client.get(f"/api/v1/projects/{project}/custom-components").json()[
                "components"
            ]
            == []
        )
        assert (
            client.get(f"/api/v1/projects/{project}").json()["agent_count"]
            == (before["agent_count"])
        )
        assert "不会静默降级创建 Agent" in payload["messages"][-1]["content"]


def test_component_apply_failure_is_recorded_on_builder_operation(
    tmp_path: Path, monkeypatch: Any
) -> None:
    component_intent = intent(
        intent="create_component",
        create_kind="custom_component",
        instruction="Create a reusable text normalization component.",
        message="I can propose a reusable text normalization component.",
        plan=["Normalize the supplied string."],
        component_plan={
            "capability_requirement": "Text normalization",
            "purpose": "normalized: {{text}}",
            "operation_kind": "transform",
            "dependency_requirement": "",
            "inputs": [{"name": "text", "type": "string"}],
            "outputs": [{"name": "normalized", "type": "string"}],
        },
    )
    transport = ScriptedKimiTransport([_completion(json.dumps(component_intent))])
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        before = client.get(f"/api/v1/projects/{project}").json()
        snapshot = _turn(
            client, project, content="创建一个可复用的文本规范化组件。", locale="zh"
        ).json()
        operation = snapshot["operations"][0]
        edits = client.app.state.builder_conversations.edits

        def fail_apply(*args: Any, **kwargs: Any) -> None:
            raise FactoryError(
                "component_validation_failed",
                "The Component did not pass validation and was not published.",
            )

        monkeypatch.setattr(edits, "command", fail_apply)
        command_url = (
            f"/api/v1/projects/{project}/builder/conversations/"
            f"{snapshot['conversation']['conversation_id']}/operations/"
            f"{operation['operation_id']}/component-proposals/"
            f"{operation['proposal_id']}/commands"
        )

        failed = client.post(
            command_url,
            json={"command": "apply", "confirm": True, "locale": "zh"},
        )

        assert failed.status_code == 200, failed.text
        payload = failed.json()
        assert payload["operations"][0]["status"] == "failed"
        assert payload["operations"][0]["error_code"] == "component_validation_failed"
        assert _event_kinds(payload)[-1] == "builder.operation.failed"
        assert (
            client.get(f"/api/v1/projects/{project}/custom-components").json()[
                "components"
            ]
            == []
        )
        assert (
            client.get(f"/api/v1/projects/{project}").json()["agent_count"]
            == (before["agent_count"])
        )


def test_reusable_component_confirmation_resumes_original_agent_plan(
    tmp_path: Path,
) -> None:
    plan = json.loads(json.dumps(VALID_SEMANTIC_PLAN))
    plan.update(
        inputs=[{"name": "text", "type": "string"}],
        outputs=[{"name": "normalized", "type": "string"}],
        steps=["Normalize the text"],
        step_intents=[
            {
                "semantic_key": "normalize",
                "name": "Normalize text",
                "purpose": "normalized: {{text}}",
                "operation_kind": "transform",
                "capability_requirement": "Text normalization",
                "reusable_capability": True,
                "inputs": [{"name": "text", "type": "string"}],
                "outputs": [{"name": "normalized", "type": "string"}],
            }
        ],
    )
    transport = ScriptedKimiTransport(
        [
            _completion(json.dumps(intent(intent="create", create_kind="agent"))),
            _completion("Ready for a proposal."),
            _completion(json.dumps(plan)),
        ]
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        before = client.get(f"/api/v1/projects/{project}").json()
        snapshot = _turn(
            client,
            project,
            content="创建一个会先做文本规范化的 Agent。",
            locale="zh",
        ).json()
        operation = snapshot["operations"][0]
        assert snapshot["factory_session"]["state"] == "missing_capability"
        assert operation["proposal_id"]
        proposal_url = (
            f"/api/v1/projects/{project}/edit-proposals/{operation['proposal_id']}"
        )
        proposal = client.get(proposal_url).json()
        assert proposal["continuation"] == "agent"
        assert proposal["component_plan"]["capability_requirement"] == (
            "Text normalization"
        )

        command_url = (
            f"/api/v1/projects/{project}/builder/conversations/"
            f"{snapshot['conversation']['conversation_id']}/operations/"
            f"{operation['operation_id']}/component-proposals/"
            f"{operation['proposal_id']}/commands"
        )
        resumed = client.post(
            command_url,
            json={"command": "apply", "confirm": True, "locale": "zh"},
        )
        assert resumed.status_code == 200, resumed.text
        result = resumed.json()
        assert result["factory_session"]["state"] == "review"
        assert result["factory_session"]["candidate"]["name"] == "礼物包装 Agent"
        assert result["operations"][0]["status"] == "waiting"
        assert result["operations"][0]["proposal_id"] == operation["proposal_id"]
        published_proposal = client.get(proposal_url).json()
        component = published_proposal["created_component"]
        assert any(
            item["reference"] == component["reference"]
            for item in result["factory_session"]["resource_plan"]
        )
        assert (
            client.get(f"/api/v1/projects/{project}").json()["agent_count"]
            == (before["agent_count"])
        )

        created = client.post(
            f"/api/v1/projects/{project}/factory/sessions/"
            f"{result['factory_session']['session_id']}/apply-draft",
            json={"confirm": True},
        )
        assert created.status_code == 200, created.text
        agent_id = created.json()["agent"]["agent_id"]
        exported = client.get(
            f"/api/v1/projects/{project}/agents/{agent_id}/export"
        ).json()
        assert (
            exported["source"]["lock"][component["reference"]]
            == component["content_hash"]
        )
        assert any(
            node["component_type"] == "CustomComponent"
            and node["uses"] == component["reference"]
            for node in exported["source"]["nodes"]
        )
        assert client.get(f"/api/v1/projects/{project}").json()["agent_count"] == (
            before["agent_count"] + 1
        )


def test_meeting_notes_create_keeps_extra_outputs_and_name(tmp_path: Path) -> None:
    plan = json.loads(json.dumps(VALID_SEMANTIC_PLAN))
    plan.update(
        {
            "goal": "把会议记录整理成摘要、决定和待办。",
            "suggested_name": "会议纪要整理 Agent",
            "description": "整理会议纪要。",
            "inputs": [{"name": "会议记录", "type": "string"}],
            "outputs": [
                {"name": "摘要", "type": "string"},
                {"name": "决定", "type": "string"},
                {"name": "待办", "type": "string"},
            ],
            "steps": ["阅读记录", "提取决定", "列出待办"],
            "capability_intents": [],
            "knowledge_intents": [],
            "success_criteria": ["待办可执行"],
        }
    )
    transport = ScriptedKimiTransport(
        [
            _completion(json.dumps(intent(intent="create", create_kind="agent"))),
            _completion("Ready for a proposal."),
            _completion(json.dumps(plan)),
        ]
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        payload = _turn(
            client,
            project,
            content="创建会议纪要整理 Agent，输入会议记录，输出摘要、决定和待办事项。",
            locale="zh",
        ).json()
        assert payload["operations"][0]["status"] == "waiting"
        assert payload["conversation"]["title"] == "会议纪要整理 Agent"
        assert payload["factory_session"]["candidate"]["name"] == "会议纪要整理 Agent"
        prompt = payload["factory_session"]["blueprint"]["nodes"][1]["system_prompt"]
        assert "摘要" in prompt
        assert "决定" in prompt
        assert "待办" in prompt
        assert "包装" not in prompt
        applied = client.post(
            f"/api/v1/projects/{project}/factory/sessions/"
            f"{payload['operations'][0]['factory_session_id']}/apply-draft",
            json={"confirm": True},
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["agent"]["name"] == "会议纪要整理 Agent"
        assert applied.json()["agent"]["name"] != "Generated Agent"
        _, expected_slug = agent_candidate_identity("会议纪要整理 Agent")
        assert applied.json()["agent"]["slug"] == expected_slug

    transport = InspectingTransport([])
    with _client(tmp_path, transport) as client:
        transport.client = client
        project, _, _ = _target(client, "agent")
        payload = _turn(
            client,
            project,
            content="创建一个中英文翻译 Agent。",
            locale="zh",
        ).json()
        assert payload["operations"][0]["status"] == "failed"
        assert payload["conversation"]["title"] == "中英文翻译 Agent"
        restored = client.get(
            f"/api/v1/projects/{project}/builder/conversations/"
            f"{payload['conversation']['conversation_id']}"
        ).json()
        assert restored["conversation"]["title"] == "中英文翻译 Agent"
        recent = client.get(f"/api/v1/projects/{project}/builder/activity").json()
        assert recent["items"][0]["title"] == "中英文翻译 Agent"
        assert (
            recent["items"][0]["conversation_id"]
            == payload["conversation"]["conversation_id"]
        )


def test_success_upgrades_provisional_title_to_suggested_name(tmp_path: Path) -> None:
    plan = json.loads(json.dumps(VALID_SEMANTIC_PLAN))
    plan["suggested_name"] = "中英文翻译助手"
    plan["goal"] = "Translate between Chinese and English."
    plan["description"] = "Translate user text."
    plan["inputs"] = [{"name": "text", "type": "string"}]
    plan["outputs"] = [{"name": "translation", "type": "string"}]
    transport = ScriptedKimiTransport(
        [
            _completion(json.dumps(intent(intent="create", create_kind="agent"))),
            _completion("Ready for a proposal."),
            _completion(json.dumps(plan)),
        ]
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        payload = _turn(
            client,
            project,
            content="创建一个中英文翻译 Agent。",
            locale="zh",
        ).json()
        assert payload["operations"][0]["status"] == "waiting"
        assert payload["factory_session"]["candidate"]["name"] == "中英文翻译助手"
        assert payload["conversation"]["title"] == "中英文翻译助手"
        restored = client.get(
            f"/api/v1/projects/{project}/builder/conversations/"
            f"{payload['conversation']['conversation_id']}"
        ).json()
        assert restored["conversation"]["title"] == "中英文翻译助手"
        recent = client.get(f"/api/v1/projects/{project}/builder/activity").json()
        assert recent["items"][0]["title"] == "中英文翻译助手"


def test_retry_same_conversation_does_not_duplicate_title(tmp_path: Path) -> None:
    failed_transport = InspectingTransport([])
    with _client(tmp_path, failed_transport) as client:
        failed_transport.client = client
        project, _, _ = _target(client, "agent")
        failed = _turn(
            client,
            project,
            content="创建一个中英文翻译 Agent。",
            locale="zh",
        ).json()
        conversation_id = failed["conversation"]["conversation_id"]
        assert failed["conversation"]["title"] == "中英文翻译 Agent"
        plan = json.loads(json.dumps(VALID_SEMANTIC_PLAN))
        plan["suggested_name"] = "中英文翻译助手"
        client.app.state.factory.client.transport = ScriptedKimiTransport(
            [
                _completion(json.dumps(intent(intent="create", create_kind="agent"))),
                _completion("Ready for a proposal."),
                _completion(json.dumps(plan)),
            ]
        )
        retried = _turn(
            client,
            project,
            conversation_id=conversation_id,
            retry_of=failed["operations"][0]["operation_id"],
        ).json()
        assert retried["conversation"]["conversation_id"] == conversation_id
        assert retried["conversation"]["title"] == "中英文翻译助手"
        recent = client.get(f"/api/v1/projects/{project}/builder/activity").json()
        matches = [
            item
            for item in recent["items"]
            if item["conversation_id"] == conversation_id
        ]
        assert len(matches) == 1
        assert matches[0]["title"] == "中英文翻译助手"


def test_different_conversations_keep_independent_titles(tmp_path: Path) -> None:
    transport = InspectingTransport([])
    with _client(tmp_path, transport) as client:
        transport.client = client
        project, _, _ = _target(client, "agent")
        first = _turn(
            client,
            project,
            content="创建一个中英文翻译 Agent。",
            locale="zh",
        ).json()
        second = _turn(
            client,
            project,
            content="创建会议纪要整理 Agent，输入会议记录。",
            locale="zh",
        ).json()
        assert (
            first["conversation"]["conversation_id"]
            != second["conversation"]["conversation_id"]
        )
        assert first["conversation"]["title"] == "中英文翻译 Agent"
        assert second["conversation"]["title"] == "会议纪要整理 Agent"
        recent = client.get(f"/api/v1/projects/{project}/builder/activity").json()
        titles = {item["conversation_id"]: item["title"] for item in recent["items"]}
        assert titles[first["conversation"]["conversation_id"]] == "中英文翻译 Agent"
        assert titles[second["conversation"]["conversation_id"]] == "会议纪要整理 Agent"


def test_manual_title_is_not_overwritten_by_suggested_name(tmp_path: Path) -> None:
    failed_transport = InspectingTransport([])
    with _client(tmp_path, failed_transport) as client:
        failed_transport.client = client
        project, _, _ = _target(client, "agent")
        failed = _turn(
            client,
            project,
            content="创建一个中英文翻译 Agent。",
            locale="zh",
        ).json()
        conversation_id = failed["conversation"]["conversation_id"]
        client.app.state.builder_conversations.store.touch(
            conversation_id,
            title="手工标题",
            updated_at="2026-09-19T00:00:00Z",
        )
        plan = json.loads(json.dumps(VALID_SEMANTIC_PLAN))
        plan["suggested_name"] = "中英文翻译助手"
        client.app.state.factory.client.transport = ScriptedKimiTransport(
            [
                _completion(json.dumps(intent(intent="create", create_kind="agent"))),
                _completion("Ready for a proposal."),
                _completion(json.dumps(plan)),
            ]
        )
        retried = _turn(
            client,
            project,
            conversation_id=conversation_id,
            retry_of=failed["operations"][0]["operation_id"],
        ).json()
        assert retried["conversation"]["title"] == "手工标题"


def test_placeholder_chat_title_is_repaired_on_activity(tmp_path: Path) -> None:
    transport = InspectingTransport([])
    with _client(tmp_path, transport) as client:
        transport.client = client
        project, _, _ = _target(client, "agent")
        payload = _turn(
            client,
            project,
            content="创建一个可以调用 GitHub 读取仓库 Issue 的 Agent。",
            locale="zh",
        ).json()
        conversation_id = payload["conversation"]["conversation_id"]
        client.app.state.builder_conversations.store.touch(
            conversation_id,
            title="Chat",
            updated_at="2026-09-19T00:00:00Z",
        )
        recent = client.get(f"/api/v1/projects/{project}/builder/activity").json()
        assert recent["items"][0]["title"] != "Chat"
        assert "GitHub" in recent["items"][0]["title"]
        restored = client.get(
            f"/api/v1/projects/{project}/builder/conversations/{conversation_id}"
        ).json()
        assert restored["conversation"]["title"] != "Chat"


def test_rename_and_delete_builder_conversation(tmp_path: Path) -> None:
    transport = InspectingTransport([])
    with _client(tmp_path, transport) as client:
        transport.client = client
        project, _, _ = _target(client, "agent")
        payload = _turn(
            client,
            project,
            content="创建一个日程提醒整理 Agent。",
            locale="zh",
        ).json()
        conversation_id = payload["conversation"]["conversation_id"]
        renamed = client.patch(
            f"/api/v1/projects/{project}/builder/conversations/{conversation_id}",
            json={"title": "  日程提醒整理 Agent  "},
        )
        assert renamed.status_code == 200
        assert renamed.json()["conversation"]["title"] == "日程提醒整理 Agent"
        recent = client.get(f"/api/v1/projects/{project}/builder/activity").json()
        assert recent["items"][0]["title"] == "日程提醒整理 Agent"
        missing_title = client.patch(
            f"/api/v1/projects/{project}/builder/conversations/{conversation_id}",
            json={"title": "   "},
        )
        assert missing_title.status_code == 422
        deleted = client.delete(
            f"/api/v1/projects/{project}/builder/conversations/{conversation_id}"
        )
        assert deleted.status_code == 200
        assert deleted.json() == {
            "schema_version": "1.0",
            "conversation_id": conversation_id,
            "deleted": True,
        }
        missing = client.get(
            f"/api/v1/projects/{project}/builder/conversations/{conversation_id}"
        )
        assert missing.status_code == 404
        empty = client.get(f"/api/v1/projects/{project}/builder/activity").json()
        assert empty["items"] == []
        trashed = client.get("/api/v1/trash").json()
        item = next(item for item in trashed["items"] if item["id"] == conversation_id)
        assert item["kind"] == "conversation"
        assert item["restorable"] is True
        restored = client.post(
            f"/api/v1/trash/conversation/{conversation_id}/restore",
            json={"confirm": True},
        )
        assert restored.status_code == 200, restored.text
        assert (
            client.get(
                f"/api/v1/projects/{project}/builder/conversations/{conversation_id}"
            ).status_code
            == 200
        )
        client.delete(
            f"/api/v1/projects/{project}/builder/conversations/{conversation_id}"
        )
        purged = client.post(
            f"/api/v1/trash/conversation/{conversation_id}/purge",
            json={"confirm": True},
        )
        assert purged.status_code == 200, purged.text
        assert all(
            item["id"] != conversation_id
            for item in client.get("/api/v1/trash").json()["items"]
        )
