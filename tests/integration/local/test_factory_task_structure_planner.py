from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.integration.local.test_factory_routes import _client, _project
from tests.integration.local.verified_runtime_model import MemorySecretStore
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.builder.conversation_store import (
    BuilderConversationStore,
)
from veyra_agent_platform.local.builder.receipts import HarnessReceiptRecorder
from veyra_agent_platform.local.builder.task_planner import plan_task_structure
from veyra_agent_platform.local.builder.task_structure_schema import (
    task_structure_schema,
)
from veyra_agent_platform.local.factory.client import (
    FactoryProviderError,
    FactoryProviderNotConfigured,
    KimiClient,
    KimiCompletion,
)
from veyra_agent_platform.local.factory.config import FactorySettings
from veyra_agent_platform.local.factory.task_structure_planner import (
    FactoryTaskStructurePlanner,
)


@pytest.fixture(autouse=True)
def isolate_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("VEYRA_FACTORY_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("VEYRA_FACTORY_MODEL_ID", raising=False)


def _io(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "type": "string",
        "multiple": False,
        "required": True,
        "cardinality": "single",
        "description": "Text for this task",
        "source": "user request",
    }


def _payload(*, human_input: bool = False) -> dict[str, Any]:
    boundary = {
        "kind": "human_input",
        "stage": "choose",
        "reason": "The user chooses a design before continuing",
        "required": True,
        "question": "Which design should be used?",
        "expression": "",
        "branches": [],
        "checks": [],
        "capability": "",
        "entity": "",
        "scope": "run",
        "source": "wait for my selection",
        "approval_class": None,
        "expected_schema": [{"name": "selection", "type": "string"}],
    }
    return {
        "schema_version": "1.0",
        "goal": "Translate the supplied text",
        "summary": "Translate without changing the meaning",
        "actors": [
            {
                "id": "translator",
                "role": "translator",
                "capabilities": ["text_generation"],
                "reason": "Translate the supplied request and retain its meaning",
                "inputs": [_io("request")],
                "outputs": [_io("result")],
            }
        ],
        "stages": [
            {
                "id": "translate",
                "summary": "Translate the input",
                "actor": "translator",
                "source": "translate the supplied text",
                "input_sources": [{"input": "request", "source": "input.request"}],
            }
        ],
        "entities": [],
        "inputs": [_io("request")],
        "outputs": [_io("result")],
        "execution_boundaries": [boundary] if human_input else [],
        "lifecycle": {
            "persistent": False,
            "interaction": "multi_turn" if human_input else "single_run",
            "entity": "",
        },
        "orchestration_complexity": "branched" if human_input else "single",
        "uncertainty": [],
        "constraints": ["Retain the user's meaning"],
        "success_criteria": ["Return a complete translation"],
        "state": None,
        "user_requested_surface": "agent",
        "user_shape_override": "",
    }


def _completion(payload: dict[str, Any] | str) -> KimiCompletion:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return KimiCompletion(
        content=content,
        assistant_message={
            "role": "assistant",
            "content": content,
            "reasoning_content": "private reasoning must remain chain-local",
        },
        finish_reason="stop",
        request_id="request-task-plan",
    )


def test_coverage_reads_pinned_skill_method_and_workflow_tool_contract(
    tmp_path: Path,
) -> None:
    transport = PlanningTransport([_completion({"verdict": "covered", "gaps": []})])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        factory = client.app.state.factory
        skill = factory.catalog.by_reference("veyra.skill.document-analyzer@1.0.0")
        tool = factory.catalog.by_reference("veyra.tool.entity.write@1.0.0")
        planner = _planner(client, _receipts(client, project_id))
        candidate = {
            "agent": {"lock": {skill["reference"]: skill["content_hash"]}},
            "workflow": {"lock": {tool["reference"]: tool["content_hash"]}},
            "companions": [],
        }
        assert (
            planner.review_product("Use the selected document method", candidate) == ()
        )
        body = json.loads(transport.calls[0][0][-1]["content"])
        context = body["runtime_and_resource_context"]
        assert (
            context["selected_skill_procedures"][0]["instruction"]
            == skill["spec"]["instruction"]
        )
        assert {row["reference"] for row in context["resources"]} == {
            skill["reference"],
            tool["reference"],
        }
        assert any(
            "Selected Skill procedures" in row["content"]
            for row in planner._base_messages
        )


def test_coverage_cannot_read_a_skill_from_a_different_snapshot(tmp_path: Path) -> None:
    transport = PlanningTransport([])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        planner = _planner(client, _receipts(client, project_id))
        with pytest.raises(ValueError, match="pinned hash"):
            planner.review_product(
                "Use this method",
                {
                    "agent": {
                        "lock": {"veyra.skill.document-analyzer@1.0.0": "bad-hash"}
                    }
                },
            )
        assert transport.calls == []


class PlanningTransport:
    def __init__(self, responses: list[KimiCompletion | FactoryProviderError]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[Any, Any]] = []
        self.observe_prepared: Any = None

    def models(self) -> tuple[str, ...]:
        return ("kimi-k3",)

    def complete(
        self, messages: object, *, response_format: object = None
    ) -> KimiCompletion:
        self.calls.append((messages, response_format))
        if self.observe_prepared is not None:
            self.observe_prepared()
        result = self.responses.pop(0)
        if isinstance(result, FactoryProviderError):
            raise result
        return result


def _receipts(client: Any, project_id: str) -> HarnessReceiptRecorder:
    store = BuilderConversationStore(client.app.state.repository)
    conversation_id = new_uuid7()
    operation_id = new_uuid7()
    store.commit_user_turn(
        conversation_id=conversation_id,
        project_id=project_id,
        title="Task planning test",
        create_conversation=True,
        operation_id=operation_id,
        kind="create_agent",
        retry_of=None,
        input_payload={"content": "A bounded test request"},
        message_id=new_uuid7(),
        content="A bounded test request",
        created_at="2026-10-05T00:00:00Z",
    )
    factory = client.app.state.factory
    return HarnessReceiptRecorder(
        store,
        factory.harness,
        project_id=project_id,
        conversation_id=conversation_id,
        operation_id=operation_id,
        profile=factory.resolved_capability_profile(),
    )


def _rows(receipts: HarnessReceiptRecorder) -> list[dict[str, Any]]:
    return receipts.store.receipts(
        project_id=receipts.project_id,
        conversation_id=receipts.conversation_id,
        operation_id=receipts.operation_id,
    )


def _planner(
    client: Any, receipts: HarnessReceiptRecorder
) -> FactoryTaskStructurePlanner:
    factory = client.app.state.factory
    return FactoryTaskStructurePlanner(
        harness=factory.harness,
        project_id=receipts.project_id,
        complete=factory._complete_with_receipt,
        profile=factory.resolved_capability_profile(),
        receipts=receipts,
        ensure_model=factory.client.ensure_model,
    )


def test_model_planning_preserves_human_input_and_prepared_receipt(
    tmp_path: Path,
) -> None:
    transport = PlanningTransport([_completion(_payload(human_input=True))])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        receipts = _receipts(client, project_id)
        seen: list[str] = []
        transport.observe_prepared = lambda: seen.append(_rows(receipts)[-1]["status"])
        planner = _planner(client, receipts)
        requirement = "Wait for my selection before continuing this design"
        result = plan_task_structure(
            requirement, provider=planner, repair=planner.repair
        )

        assert result.status == "ok"
        assert result.structure is not None
        human = result.structure.boundaries_of("human_input")
        assert human[0].expected_schema == {"selection": "string"}
        assert result.structure.lifecycle.interaction == "multi_turn"
        assert seen == ["prepared"]
        row = _rows(receipts)[0]
        assert row["status"] == "success"
        assert row["invocation_kind"] == "semantic_plan"
        assert row["harness_mode"] == "plan_task"
        assert row["output_contract"] == "TaskStructureV1"
        assert row["provider_request_id"] == "request-task-plan"
        assert len(row["schema_hash"]) == 64
        serialized = json.dumps(row)
        assert requirement not in serialized
        assert "private reasoning" not in serialized
        assert "credentials" in row["excluded_categories_json"]
        messages, response_format = transport.calls[0]
        assert messages[-1]["content"] == requirement
        assert "TaskStructure" in messages[0]["content"]
        assert response_format["type"] == "json_schema"


def test_provider_json_must_match_the_closed_schema_before_contract_defaults(
    tmp_path: Path,
) -> None:
    incomplete = _payload()
    del incomplete["outputs"]
    incomplete["actors"][0]["inputs"][0]["type"] = "private-invalid-value"
    transport = PlanningTransport([_completion(incomplete), _completion(_payload())])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        receipts = _receipts(client, project_id)
        planner = _planner(client, receipts)
        result = plan_task_structure(
            "Translate", provider=planner, repair=planner.repair
        )
        assert result.status == "ok" and result.structure is not None
        assert len(transport.calls) == 2 and planner.repairs == 1
        diagnostic = transport.calls[1][0][-1]["content"]
        assert "required" in diagnostic and "enum" in diagnostic
        assert "private-invalid-value" not in diagnostic
        assert result.structure.outputs[0].type == "string"


def test_persistent_identity_is_repaired_before_source_composition(
    tmp_path: Path,
) -> None:
    from copy import deepcopy

    invalid = _payload()
    invalid["lifecycle"] = {
        "persistent": True,
        "interaction": "persistent_task",
        "entity": "task",
    }
    invalid["state"] = {
        "entity": "task",
        "identity": "task_key",
        "scope": "project",
        "fields": [{"name": "title", "type": "string"}],
        "statuses": [],
        "revision": True,
        "source": "User tasks",
    }
    invalid["uncertainty"] = ["Users may need to distinguish tasks with the same title"]
    repaired = deepcopy(invalid)
    repaired["state"]["identity"] = "entity_id"
    transport = PlanningTransport([_completion(invalid), _completion(repaired)])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        planner = _planner(client, _receipts(client, project_id))
        result = plan_task_structure(
            "Persist and update tasks", provider=planner, repair=planner.repair
        )
        assert result.status == "ok" and result.structure.state.identity == "entity_id"
        assert result.structure.uncertainty == tuple(invalid["uncertainty"])
        assert planner.repairs == 1 and len(transport.calls) == 2
        assert "state.identity" in transport.calls[1][0][-1]["content"]


def test_parse_and_schema_repairs_share_a_three_call_budget(tmp_path: Path) -> None:
    invalid = _payload()
    invalid["lifecycle"]["persistent"] = "not a boolean"
    transport = PlanningTransport(
        [
            _completion("invalid JSON"),
            *[_completion(invalid) for _ in range(3)],
            _completion(_payload()),
        ]
    )
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        planner = _planner(client, receipts)
        result = plan_task_structure(
            "Translate this text", provider=planner, repair=planner.repair
        )

        assert result.status == "planner_invalid"
        assert result.structure is None
        assert planner.repairs == 3
        assert len(transport.calls) == 4
        assert len(transport.responses) == 1
        assert [row["invocation_kind"] for row in _rows(receipts)] == [
            "semantic_plan",
            "semantic_plan_repair",
            "semantic_plan_repair",
            "semantic_plan_repair",
        ]


@pytest.mark.parametrize(
    "code",
    [
        "factory_unauthorized",
        "factory_rate_limited",
        "factory_timeout",
        "factory_provider_error",
    ],
)
def test_provider_failures_never_fall_back_to_heuristic_planning(
    tmp_path: Path, code: str
) -> None:
    transport = PlanningTransport(
        [FactoryProviderError(code, "Controlled Provider failure")]
    )
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        planner = _planner(client, receipts)
        with pytest.raises(FactoryProviderError) as failed:
            plan_task_structure(
                "Translate this text", provider=planner, repair=planner.repair
            )
        assert failed.value.code == code
        assert len(transport.calls) == 1
        assert planner.repairs == 0
        assert _rows(receipts)[0]["status"] == "failed"
        assert _rows(receipts)[0]["error_code"] == code


def test_only_format_support_failure_allows_one_json_object_fallback(
    tmp_path: Path,
) -> None:
    rejection = FactoryProviderError(
        "factory_request_invalid",
        "response_format json_schema is not supported",
        details={"rejected_field": "response_format"},
    )
    transport = PlanningTransport([rejection, _completion(_payload())])
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        planner = _planner(client, receipts)
        result = planner.complete_json("Translate this text", task_structure_schema())
        assert result["goal"] == _payload()["goal"]
        assert [call[1]["type"] for call in transport.calls] == [
            "json_schema",
            "json_object",
        ]
        rows = _rows(receipts)
        assert [row["status"] for row in rows] == ["failed", "success"]
        assert rows[1]["fallback_from"] == "strict_json_schema"
        assert rows[1]["fallback_to"] == "json_object"
        assert planner.repairs == 1


def test_unclassified_request_rejection_does_not_retry(tmp_path: Path) -> None:
    transport = PlanningTransport(
        [FactoryProviderError("factory_request_invalid", "Invalid model parameter")]
    )
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        with pytest.raises(FactoryProviderError):
            _planner(client, receipts).complete_json(
                "Translate this text", task_structure_schema()
            )
        assert len(transport.calls) == 1


def test_factory_generate_wires_the_model_planner_and_receipts(tmp_path: Path) -> None:
    transport = PlanningTransport(
        [
            _completion("Ready for a proposal"),
            _completion(_payload()),
            _completion({"verdict": "covered", "gaps": []}),
        ]
    )
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        factory = client.app.state.factory
        session = factory.create_session(project_id, "Translate this text")
        receipts = _receipts(client, project_id)
        generated = factory.generate(
            project_id, session["session_id"], receipts=receipts
        )
        assert generated["state"] == "review"
        assert generated["task_structure"]["goal"] == _payload()["goal"]
        assert generated["proposal_preview"]["planning_source"] == "provider"
        assert len(transport.calls) == 3
        assert _rows(receipts)[0]["output_contract"] == "TaskStructureV1"
        assert _rows(receipts)[1]["output_contract"] == "TaskCoverageV1"
        assert client.app.state.projects.project_summary(project_id)["agents"] == []


def test_unconfigured_factory_is_explicitly_offline_and_cannot_use_operation_receipt(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        project_id = _project(client)
        factory = client.app.state.factory
        factory.client = KimiClient(FactorySettings(), secret_store=MemorySecretStore())
        session = factory.create_session(project_id, "Translate this text")
        offline = factory.generate(project_id, session["session_id"])
        assert offline["proposal_preview"]["planning_source"] == "offline_heuristic"
        assert offline["proposal_preview"]["semantic_validated"] is False
        assert "Offline compiler preview" in offline["next_prompt"]
        with pytest.raises(FactoryProviderNotConfigured):
            factory.generate(
                project_id,
                session["session_id"],
                receipts=_receipts(client, project_id),
            )
