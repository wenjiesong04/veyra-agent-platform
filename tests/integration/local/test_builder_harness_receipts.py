from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from tests.integration.local.test_builder_conversations import (
    _assert_no_secrets,
    _turn,
)
from tests.integration.local.test_builder_resolution import intent
from tests.integration.local.test_edit_proposal_routes import _target
from tests.integration.local.test_factory_routes import (
    ScriptedKimiTransport,
    _client,
    _completion,
    _project,
)
from veyra_agent_platform.local.builder.prompt import BUILDER_SYSTEM_PROMPT
from veyra_agent_platform.local.factory.client import (
    FactoryProviderError,
    KimiCompletion,
)
from veyra_agent_platform.local.factory.config import FactorySettings


@pytest.fixture(autouse=True)
def isolate_factory_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("VEYRA_FACTORY_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("VEYRA_FACTORY_MODEL_ID", raising=False)


class PreparedReceiptTransport:
    def __init__(self) -> None:
        self.seen: list[list[str]] = []
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
                """SELECT invocation_kind, status FROM builder_harness_receipts
                   ORDER BY sequence"""
            ).fetchall()
        self.seen.append([f"{row['invocation_kind']}:{row['status']}" for row in rows])
        raise FactoryProviderError(
            "factory_provider_error",
            "Factory model service failed",
            details={"http_status": "500"},
        )


class ResolveThenGenerateError:
    def __init__(self, code: str, message: str, details: dict[str, str]) -> None:
        self.code = code
        self.message = message
        self.details = details
        self.intent_sent = False

    def models(self) -> tuple[str, ...]:
        return ("kimi-k3",)

    def complete(
        self, messages: object, *, response_format: object = None
    ) -> KimiCompletion:
        del messages
        schema = (
            isinstance(response_format, dict)
            and response_format.get("type") == "json_schema"
        )
        if schema:
            raise FactoryProviderError(self.code, self.message, details=self.details)
        if not self.intent_sent:
            self.intent_sent = True
            return _completion(json.dumps(intent(intent="create", create_kind="agent")))
        raise FactoryProviderError(self.code, self.message, details=self.details)


def _receipts(payload: dict[str, Any], index: int = -1) -> list[dict[str, Any]]:
    return list(payload["operations"][index].get("receipts") or [])


def _kinds(payload: dict[str, Any]) -> list[str]:
    return [item["invocation_kind"] for item in _receipts(payload)]


def test_receipt_is_prepared_before_provider_request(tmp_path: Path) -> None:
    transport = PreparedReceiptTransport()
    with _client(tmp_path, transport) as client:
        transport.client = client
        project, _, _ = _target(client, "agent")
        payload = _turn(client, project, content="帮我生成礼物包装 Agent").json()
        assert transport.seen == [["resolve_intent:prepared"]]
        receipts = _receipts(payload)
        assert len(receipts) == 1
        assert receipts[0]["status"] == "failed"
        assert receipts[0]["invocation_kind"] == "resolve_intent"
        assert receipts[0]["failure_stage"] == "provider_request"
        _assert_no_secrets(payload)


def test_success_finalizes_resolve_and_interview(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport(
        [
            _completion(json.dumps(intent(intent="create", create_kind="agent"))),
            _completion("Ready for a proposal."),
        ]
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        payload = _turn(client, project, content="帮我生成礼物包装 Agent").json()
        receipts = _receipts(payload)
        assert _kinds(payload) == [
            "resolve_intent",
            "interview",
            "semantic_plan",
            "semantic_plan",
        ]
        assert [item["sequence"] for item in receipts] == [0, 1, 2, 3]
        assert {item["status"] for item in receipts} == {"success"}
        assert receipts[1]["output_contract"] != "AgentSemanticPlanV1"
        assert receipts[0]["provider_id"] == "moonshot"
        assert receipts[0]["model"] == "kimi-k3"
        assert "knowledge_contents" in receipts[0]["excluded_categories"]
        assert BUILDER_SYSTEM_PROMPT not in json.dumps(receipts)
        assert "帮我生成礼物包装 Agent" not in json.dumps(receipts)
        _assert_no_secrets(payload)


@pytest.mark.parametrize(
    ("code", "message", "details"),
    [
        (
            "factory_unauthorized",
            "Factory model credentials were rejected",
            {"http_status": "401"},
        ),
        (
            "factory_forbidden",
            "Factory model request was forbidden",
            {"http_status": "403"},
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
    ],
)
def test_provider_failure_preserves_safe_receipt(
    tmp_path: Path, code: str, message: str, details: dict[str, str]
) -> None:
    transport = ResolveThenGenerateError(code, message, details)
    with _client(tmp_path / code, transport) as client:
        project, _, _ = _target(client, "agent")
        payload = _turn(client, project, content="帮我生成礼物包装 Agent").json()
        receipts = _receipts(payload)
        assert [item["invocation_kind"] for item in receipts] == [
            "resolve_intent",
            "interview",
        ]
        failed = receipts[-1]
        assert failed["status"] == "failed"
        assert failed["error_code"] == code
        assert failed["failure_stage"] == "provider_request"
        blob = json.dumps(payload)
        assert "Authorization" not in blob
        assert "sk-" not in blob
        assert BUILDER_SYSTEM_PROMPT not in blob
        assert "reasoning_content" not in blob.casefold()
        assert "moonshot flavored" not in blob.casefold()
        restored = client.get(
            f"/api/v1/projects/{project}/builder/conversations/"
            f"{payload['conversation']['conversation_id']}"
        ).json()
        assert _receipts(restored) == receipts
        nested = client.get(
            f"/api/v1/projects/{project}/builder/conversations/"
            f"{payload['conversation']['conversation_id']}/operations/"
            f"{payload['operations'][0]['operation_id']}/receipts"
        ).json()
        assert nested["receipts"] == receipts


def test_generate_records_planning_and_coverage_receipts(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport(
        [
            _completion(json.dumps(intent(intent="create", create_kind="agent"))),
            _completion("Ready for a proposal."),
        ]
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        payload = _turn(client, project, content="帮我生成礼物包装 Agent").json()
        receipts = _receipts(payload)
        assert [item["invocation_kind"] for item in receipts] == [
            "resolve_intent",
            "interview",
            "semantic_plan",
            "semantic_plan",
        ]
        assert all(item["status"] == "success" for item in receipts)
        assert payload["operations"][0]["status"] == "waiting"
        assert [item["output_contract"] for item in receipts[-2:]] == [
            "TaskStructureV1",
            "TaskCoverageV1",
        ]


def test_snapshot_hash_is_stable_until_project_metadata_changes(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport(
        [
            _completion(json.dumps(intent(intent="discuss", targets=[]))),
            _completion(json.dumps(intent(intent="discuss", targets=[]))),
            _completion(json.dumps(intent(intent="discuss", targets=[]))),
        ]
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        first = _turn(client, project, content="这个项目现在有什么？").json()
        conversation_id = first["conversation"]["conversation_id"]
        second = _turn(
            client,
            project,
            conversation_id=conversation_id,
            content="还缺什么能力？",
        ).json()
        first_hash = _receipts(first)[0]["project_snapshot_hash"]
        second_hash = _receipts(second)[0]["project_snapshot_hash"]
        assert first_hash == second_hash
        assert first_hash
        created = client.post(
            f"/api/v1/projects/{project}/agents",
            json={"name": "Hash Probe Agent", "mode": "blank"},
        )
        assert created.status_code == 201, created.text
        third = _turn(
            client,
            project,
            conversation_id=conversation_id,
            content="项目现在叫什么？",
        ).json()
        assert _receipts(third)[0]["project_snapshot_hash"] != first_hash


def test_completed_receipt_is_immutable_and_recheck_does_not_rewrite(
    tmp_path: Path,
) -> None:
    transport = ScriptedKimiTransport(
        [
            _completion(json.dumps(intent(intent="create", create_kind="agent"))),
            _completion("Ready for a proposal."),
        ]
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        payload = _turn(client, project, content="帮我生成礼物包装 Agent").json()
        receipts = _receipts(payload)
        store = client.app.state.builder_conversations.store
        with pytest.raises(ValueError, match="immutable"):
            store.finalize_receipt(
                receipts[0]["receipt_id"],
                status="failed",
                completed_at="2099-01-01T00:00:00Z",
            )
        factory = client.app.state.factory
        profile = factory.resolved_capability_profile()
        factory.profiles.put(
            replace(
                profile,
                status="known",
                source="probe",
                probed=True,
                checked_at="2099-01-01T00:00:00Z",
            )
        )
        restored = client.get(
            f"/api/v1/projects/{project}/builder/conversations/"
            f"{payload['conversation']['conversation_id']}"
        ).json()
        assert _receipts(restored) == receipts


def test_cross_project_receipt_read_is_rejected(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport(
        [_completion(json.dumps(intent(intent="discuss", targets=[])))]
    )
    with _client(tmp_path, transport) as client:
        project, _, _ = _target(client, "agent")
        payload = _turn(client, project, content="这个项目现在有什么？").json()
        other = _project(client)
        conversation_id = payload["conversation"]["conversation_id"]
        operation_id = payload["operations"][0]["operation_id"]
        missing = client.get(
            f"/api/v1/projects/{other}/builder/conversations/{conversation_id}"
            f"/operations/{operation_id}/receipts"
        )
        assert missing.status_code == 404
        hidden = client.get(
            f"/api/v1/projects/{other}/builder/conversations/{conversation_id}"
        )
        assert hidden.status_code == 404


def test_retry_creates_new_receipts_and_preserves_failed_history(
    tmp_path: Path,
) -> None:
    first = ResolveThenGenerateError(
        "factory_rate_limited",
        "Factory model service is rate limited",
        {"http_status": "429"},
    )
    with _client(tmp_path, first) as client:
        project, _, _ = _target(client, "agent")
        failed = _turn(client, project, content="帮我生成礼物包装 Agent").json()
        conversation_id = failed["conversation"]["conversation_id"]
        failed_op = failed["operations"][0]["operation_id"]
        failed_receipts = _receipts(failed)
        assert failed_receipts[-1]["status"] == "failed"
        client.app.state.factory.client.transport = ScriptedKimiTransport(
            [
                _completion(json.dumps(intent(intent="create", create_kind="agent"))),
                _completion("Ready for a proposal."),
            ]
        )
        retried = _turn(
            client,
            project,
            conversation_id=conversation_id,
            retry_of=failed_op,
        ).json()
        assert retried["operations"][0]["receipts"] == failed_receipts
        assert retried["operations"][1]["receipts"]
        retried_id = retried["operations"][1]["receipts"][0]["receipt_id"]
        assert retried_id != failed_receipts[0]["receipt_id"]
        assert retried["operations"][1]["receipts"][-1]["status"] == "success"


def test_task_planning_receives_real_capability_names_without_graph_descriptors(
    tmp_path: Path,
) -> None:
    transport = ScriptedKimiTransport([])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        catalog = client.get("/api/v1/resources").json()["resources"]
        allowed_kinds = {"tool", "mcp_tool", "skill", "policy"}
        expected = {
            item["reference"]: item
            for item in catalog
            if item["factory_selectable"] and item["kind"] in allowed_kinds
        }
        graph_references = {
            item["reference"] for item in catalog if item["kind"] == "component"
        }
        assert "veyra.component.model@1.0.0" in graph_references
        assert "veyra.component.transform@1.0.0" in graph_references

        messages = client.app.state.factory.harness.messages(
            project_id, "plan_task", schema={"type": "object"}
        )
        context = json.loads(messages[1]["content"])
        received = {item["reference"]: item for item in context["resources"]}
        assert received.keys() == expected.keys()
        assert graph_references.isdisjoint(received)
        for reference, resource in received.items():
            assert resource["capabilities"] == expected[reference].get(
                "capabilities", []
            )
            assert resource["content_hash"] == expected[reference]["content_hash"]
            assert resource["factory_selectable"] is True
        assert received["veyra.tool.web.search@1.0.0"]["capabilities"] == ["web_search"]
        assert received["veyra.skill.research-brief@1.0.0"]["capabilities"] == [
            "research_planning"
        ]
        assert transport.calls == []


def test_task_planning_keeps_metadata_boundary_and_other_harness_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    credential_marker = "TEST_ONLY_CREDENTIAL_NOT_FOR_BUILDER_CONTEXT"
    knowledge_marker = "TEST_KNOWLEDGE_CONTENT_NOT_FOR_BUILDER_CONTEXT"
    file_marker = "TEST_FILE_CONTENT_NOT_FOR_BUILDER_CONTEXT"
    monkeypatch.setenv("VEYRA_TEST_HARNESS_CREDENTIAL", credential_marker)
    transport = ScriptedKimiTransport([])
    with _client(
        tmp_path,
        transport,
        factory_settings=FactorySettings(
            model_api_key_env="VEYRA_TEST_HARNESS_CREDENTIAL"
        ),
    ) as client:
        project_id = _project(client)
        knowledge = client.post(
            f"/api/v1/projects/{project_id}/knowledge",
            json={"name": "Fixture brief", "text": knowledge_marker},
        )
        assert knowledge.status_code == 201, knowledge.text
        uploaded = client.post(
            f"/api/v1/projects/{project_id}/files/materialize",
            data={"relative_path": "assets/fixture.txt"},
            files={"file": ("fixture.txt", file_marker.encode(), "text/plain")},
        )
        assert uploaded.status_code == 201, uploaded.text
        harness = client.app.state.factory.harness
        plan = json.loads(
            harness.messages(project_id, "plan_task", schema={"type": "object"})[1][
                "content"
            ]
        )
        assert plan["inventory"]["knowledge"][0]["name"] == "Fixture brief"
        assert "assets/fixture.txt" in {item["path"] for item in plan["files"]}
        assert plan["authority"]["file_contents"] == "not_loaded"
        assert plan["authority"]["runtime_execution"] == "not_performed"
        original_resources = {
            item["reference"]: item
            for item in client.app.state.factory.catalog.factory_snapshot()
        }
        other_contexts = [
            harness.context_document(project_id, mode)
            for mode in ("interview", "create_agent", "edit_source", "resolve_intent")
        ]
        for context in other_contexts:
            received = {item["reference"]: item for item in context["resources"]}
            assert received.keys() == original_resources.keys()
            assert "veyra.component.model@1.0.0" in received
            assert "veyra.component.transform@1.0.0" in received
            for reference, resource in received.items():
                assert resource["spec"] == original_resources[reference]["spec"]
                assert (
                    resource["required_permissions"]
                    == original_resources[reference]["required_permissions"]
                )
            for key in (
                "project",
                "inventory",
                "files",
                "project_bindings",
                "authority",
            ):
                assert context[key] == plan[key]
        for context in [plan, *other_contexts]:
            encoded = json.dumps(context, ensure_ascii=False)
            for excluded in (credential_marker, knowledge_marker, file_marker):
                assert excluded not in encoded
            assert str(tmp_path) not in encoded
        assert transport.calls == []
