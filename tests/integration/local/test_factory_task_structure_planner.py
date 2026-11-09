from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.integration.local.test_factory_routes import _client, _project
from tests.integration.local.verified_runtime_model import MemorySecretStore
from tests.unit.local.test_model_resolver import _profile
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.builder.conversation_store import (
    BuilderConversationStore,
)
from veyra_agent_platform.local.builder.generate_product import generate_builder_product
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
from veyra_agent_platform.local.models.contracts import CapabilityStatus


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
        "skill_choices": [],
        "filesystem_write_roots": [],
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


def _condition_payload(expression: Any) -> dict[str, Any]:
    payload = _payload(human_input=True)
    payload["actors"][0]["outputs"][0]["type"] = "object"
    payload["outputs"][0]["type"] = "object"
    payload["stages"].extend(
        [
            {
                "id": "choose",
                "summary": "Receive the user's declared choice",
                "actor": "",
                "source": "user choice",
                "input_sources": [],
            },
            {
                "id": "route",
                "summary": "Route on the recorded decision",
                "actor": "",
                "source": "use the actual decision",
                "input_sources": [],
            },
        ]
    )
    boundary = dict(payload["execution_boundaries"][0])
    boundary.update(
        kind="condition",
        stage="route",
        reason="Continue only on the declared choice",
        question="",
        expression=expression,
        branches=["continue", "stop"],
        source="compare the recorded choice before continuing",
        expected_schema=[],
    )
    payload["execution_boundaries"].append(boundary)
    return payload


@pytest.mark.parametrize(
    ("requirement", "predicate"),
    [
        (
            "用户确认之后才继续下一步",
            {"path": "choose.selection", "operator": "==", "literal": "继续"},
        ),
        (
            "按审阅输出的可信度阈值决定后续路径",
            {
                "path": "translate.result.confidence",
                "operator": ">=",
                "literal": 0.00001,
            },
        ),
        (
            "根据前一步的标记是否包含待复查项选择路径",
            {
                "path": "translate.result.tags",
                "operator": "contains",
                "literal": "待复查",
            },
        ),
    ],
)
def test_normal_typed_condition_plans_do_not_spend_repairs_on_dsl_syntax(
    tmp_path: Path, requirement: str, predicate: dict[str, Any]
) -> None:
    payload = _condition_payload(predicate)
    transport = PlanningTransport([_completion(payload)])
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        planner = _planner(client, receipts)
        # The same contract must remain usable after the current profile falls
        # back to JSON mode, with documented optional I/O metadata defaults.
        planner._json_object = True
        for container in [payload, *payload["actors"]]:
            for kind in ("inputs", "outputs"):
                container[kind] = [
                    {"name": item["name"], "type": item["type"]}
                    for item in container[kind]
                ]
        transport.responses = [_completion(payload)]
        result = plan_task_structure(
            requirement, provider=planner, repair=planner.repair
        )
        assert result.status == "ok", result.diagnostics
        assert result.structure is not None
        condition = result.structure.boundaries_of("condition")[0]
        from veyra_agent_platform.contracts.condition import parse_condition_expression

        assert (
            parse_condition_expression(condition.expression).to_predicate() == predicate
        )
        assert len(result.structure.boundaries_of("human_input")) == 1
        assert planner.repairs == 0 and len(transport.calls) == 1
        assert transport.calls[0][1] == {"type": "json_object"}
        assert result.structure.actors[0].inputs[0].required is True


def test_redacted_condition_failure_category_repairs_to_typed_confirmation(
    tmp_path: Path,
) -> None:
    # Only the captured failure category is known: an invalid DSL comparison
    # exhausted repair. This synthetic expression is not the real lost response.
    invalid = _condition_payload("choose.selection == continue")
    fixed = _condition_payload(
        {"path": "choose.selection", "operator": "==", "literal": "continue"}
    )
    transport = PlanningTransport([_completion(invalid), _completion(fixed)])
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = plan_task_structure(
            "Use my recorded confirmation", provider=planner, repair=planner.repair
        )
        assert result.structure is not None, result.diagnostics
        assert planner.repairs == 1 and len(transport.calls) == 2
        diagnostic = transport.calls[1][0][-1]["content"]
        assert "execution_boundaries[1].expression" in diagnostic
        assert "expression_syntax_invalid" in diagnostic
        assert "typed predicate object" in diagnostic
        assert (
            result.structure.boundaries_of("condition")[0].expression
            == 'choose.selection == "continue"'
        )


def test_condition_budget_failure_keeps_redacted_location_operator_and_type(
    tmp_path: Path,
) -> None:
    private_literal = "TEST_PRIVATE_LITERAL_MUST_NOT_ENTER_DIAGNOSTICS"
    payload = _condition_payload(
        {"path": "translate.result.score", "operator": ">", "literal": private_literal}
    )
    transport = PlanningTransport([_completion(payload) for _ in range(4)])
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        planner = _planner(client, receipts)
        result = plan_task_structure(
            "Check the declared numeric threshold",
            provider=planner,
            repair=planner.repair,
        )
        assert result.structure is None
        assert planner.repairs == 3 and len(transport.calls) == 4
        diagnostic = result.diagnostics[0]
        assert "execution_boundaries[1].expression" in diagnostic
        assert "ordering_requires_number" in diagnostic
        assert '"operator": ">"' in diagnostic
        assert '"literal_type": "string"' in diagnostic
        assert "grammar" in diagnostic
        assert private_literal not in diagnostic
        assert private_literal not in json.dumps(_rows(receipts))


def test_initial_invalid_predicate_cannot_be_repaired_by_dropping_its_duty(
    tmp_path: Path,
) -> None:
    invalid = _condition_payload("classify the user's request as accepted")
    invalid["execution_boundaries"][1].pop("required")
    dropped = _payload(human_input=True)
    transport = PlanningTransport(
        [_completion(invalid), *[_completion(dropped) for _ in range(3)]]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = plan_task_structure(
            "Retain the requested decision", provider=planner, repair=planner.repair
        )
        assert result.structure is None
        assert planner.repairs == 3 and len(transport.calls) == 4
        assert '"issue": "required_duty_removed"' in result.diagnostics[0]
        assert "classify the user's request" not in result.diagnostics[0]


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
        policy = transport.calls[0][0][0]["content"]
        assert "Fidelity is bidirectional" in policy
        assert "optional future corrections" in policy
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


def test_reviewed_semantic_correction_can_remove_an_invented_input_gate(
    tmp_path: Path,
) -> None:
    requirement = (
        "Report conflicting facts as unknown; support optional later corrections"
    )
    initial = _payload(human_input=True)
    question = initial["execution_boundaries"][0]
    question.update(
        stage="translate", reason="Accept later corrections", source=requirement
    )
    initial["constraints"].append("Resolve all conflicts before delivery")
    initial["execution_boundaries"].append(
        {
            "kind": "verification",
            "stage": "translate",
            "reason": "Report only supplied facts and mark gaps",
            "required": True,
            "checks": ["required_fields:result"],
        }
    )
    corrected = json.loads(json.dumps(initial))
    corrected["execution_boundaries"][0]["required"] = False
    corrected["constraints"].pop()
    feedback = {
        "verdict": "incomplete",
        "gaps": [
            {
                "requirement": requirement,
                "reason": "Optional corrections became a mandatory input gate",
            }
        ],
    }
    transport = PlanningTransport(
        [
            _completion(initial),
            _completion(feedback),
            _completion(corrected),
            _completion({"verdict": "covered", "gaps": []}),
        ]
    )
    with _client(tmp_path, transport) as client:
        factory = client.app.state.factory
        receipts = _receipts(client, _project(client))
        planner = _planner(client, receipts)
        product = generate_builder_product(
            requirement,
            factory.catalog,
            planner_provider=planner,
            planner_repair=planner.repair,
            planner_review=planner.review_product,
        )
        assert product.status == "review", product.diagnostics
        assert len(transport.calls) == 4
        assert product.source.finalization is not None
        assert not any(
            criterion.startswith("Resolve this interaction")
            for criterion in product.source.finalization.criteria
        )
        assert (
            "Resolve all conflicts before delivery" not in product.source.instructions
        )
        assert requirement in product.source.instructions
        assert "remove unrequested restrictions" in transport.calls[2][0][-1]["content"]
        assert (
            json.loads(transport.calls[3][0][-1]["content"])["requirement"]
            == requirement
        )

        # Recovery must not re-anchor the correction to its rejected first draft.
        resumed = _planner(
            client,
            receipts,
            initial_draft={
                "first_schema_valid": initial,
                "latest_schema_valid": corrected,
                "last_semantic_valid": corrected,
            },
        )
        restored = resumed.complete_json(requirement, task_structure_schema())
        assert restored["execution_boundaries"][0]["required"] is False
        assert "Resolve all conflicts before delivery" not in restored["constraints"]
        assert len(transport.calls) == 4


def _review_payload(criterion: str) -> dict[str, Any]:
    payload = _payload()
    payload.update(
        goal="Independently review the supplied material",
        summary="Return a report and only evidence-supported findings",
        constraints=[],
        success_criteria=["Report findings without inventing evidence"],
        execution_boundaries=[
            {
                "kind": "verification",
                "stage": "translate",
                "reason": criterion,
                "required": True,
                "checks": ["output.not_empty"],
                "source": "Review the supplied material",
            }
        ],
    )
    actor = payload["actors"][0]
    actor.update(role="reviewer", reason="Independently review supplied evidence")
    payload["stages"][0].update(
        summary="Review the material and return the actual findings",
        source="Review the supplied material",
    )
    for container in (payload, actor):
        container["outputs"].append(
            {
                **_io("issues"),
                "type": "array",
                "description": "Actual findings; an empty array means none found",
            }
        )
    return payload


def test_coverage_correction_allows_zero_findings_and_restores_latest_plan(
    tmp_path: Path,
) -> None:
    requirement = "Review supplied evidence; report only actual defects, if any"
    invented = "The issues list must contain at least one defect before delivery"
    initial = _review_payload(invented)
    initial["constraints"].append(invented)
    corrected = json.loads(json.dumps(initial))
    corrected["constraints"] = []
    corrected["execution_boundaries"][0]["reason"] = (
        "Return the report and actual findings, allowing zero findings"
    )
    feedback = {
        "verdict": "incomplete",
        "gaps": [
            {
                "requirement": requirement,
                "reason": "The plan invented a minimum count for discovered defects",
            }
        ],
    }
    transport = PlanningTransport(
        [
            _completion(initial),
            _completion(feedback),
            _completion(corrected),
            _completion({"verdict": "covered", "gaps": []}),
        ]
    )
    with _client(tmp_path, transport) as client:
        factory = client.app.state.factory
        receipts = _receipts(client, _project(client))
        planner = _planner(client, receipts)
        product = generate_builder_product(
            requirement,
            factory.catalog,
            planner_provider=planner,
            planner_repair=planner.repair,
            planner_review=planner.review_product,
        )
        assert product.status == "review", product.diagnostics
        assert product.source is not None and product.source.finalization is not None
        assert invented not in product.source.instructions
        assert invented not in product.source.finalization.criteria
        assert corrected["execution_boundaries"][0]["reason"] in (
            product.source.finalization.criteria
        )
        assert product.source.outputs["issues"].type == "array"
        planning_policy = "\n".join(
            item["content"]
            for item in transport.calls[0][0]
            if item["role"] == "system"
        )
        coverage_policy = transport.calls[1][0][0]["content"]
        for policy in (planning_policy, coverage_policy):
            assert "zero findings" in policy
            assert "minimum count" in policy
        assert "remove unrequested restrictions" in transport.calls[2][0][-1]["content"]

        resumed = _planner(
            client,
            receipts,
            initial_draft={
                "first_schema_valid": initial,
                "latest_schema_valid": corrected,
                "last_semantic_valid": corrected,
            },
        )
        restored = resumed.complete_json(requirement, task_structure_schema())
        assert invented not in restored["constraints"]
        assert restored["execution_boundaries"] == corrected["execution_boundaries"]
        assert len(transport.calls) == 4


def test_explicit_minimum_findings_survives_compilation_and_retained_recovery(
    tmp_path: Path,
) -> None:
    minimum = "Return at least two independently supported findings"
    requirement = minimum + "; do not fabricate evidence"
    initial = _review_payload(minimum)
    initial["constraints"].append(minimum)
    transport = PlanningTransport(
        [_completion(initial), _completion({"verdict": "covered", "gaps": []})]
    )
    with _client(tmp_path, transport) as client:
        factory = client.app.state.factory
        receipts = _receipts(client, _project(client))
        planner = _planner(client, receipts)
        product = generate_builder_product(
            requirement,
            factory.catalog,
            planner_provider=planner,
            planner_repair=planner.repair,
            planner_review=planner.review_product,
        )
        assert product.status == "review", product.diagnostics
        assert product.source is not None and product.source.finalization is not None
        assert minimum in product.source.instructions
        assert minimum in product.source.finalization.criteria

        latest = json.loads(json.dumps(initial))
        latest["constraints"] = []
        resumed = _planner(
            client,
            receipts,
            initial_draft={
                "first_schema_valid": initial,
                "latest_schema_valid": latest,
                "last_semantic_valid": initial,
            },
        )
        restored = resumed.complete_json(requirement, task_structure_schema())
        assert minimum in restored["constraints"]
        assert restored["execution_boundaries"][0]["reason"] == minimum
        assert len(transport.calls) == 2


@pytest.mark.parametrize(
    "protection", ["input_files", "protected_fields", "write_scope"]
)
def test_semantic_feedback_does_not_allow_permission_protections_to_be_relaxed(
    tmp_path: Path, protection: str
) -> None:
    initial = _payload()
    initial["protect_input_files"] = True
    initial["filesystem_write_roots"] = ["project/reports"]
    if protection == "protected_fields":
        initial["protected_input_fields"] = ["request"]
    changed = json.loads(json.dumps(initial))
    if protection == "input_files":
        changed["protect_input_files"] = False
    elif protection == "protected_fields":
        changed["protected_input_fields"] = []
    else:
        changed["filesystem_write_roots"] = ["project"]
    feedback = {
        "verdict": "incomplete",
        "gaps": [{"requirement": "Report gaps", "reason": "Remove an invented gate"}],
    }
    transport = PlanningTransport(
        [_completion(initial), _completion(feedback), _completion(changed)]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)), max_repairs=1)
        planned = planner.complete_json("Report gaps", task_structure_schema())
        gaps = planner.review_product("Report gaps", {})
        with pytest.raises(
            ValueError, match="input-file protection|protected input field|write limit"
        ):
            planner.repair(json.dumps(planned), "; ".join(gaps))
        assert len(transport.calls) == 3


def test_repairs_keep_the_complete_bounded_candidate_instead_of_cutting_its_json(
    tmp_path: Path,
) -> None:
    transport = PlanningTransport([])
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        previous = json.dumps({"summary": "A" * 60_000})
        assert (
            planner._repair_messages(previous, "Correct the binding")[-2]["content"]
            == previous
        )
        with pytest.raises(ValueError, match="size limit"):
            planner._repair_messages("A" * 200_001, "Oversized")
        assert transport.calls == []


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


def _method_payload() -> dict[str, Any]:
    payload = _payload()
    payload["actors"][0]["capabilities"].append("document_analysis")
    payload["skill_choices"] = [
        {
            "actor": "translator",
            "capability": "document_analysis",
            "reference": "veyra.skill.document-analyzer@1.0.0",
            "reason": "Use the requested document method",
        }
    ]
    return payload


def test_selected_procedure_is_read_before_tool_dependencies_are_composed(
    tmp_path: Path,
) -> None:
    initial = _method_payload()
    grounded = _method_payload()
    grounded["actors"][0]["capabilities"].append("workspace_read")
    transport = PlanningTransport([_completion(initial), _completion(grounded)])
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        planner = _planner(client, receipts)
        result = plan_task_structure(
            "Use this document method to read project files",
            provider=planner,
            repair=planner.repair,
        )
        assert result.structure is not None
        assert "workspace_read" in result.structure.actors[0].capabilities
        messages = transport.calls[1][0]
        context = next(
            row
            for row in messages
            if row["content"].startswith("Selected Skill procedures")
        )
        procedures = json.loads(context["content"].split("\n", 1)[1])
        actual = client.app.state.factory.catalog.by_reference(
            "veyra.skill.document-analyzer@1.0.0"
        )
        assert procedures[0]["instruction"] == actual["spec"]["instruction"]
        assert procedures[0]["content_hash"] == actual["content_hash"]
        assert planner.repairs == 1
        assert [row["invocation_kind"] for row in _rows(receipts)] == [
            "semantic_plan",
            "semantic_plan_repair",
        ]
        from veyra_agent_platform.local.builder.generate_product import (
            generate_builder_product,
        )

        class GroundedPlanner:
            def complete_json(self, prompt, schema):
                return result.structure.to_dict()

        product = generate_builder_product(
            "Use this document method to read project files",
            client.app.state.factory.catalog,
            planner_provider=GroundedPlanner(),
        )
        assert product.source is not None, product.diagnostics
        assert "veyra.tool.filesystem.read@1.0.0" in product.source.lock
        assert actual["reference"] in product.source.skill_refs


def test_unknown_method_repairs_share_budget_and_never_read_a_substitute(
    tmp_path: Path,
) -> None:
    payload = _method_payload()
    payload["skill_choices"][0]["reference"] = "unknown.method@1.0.0"
    transport = PlanningTransport([_completion(payload) for _ in range(4)])
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = plan_task_structure(
            "Use my chosen method", provider=planner, repair=planner.repair
        )
        assert result.structure is None and planner.repairs == 3
        assert len(transport.calls) == 4
        assert not any(
            row["content"].startswith("Selected Skill procedures")
            for messages, _ in transport.calls
            for row in messages
        )


def test_method_grounding_cannot_erase_a_required_user_decision(tmp_path: Path) -> None:
    initial = _method_payload()
    initial["execution_boundaries"] = _payload(human_input=True)["execution_boundaries"]
    dropped = _method_payload()
    transport = PlanningTransport(
        [_completion(initial), *[_completion(dropped) for _ in range(4)]]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = plan_task_structure(
            "Ask me before continuing the chosen method",
            provider=planner,
            repair=planner.repair,
        )
        assert result.structure is None
        assert planner.semantic_repairs == 3 and planner.method_groundings == 1
        assert planner.repairs == 4 and len(transport.calls) == 5


def test_exhausted_grounding_reports_safe_last_issue_instead_of_only_budget(
    tmp_path: Path,
) -> None:
    original = _method_payload()
    dropped = _method_payload()
    dropped["skill_choices"] = []
    transport = PlanningTransport(
        [
            _completion(original),
            *[_completion(dropped) for _ in range(4)],
        ]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = plan_task_structure(
            "Use this method", provider=planner, repair=planner.repair
        )
        assert result.structure is None
        assert '"issue": "method_changed"' in result.diagnostics[0]
        with pytest.raises(ValueError) as exhausted:
            planner._consume_repair("Controlled schema issue sk-private-secret-value")
        assert "sk-private-secret-value" not in str(exhausted.value)
        assert "[redacted]" in str(exhausted.value)


@pytest.mark.parametrize(
    "replacement",
    [
        [],
        [
            {
                "actor": "translator",
                "capability": "document_analysis",
                "reference": "veyra.skill.evidence-ledger@1.0.0",
                "reason": "Substitute the previous method",
            }
        ],
    ],
)
def test_grounding_and_repairs_cannot_silently_drop_or_replace_a_read_method(
    tmp_path: Path,
    replacement: list[dict[str, Any]],
) -> None:
    original = _method_payload()
    changed = _method_payload()
    changed["skill_choices"] = replacement
    transport = PlanningTransport(
        [
            _completion(original),
            *[_completion(changed) for _ in range(4)],
        ]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = plan_task_structure(
            "Use my chosen method",
            provider=planner,
            repair=planner.repair,
        )
        assert result.structure is None and len(transport.calls) == 5
        assert planner.semantic_repairs == 3 and planner.repairs == 4


def test_grounded_dependencies_survive_later_repairs_with_the_same_method(
    tmp_path: Path,
) -> None:
    original = _method_payload()
    grounded = _method_payload()
    grounded["actors"][0]["capabilities"].append("workspace_read")
    boundary = dict(_payload(human_input=True)["execution_boundaries"][0])
    boundary.update(
        kind="tool",
        stage="translate",
        question="",
        expected_schema=[],
        reason="Read the material required by the selected method",
        capability="workspace_read",
        source="Selected method requires project material",
    )
    grounded["execution_boundaries"] = [boundary]
    transport = PlanningTransport(
        [
            _completion(original),
            _completion(grounded),
            _completion(original),
            _completion(original),
            _completion(original),
        ]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        payload = planner.complete_json(
            "Read project files using this method", task_structure_schema()
        )
        assert "workspace_read" in payload["actors"][0]["capabilities"]
        with pytest.raises(ValueError, match="budget exhausted"):
            planner.repair(json.dumps(payload), "Repair a composition issue")
        assert planner.semantic_repairs == 3 and planner.repairs == 4
        assert len(transport.calls) == 5


def test_two_required_decisions_from_the_same_source_cannot_collapse(
    tmp_path: Path,
) -> None:
    initial = _method_payload()
    decision = _payload(human_input=True)["execution_boundaries"][0]
    second = dict(decision, stage="final_confirm", question="Confirm the final result?")
    initial["execution_boundaries"] = [decision, second]
    dropped = _method_payload()
    dropped["execution_boundaries"] = [decision]
    transport = PlanningTransport(
        [
            _completion(initial),
            *[_completion(dropped) for _ in range(4)],
        ]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = plan_task_structure(
            "Ask me to choose, then ask me to confirm the final result",
            provider=planner,
            repair=planner.repair,
        )
        assert result.structure is None and planner.semantic_repairs == 3
        assert planner.method_groundings == 1 and len(transport.calls) == 5


def test_corrected_grounding_plan_reuses_supplied_procedure_without_a_fourth_call(
    tmp_path: Path,
) -> None:
    from copy import deepcopy

    initial = _method_payload()
    initial["execution_boundaries"] = _payload(human_input=True)["execution_boundaries"]
    dropped = deepcopy(initial)
    dropped["execution_boundaries"] = []
    fixed = deepcopy(initial)
    fixed["actors"][0]["capabilities"].append("workspace_read")
    transport = PlanningTransport(
        [_completion(initial), _completion(dropped), _completion(fixed)]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = plan_task_structure(
            "Use the selected method and retain my decision",
            provider=planner,
            repair=planner.repair,
        )
        assert result.structure is not None
        assert (
            result.structure.execution_boundaries[0].question
            == "Which design should be used?"
        )
        assert planner.repairs == 2 and len(transport.calls) == 3
        repair = transport.calls[2][0][-1]["content"]
        assert "human_input:" in repair
        assert "Retain these required execution boundary contracts" in repair
        assert '"question": "Which design should be used?"' in repair
        assert "workspace_read" in result.structure.actors[0].capabilities


def test_grounding_can_narrow_excess_actor_capabilities_without_repeating_method_read(
    tmp_path: Path,
) -> None:
    original = _method_payload()
    original["actors"][0]["capabilities"].append("workspace_write")
    grounded = _method_payload()
    grounded["actors"][0]["capabilities"].extend(["workspace_read", "workspace_write"])
    narrowed = _method_payload()
    narrowed["actors"][0]["capabilities"].append("workspace_read")
    transport = PlanningTransport(
        [
            _completion(original),
            _completion(grounded),
            _completion(narrowed),
        ]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        payload = planner.complete_json(
            "Inspect without modifying files", task_structure_schema()
        )
        repaired = planner.repair(json.dumps(payload), "Narrow the readonly role")
        assert "workspace_write" not in repaired["actors"][0]["capabilities"]
        assert "workspace_read" in repaired["actors"][0]["capabilities"]
        assert repaired["skill_choices"] == original["skill_choices"]
        assert len(transport.calls) == 3 and planner.repairs == 2


def _grounded_method_with_executor() -> dict[str, Any]:
    payload = _method_payload()
    payload["actors"][0]["capabilities"].append("workspace_read")
    boundary = dict(_payload(human_input=True)["execution_boundaries"][0])
    boundary.update(
        kind="tool",
        stage="translate",
        question="",
        expected_schema=[],
        capability="workspace_read",
        reason="Read the material needed by the selected method",
        source="Selected method needs project material",
    )
    payload["execution_boundaries"] = [boundary]
    return payload


@pytest.mark.parametrize("split_role", [False, True])
def test_repair_can_reassign_an_exact_read_method_without_another_grounding_call(
    tmp_path: Path, split_role: bool
) -> None:
    from copy import deepcopy

    initial = _method_payload()
    grounded = _grounded_method_with_executor()
    reassigned = deepcopy(grounded)
    if split_role:
        writer = deepcopy(reassigned["actors"][0])
        writer.update(id="writer", role="report writer")
        reassigned["actors"][0]["capabilities"] = ["text_generation"]
        reassigned["actors"].append(writer)
        stage = deepcopy(reassigned["stages"][0])
        stage.update(id="write", actor="writer", summary="Read and prepare the report")
        reassigned["stages"][0]["input_sources"] = [
            {"input": "request", "source": "write.result"}
        ]
        reassigned["stages"].insert(0, stage)
        reassigned["execution_boundaries"][0]["stage"] = "write"
    else:
        reassigned["actors"][0]["id"] = "writer"
        reassigned["stages"][0]["actor"] = "writer"
    reassigned["skill_choices"][0]["actor"] = "writer"
    transport = PlanningTransport(
        [_completion(initial), _completion(grounded), _completion(reassigned)]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        payload = planner.complete_json(
            "Use this exact method", task_structure_schema()
        )
        repaired = planner.repair(
            json.dumps(payload), "Assign the method to its writer"
        )
        assert repaired["skill_choices"][0]["actor"] == "writer"
        assert (
            repaired["skill_choices"][0]["reference"]
            == initial["skill_choices"][0]["reference"]
        )
        assert len(transport.calls) == 3 and planner.repairs == 2
        writer = next(actor for actor in repaired["actors"] if actor["id"] == "writer")
        assert "workspace_read" in writer["capabilities"]
        assert repaired["execution_boundaries"][0]["capability"] == "workspace_read"
        procedure_context = next(
            row
            for row in planner._base_messages
            if row["content"].startswith("Selected Skill procedures")
        )
        procedure = json.loads(procedure_context["content"].split("\n", 1)[1])[0]
        assert procedure["actor"] == "writer"


@pytest.mark.parametrize("invalid_assignment", ["unknown_actor", "missing_capability"])
def test_method_reassignment_still_requires_a_legal_actor_capability(
    tmp_path: Path, invalid_assignment: str
) -> None:
    from copy import deepcopy

    grounded = _grounded_method_with_executor()
    changed = deepcopy(grounded)
    if invalid_assignment == "unknown_actor":
        changed["skill_choices"][0]["actor"] = "unregistered"
    else:
        changed["actors"][0]["capabilities"].remove("document_analysis")
    transport = PlanningTransport(
        [
            _completion(_method_payload()),
            _completion(grounded),
            _completion(changed),
            _completion(changed),
            _completion(changed),
        ]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        payload = planner.complete_json(
            "Use this exact method", task_structure_schema()
        )
        with pytest.raises(ValueError, match="declared actor capability"):
            planner.repair(json.dumps(payload), "Reassign the method")
        assert len(transport.calls) == 5 and planner.semantic_repairs == 3


def test_reassignment_cache_cannot_accept_a_changed_method_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from copy import deepcopy

    grounded = _grounded_method_with_executor()
    renamed = deepcopy(grounded)
    renamed["actors"][0]["id"] = "writer"
    renamed["stages"][0]["actor"] = "writer"
    renamed["skill_choices"][0]["actor"] = "writer"
    transport = PlanningTransport(
        [
            _completion(_method_payload()),
            _completion(grounded),
            _completion(renamed),
            _completion(renamed),
            _completion(renamed),
        ]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        payload = planner.complete_json(
            "Use this exact method", task_structure_schema()
        )
        lookup = planner.harness.catalog.by_reference

        def changed(reference):
            resource = deepcopy(lookup(reference))
            if resource["reference"] == grounded["skill_choices"][0]["reference"]:
                resource["content_hash"] = "f" * 64
            return resource

        monkeypatch.setattr(planner.harness.catalog, "by_reference", changed)
        with pytest.raises(ValueError, match="planning snapshot"):
            planner.repair(json.dumps(payload), "Reassign the method")
        assert len(transport.calls) == 5 and planner.semantic_repairs == 3


def test_two_required_method_uses_cannot_be_reduced_to_one(tmp_path: Path) -> None:
    from copy import deepcopy

    initial = _method_payload()
    second = deepcopy(initial["actors"][0])
    second["id"] = "reviewer"
    initial["actors"].append(second)
    stage = deepcopy(initial["stages"][0])
    stage.update(id="review", actor="reviewer")
    stage["input_sources"] = [{"input": "request", "source": "translate.result"}]
    initial["stages"].append(stage)
    initial["skill_choices"].append(dict(initial["skill_choices"][0], actor="reviewer"))
    grounded = deepcopy(initial)
    for actor in grounded["actors"]:
        actor["capabilities"].append("workspace_read")
    dropped = deepcopy(grounded)
    dropped["skill_choices"].pop()
    transport = PlanningTransport(
        [
            _completion(initial),
            _completion(grounded),
            _completion(dropped),
            _completion(dropped),
            _completion(dropped),
        ]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        payload = planner.complete_json("Use the method twice", task_structure_schema())
        with pytest.raises(ValueError, match="selected exact Skill method"):
            planner.repair(json.dumps(payload), "Retain both method uses")
        assert len(transport.calls) == 5 and planner.semantic_repairs == 3


def test_failed_post_coverage_repair_is_stored_with_safe_latest_cause_and_valid_ir(
    tmp_path: Path,
) -> None:
    from copy import deepcopy

    from fastapi.testclient import TestClient

    from veyra_agent_platform.local.app import create_app
    from veyra_agent_platform.local.config import LocalSettings

    initial = _payload()
    invalid = deepcopy(initial)
    private_value = "sk-private-repair-value"
    invalid["actors"][0]["inputs"][0]["type"] = private_value
    coverage = {
        "verdict": "incomplete",
        "gaps": [{"requirement": "Distinct writer", "reason": "Writer is missing"}],
    }
    transport = PlanningTransport(
        [
            _completion(initial),
            _completion(coverage),
            _completion(invalid),
            _completion(invalid),
            _completion(invalid),
            _completion(invalid),
        ]
    )
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(
        create_app(
            settings, factory_transport=transport, secret_store=MemorySecretStore()
        )
    ) as client:
        project_id = _project(client)
        session = client.app.state.factory.create_session(
            project_id, "Translate with a distinct writer", interview=False
        )
        client.app.state.factory.client.settings.repair_attempts = 3
        url = f"/api/v1/projects/{project_id}/factory/sessions/{session['session_id']}"
        generated = client.post(f"{url}/generate")
        assert generated.status_code == 200, generated.text
        stored = client.get(url).json()
        assert stored["specification_status"] == "blocked"
        diagnostic = stored["diagnostics"][0]
        assert "planner_repair_budget_exhausted" in diagnostic
        assert '"phase": "task_schema"' in diagnostic
        assert '"issue": "io_schema_invalid"' in diagnostic
        assert '"validator": "additionalProperties"' in diagnostic
        assert "retained_ir=last_validated" in diagnostic
        assert any("Writer is missing" in issue for issue in stored["diagnostics"])
        assert stored["task_structure"]["actors"][0]["inputs"][0]["type"] == "string"
        assert private_value not in json.dumps(stored)
        assert len(transport.calls) == 6
        with client.app.state.repository.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM factory_sessions WHERE session_id = ?",
                (session["session_id"],),
            ).fetchone()
        assert "planner_repair_budget_exhausted" in row["diagnostics_json"]
        assert private_value not in " ".join(str(value) for value in row)


def test_invalid_initial_directory_syntax_uses_bounded_contract_repair(
    tmp_path: Path,
) -> None:
    invalid = _payload()
    invalid["filesystem_write_roots"] = ["reports"]
    fixed = _payload()
    fixed["filesystem_write_roots"] = ["project/reports"]
    transport = PlanningTransport([_completion(invalid), _completion(fixed)])
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = plan_task_structure(
            "Only write reports", provider=planner, repair=planner.repair
        )
        assert result.structure is not None
        assert result.structure.filesystem_write_roots == ("project/reports",)
        assert planner.repairs == 1


def test_repair_may_narrow_a_write_scope_but_cannot_widen_or_remove_it(
    tmp_path: Path,
) -> None:
    original = _payload()
    original["filesystem_write_roots"] = ["project/reports"]
    narrower = _payload()
    narrower["filesystem_write_roots"] = ["project/reports/weekly"]
    wider = _payload()
    wider["filesystem_write_roots"] = ["project"]
    transport = PlanningTransport(
        [
            _completion(original),
            _completion(narrower),
            _completion(wider),
            _completion(wider),
        ]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = planner.complete_json("Only write reports", task_structure_schema())
        narrowed = planner.repair(json.dumps(result), "Use a weekly output directory")
        assert narrowed["filesystem_write_roots"] == ["project/reports/weekly"]
        with pytest.raises(ValueError, match="write limit"):
            planner.repair(json.dumps(narrowed), "Repair a composition issue")
        assert planner.repairs == 3


def test_provider_empty_outputs_are_repaired_before_contract_defaults(
    tmp_path: Path,
) -> None:
    invalid = _payload()
    invalid["outputs"] = []
    transport = PlanningTransport([_completion(invalid), _completion(_payload())])
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = plan_task_structure(
            "Return a translation", provider=planner, repair=planner.repair
        )
        assert result.structure is not None and result.structure.outputs
        assert planner.repairs == 1 and len(transport.calls) == 2
        assert "outputs" in transport.calls[1][0][-1]["content"]


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
    client: Any, receipts: HarnessReceiptRecorder, **options: Any
) -> FactoryTaskStructurePlanner:
    factory = client.app.state.factory
    return FactoryTaskStructurePlanner(
        harness=factory.harness,
        project_id=receipts.project_id,
        complete=factory._complete_with_receipt,
        profile=factory.resolved_capability_profile(),
        receipts=receipts,
        ensure_model=factory.client.ensure_model,
        **options,
    )


@pytest.mark.parametrize("canonical_mapping", [False, True])
def test_persistent_missing_state_uses_small_field_repair_not_another_full_plan(
    tmp_path: Path,
    canonical_mapping: bool,
) -> None:
    initial = _payload()
    initial["lifecycle"].update(
        persistent=True, interaction="persistent_task", entity="SavedTask"
    )
    state = {
        "entity": "SavedTask",
        "identity": "entity_id",
        "scope": "project",
        "fields": [
            {"name": "request", "type": "string"},
            {"name": "result", "type": "string"},
        ],
        "statuses": ["draft", "confirmed"],
        "revision": True,
        "source": "Store project revisions",
    }
    if canonical_mapping:
        state["fields"] = {"request": "string", "result": "string"}
        state.pop("revision")
        state.pop("source")
    transport = PlanningTransport([_completion(initial), _completion({"state": state})])
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        planner = _planner(client, receipts, max_repairs=None)
        result = plan_task_structure(
            "Save and restore project revisions",
            provider=planner,
            repair=planner.repair,
        )
        assert result.structure is not None, result.diagnostics
        assert result.structure.state is not None
        assert result.structure.state.identity == "entity_id"
        assert result.structure.state.fields == {
            "request": "string",
            "result": "string",
        }
        assert result.structure.state.revision is True
        assert result.structure.actors[0].to_dict() == initial["actors"][0]
        assert len(transport.calls) == 2
        assert _rows(receipts)[1]["output_contract"] == "TaskStateRepairV1"
        assert (
            _rows(receipts)[1]["request_size_bytes"]
            < _rows(receipts)[0]["request_size_bytes"]
        )


def test_unlimited_semantic_repairs_still_respect_one_configured_total_budget(
    tmp_path: Path,
) -> None:
    invalid = _payload()
    invalid["outputs"][0] = {}
    transport = PlanningTransport([_completion(invalid), _completion({"field_0": {}})])
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        planner = _planner(client, receipts, max_repairs=None, max_requests=2)
        result = plan_task_structure(
            "Translate this request", provider=planner, repair=planner.repair
        )
        assert result.structure is None
        assert len(transport.calls) == 2
        assert '"phase": "model_requests"' in result.diagnostics[0]


def test_generation_deadline_prevents_a_model_request_before_dispatch(
    tmp_path: Path,
) -> None:
    transport = PlanningTransport([])
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        planner = _planner(client, receipts, max_repairs=None, max_seconds=0)
        result = plan_task_structure(
            "Translate this request", provider=planner, repair=planner.repair
        )
        assert result.structure is None and not transport.calls
        assert '"phase": "elapsed_time"' in result.diagnostics[0]


def test_canonical_optional_io_metadata_needs_no_model_repair(tmp_path: Path) -> None:
    initial = _payload()
    for owner in [initial, *initial["actors"]]:
        for kind in ("inputs", "outputs"):
            owner[kind] = [
                {"name": item["name"], "type": item["type"]} for item in owner[kind]
            ]
    transport = PlanningTransport([_completion(initial)])
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        planner = _planner(client, receipts)
        result = plan_task_structure(
            "Translate this text", provider=planner, repair=planner.repair
        )
        assert result.structure is not None, result.diagnostics
        assert len(transport.calls) == 1 and planner.repairs == 0
        assert result.structure.inputs[0].name == "request"


def test_repair_progress_reports_code_and_locations_without_model_values(
    tmp_path: Path,
) -> None:
    invalid = _payload()
    invalid["outputs"][0] = {}
    transport = PlanningTransport(
        [_completion(invalid), _completion({"field_0": _io("result")})]
    )
    progress = []
    with _client(tmp_path, transport) as client:
        recorder = _receipts(client, _project(client))
        planner = _planner(client, recorder, on_progress=progress.append)
        result = plan_task_structure(
            "Translate this text", provider=planner, repair=planner.repair
        )
        assert result.structure is not None
        assert progress[0]["repair_issue_code"] == "task_schema_invalid"
        assert "$.outputs[0]" in progress[0]["repair_locations"]


def test_protocol_and_method_grounding_leave_three_semantic_corrections_and_total_cap(
    tmp_path: Path,
) -> None:
    initial = _method_payload()
    initial["outputs"][0] = {}
    grounded = _grounded_method_with_executor()
    coverage_gap = {
        "verdict": "incomplete",
        "gaps": [{"requirement": "A complete result", "reason": "Fix the output"}],
    }
    coverage_ok = {"verdict": "covered", "gaps": []}
    transport = PlanningTransport(
        [
            _completion(initial),
            _completion({"field_0": _io("result")}),
            _completion(grounded),
            _completion(coverage_gap),
            *[_completion(grounded) for _ in range(3)],
            _completion(coverage_ok),
        ]
    )
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        planner = _planner(client, receipts)
        payload = planner.complete_json(
            "Use the selected method", task_structure_schema()
        )
        assert planner.protocol_fallbacks == 1 and planner.method_groundings == 1
        assert planner.semantic_repairs == 0 and planner.requests == 3
        assert planner.review_product("Use the selected method", {})
        for _ in range(3):
            payload = planner.repair(json.dumps(payload), "Correct a coverage gap")
        assert not planner.review_product("Use the selected method", {})
        assert planner.semantic_repairs == 3 and planner.repairs == 5
        assert planner.requests == 8 and len(transport.calls) == 8
        with pytest.raises(ValueError) as exhausted:
            planner.review_product("Use the selected method", {})
        assert (
            '"issue": "model_request_limit"' in exhausted.value.safe_repair_diagnostic
        )
        assert '"phase": "model_requests"' in exhausted.value.safe_repair_diagnostic
        assert len(transport.calls) == 8 and len(_rows(receipts)) == 8


def test_configured_total_cap_bounds_a_larger_semantic_budget(tmp_path: Path) -> None:
    payload = _payload()
    transport = PlanningTransport([_completion(payload), _completion(payload)])
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        planner = _planner(client, receipts, max_repairs=5, max_requests=2)
        result = planner.complete_json("Translate", task_structure_schema())
        planner.repair(json.dumps(result), "Correct the result")
        assert planner.max_repairs == 5
        with pytest.raises(ValueError) as exhausted:
            planner.repair(json.dumps(result), "Another correction")
        assert '"phase": "model_requests"' in exhausted.value.safe_repair_diagnostic
        assert len(transport.calls) == 2 and planner.requests == 2
        assert len(_rows(receipts)) == 2


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


def test_malformed_actor_io_gets_local_schema_targets_without_dropping_inputs(
    tmp_path: Path,
) -> None:
    invalid = _payload()
    invalid["actors"][0]["inputs"][0] = {"$ref": "private-model-alias"}
    invalid["actors"][0]["outputs"][0]["type"] = "private-model-type"
    transport = PlanningTransport(
        [
            _completion(invalid),
            _completion({"field_0": _io("request"), "field_1": _io("result")}),
        ]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = plan_task_structure(
            "Translate every supplied input", provider=planner, repair=planner.repair
        )
        assert result.structure is not None
        assert result.structure.actors[0].inputs[0].name == "request"
        assert result.structure.actors[0].outputs[0].type == "string"
        assert planner.repairs == 1 and len(transport.calls) == 2
        repair = transport.calls[1][0][-1]["content"]
        assert repair.count("$.actors[0].inputs[0]: required:") == 1
        assert "$.actors[0].outputs[0].type: enum:" in repair
        assert "private-model-alias" not in repair
        assert "private-model-type" not in repair
        response_schema = json.loads(
            repair.split("Response schema: ", 1)[1].split(
                "\nValidation diagnostic: ", 1
            )[0]
        )
        input_schema = response_schema["properties"]["field_0"]
        assert '"path": "$.actors[0].inputs[0]"' in repair
        assert input_schema["required"] == list(_io("request"))
        assert input_schema["additionalProperties"] is False
        assert input_schema["properties"]["source"]["type"] == "string"
        assert "Do not return the whole TaskStructure" in repair
        assert result.structure.constraints == tuple(invalid["constraints"])
        assert (
            _rows(planner.receipts)[1]["output_contract"] == "TaskStructureIORepairV1"
        )
        first, repaired = _rows(planner.receipts)
        assert first["structured_mode"] == "strict_json_schema"
        assert repaired["structured_mode"] == "json_object"
        assert repaired["fallback_from"] == "strict_json_schema"
        assert repaired["fallback_to"] == "json_object"


def test_invalid_external_reference_is_repaired_before_resource_grounding(
    tmp_path: Path,
) -> None:
    from copy import deepcopy

    invalid = _payload()
    boundary = _payload(human_input=True)["execution_boundaries"][0]
    boundary.update(
        kind="verification",
        stage="translate",
        question="",
        checks=["output.not_empty"],
        expected_schema=[],
    )
    invalid["execution_boundaries"] = [boundary]
    invalid["stages"][0]["input_sources"][0]["source"] = "missing.result"
    fixed = deepcopy(invalid)
    fixed["stages"][0]["input_sources"][0]["source"] = "input.request"
    transport = PlanningTransport([_completion(invalid), _completion(fixed)])
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = plan_task_structure(
            "Translate then independently check the result",
            provider=planner,
            repair=planner.repair,
        )
        assert result.structure is not None
        assert planner.repairs == 1 and len(transport.calls) == 2
        assert (
            "references unknown stage missing" in transport.calls[1][0][-1]["content"]
        )
        assert result.structure.execution_boundaries[0].kind == "verification"
        assert result.structure.stages[0].input_sources == {"request": "input.request"}


def test_io_patch_preserves_valid_field_identity_requiredness_and_file_semantics(
    tmp_path: Path,
) -> None:
    invalid = _payload()
    field = invalid["actors"][0]["inputs"][0]
    field.update(type="file", multiple=True, cardinality="multiple")
    field["source"] = 42  # Invalid provided metadata still needs a bounded repair.
    changed = {**_io("different"), "required": False}
    fixed = {**field, "source": "input.request"}
    transport = PlanningTransport(
        [
            _completion(invalid),
            _completion({"field_0": changed}),
            _completion(
                {
                    "field_0": {
                        "name": "request",
                        "type": "file",
                        "source": "input.request",
                    }
                }
            ),
        ]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = planner.complete_json(
            "Read the selected files", task_structure_schema()
        )
        assert result["actors"][0]["inputs"][0] == fixed
        assert planner.repairs == 2
        first_patch_schema = transport.calls[1][0][-1]["content"]
        assert '"enum": ["file"]' in first_patch_schema
        assert '"enum": [true]' in first_patch_schema


def test_invalid_schema_never_falls_back_to_a_declared_unsupported_json_mode(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    invalid = _payload()
    invalid["outputs"][0] = {}
    transport = PlanningTransport(
        [_completion(invalid), *[_completion({"field_0": {}}) for _ in range(3)]]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        planner.profile = replace(planner.profile, json_object_support="unsupported")
        result = plan_task_structure(
            "Translate", provider=planner, repair=planner.repair
        )
        assert result.structure is None and planner.repairs == 3
        assert len(transport.calls) == 4
        assert all(
            row["structured_mode"] == "strict_json_schema"
            and row["fallback_from"] is None
            for row in _rows(planner.receipts)
        )


def test_later_generations_reuse_format_evidence_only_for_the_same_provider_and_schema(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    invalid = _payload()
    invalid["outputs"][0] = {}
    transport = PlanningTransport(
        [
            _completion(invalid),
            _completion({"field_0": _io("result")}),
            _completion(_payload()),
            _completion(_payload()),
        ]
    )
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        hints: set[str] = set()
        first = _planner(client, receipts)
        first._json_mode_schema_hints = hints
        first.complete_json("Translate", task_structure_schema())
        assert hints and first.repairs == 1
        second = _planner(client, receipts)
        second._json_mode_schema_hints = hints
        second.complete_json("Translate another text", task_structure_schema())
        assert second.repairs == 0
        assert transport.calls[2][1] == {"type": "json_object"}
        other = _planner(client, receipts)
        other._json_mode_schema_hints = hints
        other.profile = replace(other.profile, model="another-model")
        other.complete_json("Translate", task_structure_schema())
        assert transport.calls[3][1]["type"] == "json_schema"


def test_invalid_io_patch_cannot_change_other_task_fields_or_bypass_repair_budget(
    tmp_path: Path,
) -> None:
    invalid = _payload()
    invalid["outputs"][0] = {}
    transport = PlanningTransport(
        [
            _completion(invalid),
            *[
                _completion({"field_0": _io("result"), "constraints": []})
                for _ in range(4)
            ],
        ]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = plan_task_structure(
            "Translate without changing meaning",
            provider=planner,
            repair=planner.repair,
        )
        assert result.structure is None
        assert planner.semantic_repairs == 3 and planner.protocol_fallbacks == 1
        assert planner.repairs == 4 and len(transport.calls) == 5
        assert '"issue": "io_schema_invalid"' in result.diagnostics[0]
        assert "additionalProperties" in result.diagnostics[0]


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


def test_parse_and_schema_corrections_share_semantic_budget_after_protocol_fallback(
    tmp_path: Path,
) -> None:
    invalid = _payload()
    invalid["lifecycle"]["persistent"] = "not a boolean"
    transport = PlanningTransport(
        [
            _completion("invalid JSON"),
            *[_completion(invalid) for _ in range(4)],
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
        assert planner.semantic_repairs == 3 and planner.protocol_fallbacks == 1
        assert planner.repairs == 4
        assert len(transport.calls) == 5
        assert len(transport.responses) == 1
        assert [row["invocation_kind"] for row in _rows(receipts)] == [
            "semantic_plan",
            "semantic_plan_repair",
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


def test_provider_failure_retains_the_prior_local_validation_issue(
    tmp_path: Path,
) -> None:
    transport = PlanningTransport(
        [
            _completion({}),
            FactoryProviderError(
                "factory_rate_limited",
                "Provider overloaded",
                details={"provider_error_type": "engine_overloaded_error"},
            ),
        ]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        with pytest.raises(FactoryProviderError) as failed:
            planner.complete_json("Translate this text", task_structure_schema())
        details = failed.value.details or {}
        assert details["provider_error_type"] == "engine_overloaded_error"
        prior = json.loads(details["prior_validation_issue"])
        assert prior["issue"] == "task_schema_invalid"
        assert prior["locations"]
        assert failed.value.code == "factory_rate_limited"
        assert len(transport.calls) == 2


def test_json_intake_uses_canonical_io_defaults_without_another_model_call(
    tmp_path: Path,
) -> None:
    sparse = _payload()
    for container in [sparse, *sparse["actors"]]:
        for kind in ("inputs", "outputs"):
            container[kind] = [
                {"name": field["name"], "type": field["type"]}
                for field in container[kind]
            ]
    # First response reproduces the known constrained-output failure. JSON mode
    # then returns a complete task with legal compact I/O definitions.
    transport = PlanningTransport([_completion({}), _completion(sparse)])
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = plan_task_structure(
            "Translate this text", provider=planner, repair=planner.repair
        )
        assert result.structure is not None, result.diagnostics
        assert len(transport.calls) == 2 and planner.repairs == 1
        field = result.structure.inputs[0]
        assert field.name == "request" and field.type == "string"
        assert field.required is True and field.multiple is False
        assert field.source == "" and field.description == ""


@pytest.mark.parametrize("typed_condition", [False, True])
@pytest.mark.parametrize(
    "rejection_message",
    [
        "response_format json_schema is not supported",
        "Moonshot Flavored JSON Schema constraint is invalid",
    ],
)
def test_only_format_support_failure_allows_one_json_object_fallback(
    tmp_path: Path,
    typed_condition: bool,
    rejection_message: str,
) -> None:
    rejection = FactoryProviderError(
        "factory_request_invalid",
        rejection_message,
        details={"rejected_field": "response_format"},
    )
    payload = (
        _condition_payload(
            {"path": "choose.selection", "operator": "==", "literal": "continue"}
        )
        if typed_condition
        else _payload()
    )
    transport = PlanningTransport([rejection, _completion(payload)])
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
        if typed_condition:
            from veyra_agent_platform.local.builder.task_structure_schema import (
                task_structure_payload,
            )

            assert (
                task_structure_payload(result)["execution_boundaries"][1]["expression"]
                == 'choose.selection == "continue"'
            )
        assert {row["model"] for row in rows} == {"kimi-k3"}


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


def test_new_pure_agent_projects_verified_models_without_rewriting_old_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _payload()
    image = {**_io("view"), "type": "image"}
    payload["outputs"].append(image)
    payload["actors"][0]["outputs"].append(image)
    payload["actors"][0]["capabilities"].append("image_generation")
    transport = PlanningTransport(
        [
            completion
            for _ in range(2)
            for completion in (
                _completion("Ready for a proposal"),
                _completion(payload),
                _completion({"verdict": "covered", "gaps": []}),
            )
        ]
    )
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        factory = client.app.state.factory
        first = factory.create_session(project_id, "Translate this text")
        old = factory.generate(project_id, first["session_id"])
        assert old["state"] == "review"
        assert old["run_availability"] == "requires_configuration"
        profiles = (
            _profile("primary", {"text_generation": CapabilityStatus.SUPPORTED}),
            _profile("image", {"image_generation": CapabilityStatus.SUPPORTED}),
        )
        monkeypatch.setattr(factory.model_registry, "list_profiles", lambda: profiles)
        second = factory.create_session(project_id, "Translate this text")
        generated = factory.generate(project_id, second["session_id"])
        assert generated["state"] == "review"
        assert generated["product_shape"] == "PURE_AGENT"
        assert generated["run_availability"] == "ready"
        models = generated["proposal_preview"]["models"]
        assert {item["slot"] for item in models} == {"primary", "image"}
        assert all(
            item["status"] == "will_bind" and not item["issue"] for item in models
        )
        model_resource = next(
            item
            for item in generated["resource_plan"]
            if item["reference"] == "veyra.component.model@1.0.0"
        )
        assert model_resource["availability"] == "ready"
        snapshot = factory.compile_review_source(project_id, second["session_id"])
        assert snapshot["run_availability"] == "ready"
        assert (
            factory.catalog.by_reference("veyra.component.model@1.0.0")["availability"]
            == "requires_configuration"
        )
        old_again = factory.get_session(project_id, first["session_id"])
        assert old_again["run_availability"] == "requires_configuration"
        assert old_again["resource_plan"] == old["resource_plan"]
        assert old_again["proposal_preview"] == old["proposal_preview"]
        assert len(transport.calls) == 6
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


def test_optional_projection_defaults_and_canonical_mappings_need_no_paid_repair(
    tmp_path: Path,
) -> None:
    payload = _payload(human_input=True)
    payload["inputs"] = [{"name": "request", "type": "string"}]
    actor = payload["actors"][0]
    actor.pop("reason")
    actor["inputs"] = [{"name": "request", "type": "string"}]
    actor["outputs"] = [{"name": "result", "type": "string"}]
    payload["outputs"] = [{"name": "result", "type": "string"}]
    payload["stages"][0]["input_sources"] = {"request": "input.request"}
    payload["stages"][0].pop("source")
    boundary = payload["execution_boundaries"][0]
    boundary["expected_schema"] = {"selection": "string"}
    for key in ("required", "expression", "branches", "checks", "capability"):
        boundary.pop(key)
    for key in (
        "skill_choices",
        "filesystem_write_roots",
        "state",
        "user_shape_override",
    ):
        payload.pop(key)
    transport = PlanningTransport([_completion(payload)])
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)))
        result = plan_task_structure(
            "Translate and wait for my selection",
            provider=planner,
            repair=planner.repair,
        )
        assert result.structure is not None, result.diagnostics
        assert result.structure.inputs[0].required is True
        assert result.structure.boundaries_of("human_input")[0].required is True
        assert result.structure.boundaries_of("human_input")[0].expected_schema == {
            "selection": "string"
        }
        assert planner.repairs == 0 and len(transport.calls) == 1


@pytest.mark.parametrize(
    ("container", "member", "value"),
    [
        ("input", "source", 42),
        ("input", "required", "false"),
        ("actor", "capabilities", {}),
        ("stage", "actor", 42),
        ("boundary", "required", "true"),
        ("boundary", "expected_schema", {"selection": False}),
        ("lifecycle", "interaction", False),
    ],
)
def test_optional_defaults_do_not_coerce_invalid_supplied_values(
    tmp_path: Path, container: str, member: str, value: Any
) -> None:
    payload = _payload(human_input=True)
    containers = {
        "input": payload["inputs"][0],
        "actor": payload["actors"][0],
        "stage": payload["stages"][0],
        "boundary": payload["execution_boundaries"][0],
        "lifecycle": payload["lifecycle"],
    }
    containers[container][member] = value
    transport = PlanningTransport([_completion(payload)])
    with _client(tmp_path, transport) as client:
        planner = _planner(client, _receipts(client, _project(client)), max_repairs=0)
        planner._json_object = True
        result = plan_task_structure(
            "Translate", provider=planner, repair=planner.repair
        )
        assert result.structure is None
        assert len(transport.calls) == 1


def test_quota_failure_retains_schema_draft_and_factory_retry_skips_full_replanning(
    tmp_path: Path,
) -> None:
    initial = _payload()
    initial["lifecycle"].update(
        persistent=True, interaction="persistent_task", entity="SavedTask"
    )
    state = {
        "entity": "SavedTask",
        "identity": "entity_id",
        "scope": "project",
        "fields": [{"name": "request", "type": "string"}],
        "statuses": ["draft"],
        "revision": True,
        "source": "Keep project revisions",
    }
    transport = PlanningTransport(
        [
            _completion(initial),
            FactoryProviderError("factory_quota_exhausted", "Account quota exhausted"),
            _completion({"state": state}),
            _completion({"verdict": "covered", "gaps": []}),
        ]
    )
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        factory = client.app.state.factory
        session = factory.create_session(
            project_id, "Translate and keep revisions", interview=False
        )
        session_id = session["session_id"]
        with pytest.raises(FactoryProviderError):
            factory.generate(project_id, session_id)
        row = factory.store.session(session_id, project_id)
        draft = json.loads(row["specification_json"])["semantic_draft"]
        assert draft["latest_schema_valid"]["state"] is None
        assert "last_semantic_valid" not in draft
        assert factory.get_session(project_id, session_id)["state"] != "review"
        assert client.app.state.projects.project_summary(project_id)["agents"] == []

        generated = factory.generate(project_id, session_id)
        assert generated["state"] == "review", generated
        assert len(transport.calls) == 4
        second_attempt = transport.calls[2][1]
        assert second_attempt["json_schema"]["schema"]["required"] == ["state"]
        stored = json.loads(
            factory.store.session(session_id, project_id)["specification_json"]
        )
        assert stored["semantic_draft"]["first_schema_valid"]["state"] is None
        assert stored["semantic_draft"]["last_semantic_valid"]["state"] == state


def test_draft_persistence_failure_stops_without_another_paid_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from veyra_agent_platform.local.factory.service import FactoryError

    transport = PlanningTransport([_completion(_payload())])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        factory = client.app.state.factory
        session = factory.create_session(project_id, "Translate", interview=False)

        def cannot_save(*args: Any) -> None:
            raise ValueError("Storage is not writable")

        monkeypatch.setattr(factory.store, "save_semantic_draft", cannot_save)
        with pytest.raises(FactoryError) as error:
            factory.generate(project_id, session["session_id"])
        assert error.value.code == "factory_draft_persistence_failed"
        assert len(transport.calls) == 1


def test_state_patch_is_retained_if_later_method_grounding_runs_out_of_quota(
    tmp_path: Path,
) -> None:
    from copy import deepcopy

    initial = _method_payload()
    initial["skill_choices"][0]["reference"] = "missing.skill@1.0.0"
    initial["lifecycle"].update(
        persistent=True, interaction="persistent_task", entity="SavedTask"
    )
    state = {
        "entity": "SavedTask",
        "identity": "entity_id",
        "scope": "project",
        "fields": {"request": "string"},
        "revision": True,
    }
    repaired = deepcopy(initial)
    repaired["state"] = state
    repaired["skill_choices"] = []
    repaired["actors"][0]["capabilities"] = ["text_generation"]
    transport = PlanningTransport(
        [
            _completion(initial),
            _completion({"state": state}),
            FactoryProviderError("factory_quota_exhausted", "Quota exhausted"),
            _completion(repaired),
            _completion({"verdict": "covered", "gaps": []}),
        ]
    )
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        factory = client.app.state.factory
        session = factory.create_session(project_id, "Keep revisions", interview=False)
        with pytest.raises(FactoryProviderError):
            factory.generate(project_id, session["session_id"])
        draft = json.loads(
            factory.store.session(session["session_id"], project_id)[
                "specification_json"
            ]
        )["semantic_draft"]
        assert draft["latest_schema_valid"]["state"] == state
        assert "last_semantic_valid" not in draft
        resumed = factory.generate(project_id, session["session_id"])
        assert resumed["state"] == "review", resumed
        assert len(transport.calls) == 5
        assert "goal" in transport.calls[3][1]["json_schema"]["schema"]["properties"]


def test_resumed_draft_cannot_drop_the_original_required_decision(
    tmp_path: Path,
) -> None:
    from copy import deepcopy

    original = _payload(human_input=True)
    original["execution_boundaries"][0].pop("required")
    changed = deepcopy(original)
    changed["execution_boundaries"] = []
    transport = PlanningTransport([])
    with _client(tmp_path, transport) as client:
        planner = _planner(
            client,
            _receipts(client, _project(client)),
            max_repairs=0,
            initial_draft={
                "first_schema_valid": original,
                "latest_schema_valid": changed,
                "last_semantic_valid": original,
            },
        )
        result = plan_task_structure(
            "Wait for my selection", provider=planner, repair=planner.repair
        )
        assert result.structure is None
        assert transport.calls == []


def test_resumed_draft_cannot_drop_a_previously_grounded_exact_skill(
    tmp_path: Path,
) -> None:
    from copy import deepcopy

    original = _method_payload()
    original["actors"][0]["capabilities"].append("workspace_read")
    changed = deepcopy(original)
    changed["skill_choices"] = []
    transport = PlanningTransport([])
    with _client(tmp_path, transport) as client:
        planner = _planner(
            client,
            _receipts(client, _project(client)),
            max_repairs=0,
            initial_draft={
                "first_schema_valid": original,
                "latest_schema_valid": changed,
                "last_semantic_valid": original,
            },
        )
        result = plan_task_structure(
            "Use the selected method", provider=planner, repair=planner.repair
        )
        assert result.structure is None
        assert transport.calls == []
        assert "method_changed" in " ".join(result.diagnostics)


@pytest.mark.parametrize("invalidation", ["schema", "resource"])
def test_invalidated_draft_does_not_carry_old_anchors_into_fresh_generation(
    tmp_path: Path, invalidation: str
) -> None:
    from veyra_agent_platform.local.builder.harness import canonical_json_hash

    transport = PlanningTransport(
        [_completion(_payload()), _completion({"verdict": "covered", "gaps": []})]
    )
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        factory = client.app.state.factory
        requirement = "Translate this text"
        session = factory.create_session(project_id, requirement, interview=False)
        old = _payload(human_input=True)
        old["goal"] = "An obsolete task"
        draft = {
            "requirement_hash": canonical_json_hash({"requirement": requirement}),
            "schema_hash": canonical_json_hash(task_structure_schema()),
            "first_schema_valid": old,
            "latest_schema_valid": old,
            "last_semantic_valid": old,
        }
        if invalidation == "schema":
            draft["schema_hash"] = "obsolete-schema"
            old["removed_schema_field"] = "unsupported by the current schema"
        else:
            draft["resource_pins"] = {
                "veyra.skill.document-analyzer@1.0.0": "obsolete-content-hash"
            }
        factory.store.save_semantic_draft(session["session_id"], draft)
        generated = factory.generate(project_id, session["session_id"])
        assert generated["state"] == "review", generated
        stored = json.loads(
            factory.store.session(session["session_id"], project_id)[
                "specification_json"
            ]
        )["semantic_draft"]
        assert stored["first_schema_valid"]["goal"] == _payload()["goal"]
        assert stored["last_semantic_valid"]["goal"] == _payload()["goal"]
        assert len(transport.calls) == 2


def test_resuming_pinned_grounded_method_does_not_pay_for_grounding_again(
    tmp_path: Path,
) -> None:
    initial = _method_payload()
    grounded = _method_payload()
    grounded["actors"][0]["capabilities"].append("workspace_read")
    transport = PlanningTransport(
        [
            _completion(initial),
            _completion(grounded),
            FactoryProviderError("factory_quota_exhausted", "Quota exhausted"),
            _completion({"verdict": "covered", "gaps": []}),
        ]
    )
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        factory = client.app.state.factory
        session = factory.create_session(
            project_id, "Read the document", interview=False
        )
        with pytest.raises(FactoryProviderError):
            factory.generate(project_id, session["session_id"])
        clone = factory.clone_generation_draft(project_id, session["session_id"])
        assert clone is not None
        receipts = _receipts(client, project_id)
        receipts.request_limit = 1
        receipts.allowed_output_contracts = frozenset({"TaskCoverageV1"})
        generated = factory.generate(project_id, clone["session_id"], receipts=receipts)
        assert generated["state"] == "review", generated
        assert len(transport.calls) == 4
        assert [receipt["output_contract"] for receipt in _rows(receipts)] == [
            "TaskCoverageV1"
        ]
