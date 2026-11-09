from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from tests.integration.local.test_factory_routes import VALID_SEMANTIC_PLAN
from tests.unit.local.test_semantic_plan_compiler import _empty_context, _step
from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.semantic_plan import AgentSemanticPlanV1
from veyra_agent_platform.local.builder.semantic_compiler import (
    compile_semantic_plan,
)
from veyra_agent_platform.local.factory.capability_profile import (
    derive_provider_capability_profile,
    structured_response_format,
)
from veyra_agent_platform.local.factory.config import FactorySettings
from veyra_agent_platform.local.factory.semantic_plan_repair import (
    bounded_repair_semantic_plan,
    classify_plan_error,
    graph_obligations,
    reject_silent_v1_degradation,
    semantic_plan_shape,
)
from veyra_agent_platform.local.factory.service import (
    _plan_schema,
    _planning_user_content,
    _repair_prompt,
)
from veyra_agent_platform.local.factory.structured_schema import (
    project_moonshot_json_schema,
)


def _base(**changes: object) -> dict[str, object]:
    payload = deepcopy(VALID_SEMANTIC_PLAN)
    payload.update(changes)
    return payload


def _real_provider_failure_fixture() -> dict[str, Any]:
    fixture_path = (
        Path(__file__).resolve().parents[3]
        / "contracts/fixtures/invalid/agent-semantic-plan-real-provider-failure.json"
    )
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_sanitized_real_provider_failure_parses_typed_step_io() -> None:
    payload = _real_provider_failure_fixture()
    plan = AgentSemanticPlanV1.from_dict(payload)
    assert plan.step_intents[2].inputs
    assert plan.step_intents[2].outputs
    compiled = compile_semantic_plan(plan, _empty_context())
    assert compiled.status == "compile_error"
    assert compiled.error is not None
    assert "condition_expression_required" in compiled.error


def test_sanitized_real_provider_mapping_compiles_typed_transform() -> None:
    payload = _real_provider_failure_fixture()
    for step in payload["step_intents"]:  # type: ignore[index,union-attr]
        if isinstance(step, dict) and step.get("semantic_key") == "classify_request":
            step["purpose"] = 'request != ""'
            step["condition_expression"] = 'request != ""'
    plan = AgentSemanticPlanV1.from_dict(payload)

    compiled = compile_semantic_plan(plan, _empty_context())

    assert compiled.status == "compiled", compiled.error
    assert compiled.blueprint is not None
    mapping = next(
        node["mapping"]
        for node in compiled.blueprint.to_dict()["nodes"]
        if node["component_type"] == "Transform"
    )
    assert mapping["priority"] == "{{advice_priority}}"


def test_sanitized_reacceptance_condition_plan_fails_closed_without_expression() -> (
    None
):
    fixture_path = Path(__file__).resolve().parents[3] / (
        "contracts/fixtures/invalid/agent-semantic-plan-condition-"
        "fallback-reacceptance-2.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    plan = AgentSemanticPlanV1.from_dict(payload)

    compiled = compile_semantic_plan(plan, _empty_context())

    assert compiled.status == "compile_error"
    assert compiled.blueprint is None
    assert compiled.error is not None
    assert "code=condition_expression_required" in compiled.error
    assert "path=step_intents[classify_priority].condition_expression" in compiled.error
    assert "expected=declared_input_comparison" in compiled.error
    assert "allowed_inputs=request" in compiled.error


def test_invalid_intermediate_transform_is_not_a_preservation_obligation() -> None:
    payload = _real_provider_failure_fixture()
    obligations = graph_obligations(payload)
    assert "condition" in obligations
    assert "branch" in obligations
    assert "approval" in obligations
    assert "multi_model" in obligations
    assert "transform" not in obligations


def test_repair_prompt_names_allowed_io_and_mapping_only_transform_repair() -> None:
    prompt = _repair_prompt(
        [
            "attempt 1: invalid AgentSemanticPlan "
            "code=MISSING_REQUIRED_INPUT "
            "path=step_intents[model_alpha].inputs"
        ],
        input_fields=["request:string"],
        output_fields=["priority:string", "summary:string"],
    )
    assert "Declared Agent inputs: request:string" in prompt
    assert "Declared Agent outputs: priority:string, summary:string" in prompt
    assert "typed data ports" in prompt
    assert "Do not omit a user-required approval" in prompt


def test_neutral_branch_approvals_compile_with_all_declared_outputs() -> None:
    payload = _base(
        goal="Classify a mode and prepare one approved response.",
        suggested_name="Mode Review",
        description="Route valid or invalid modes through separate approvals.",
        inputs=[{"name": "mode", "type": "string"}],
        outputs=[
            {"name": "status", "type": "string"},
            {"name": "summary", "type": "string"},
        ],
        steps=["Classify", "Approve the selected response", "Prepare outputs"],
        success_criteria=[],
        step_intents=[
            {
                **_step(
                    "classify_mode", "Classify mode", 'mode == "valid"', "condition"
                ),
                "branches": [
                    {"key": "valid", "label": "Valid"},
                    {"key": "invalid", "label": "Invalid"},
                ],
            },
            {
                **_step(
                    "approve_valid",
                    "Approve valid response",
                    "Approve the valid response.",
                    "approval",
                    depends_on=["classify_mode"],
                ),
                "branch_condition": "classify_mode",
                "branch_key": "valid",
            },
            {
                **_step(
                    "prepare_valid",
                    "Prepare valid response",
                    "Return status and summary for the valid case.",
                    "model",
                    depends_on=["approve_valid"],
                ),
                "branch_condition": "classify_mode",
                "branch_key": "valid",
            },
            {
                **_step(
                    "approve_invalid",
                    "Approve invalid response",
                    "Approve the invalid response.",
                    "approval",
                    depends_on=["classify_mode"],
                ),
                "branch_condition": "classify_mode",
                "branch_key": "invalid",
            },
            {
                **_step(
                    "prepare_invalid",
                    "Prepare invalid response",
                    "Return status and summary for the invalid case.",
                    "model",
                    depends_on=["approve_invalid"],
                ),
                "branch_condition": "classify_mode",
                "branch_key": "invalid",
            },
        ],
    )
    plan = AgentSemanticPlanV1.from_dict(payload)
    compiled = compile_semantic_plan(plan, _empty_context())

    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    graph = compiled.blueprint.to_dict()
    assert graph["outputs"] == {"status": "string", "summary": "string"}
    edges = {(edge["from"], edge["port"], edge["to"]) for edge in graph["transitions"]}
    assert ("classify_mode", "true", "approve_valid") in edges
    assert ("classify_mode", "false", "approve_invalid") in edges
    assert ("approve_valid", "approved", "prepare_valid") in edges
    assert ("approve_invalid", "approved", "prepare_invalid") in edges
    assert ("approve_valid", "approved", "approve_invalid") not in edges
    models = {
        node["id"]: node["system_prompt"]
        for node in graph["nodes"]
        if node["component_type"] == "Model"
    }
    for model_prompt in models.values():
        assert "status (string)" in model_prompt
        assert "summary (string)" in model_prompt
        assert "exactly these declared fields" in model_prompt
    assert graph["ui_suggestions"]["branch_labels"]["classify_mode"] == {
        "true": "Valid",
        "false": "Invalid",
    }
    note = graph["ui_suggestions"]["notes"]["note_intro"]["text"]
    assert "true=Valid" in note and "false=Invalid" in note
    assert 'classify_mode: mode == "valid"' in note


def test_sibling_branch_dependency_is_rejected() -> None:
    payload = _base(
        inputs=[{"name": "mode", "type": "string"}],
        outputs=[{"name": "status", "type": "string"}],
        step_intents=[
            {
                **_step("classify", "Classify", 'mode == "valid"', "condition"),
                "branches": [
                    {"key": "valid", "label": "Valid"},
                    {"key": "invalid", "label": "Invalid"},
                ],
            },
            {
                **_step(
                    "approve_valid",
                    "Approve valid",
                    "Approve valid",
                    "approval",
                    ["classify"],
                ),
                "branch_condition": "classify",
                "branch_key": "valid",
            },
            {
                **_step(
                    "approve_invalid",
                    "Approve invalid",
                    "Approve invalid",
                    "approval",
                    ["classify"],
                ),
                "branch_condition": "classify",
                "branch_key": "invalid",
            },
            {
                **_step(
                    "prepare_valid",
                    "Prepare valid",
                    "Prepare valid",
                    "model",
                    ["approve_invalid"],
                ),
                "branch_condition": "classify",
                "branch_key": "valid",
            },
        ],
    )
    try:
        AgentSemanticPlanV1.from_dict(payload)
    except ContractValidationError as exc:
        assert "cannot depend on a sibling branch" in str(exc)
        return
    raise AssertionError("sibling branch dependencies must fail closed")


def test_approval_semantic_plan_parses() -> None:
    plan = AgentSemanticPlanV1.from_dict(
        _base(
            step_intents=[
                _step("summarize", "摘要", "生成合同摘要", "model"),
                _step(
                    "confirm",
                    "确认",
                    "请确认摘要",
                    "approval",
                    depends_on=["summarize"],
                ),
            ]
        )
    )
    assert [item.operation_kind for item in plan.step_intents] == [
        "model",
        "approval",
    ]


def test_verification_semantic_plan_parses() -> None:
    plan = AgentSemanticPlanV1.from_dict(
        _base(
            step_intents=[
                _step("summarize", "摘要", "生成摘要", "model"),
                _step(
                    "verify",
                    "检查",
                    "output is not empty",
                    "verification",
                    depends_on=["summarize"],
                ),
            ]
        )
    )
    assert plan.step_intents[1].operation_kind == "verification"


def test_condition_semantic_plan_parses() -> None:
    plan = AgentSemanticPlanV1.from_dict(
        _base(
            step_intents=[
                {
                    **_step("gate", "是否为空", 'input != ""', "condition"),
                    "branches": [
                        {"key": "present", "label": "Present"},
                        {"key": "empty", "label": "Empty"},
                    ],
                },
                _step(
                    "summarize",
                    "摘要",
                    "生成摘要",
                    "model",
                    depends_on=["gate"],
                ),
            ]
        )
    )
    assert plan.step_intents[0].operation_kind == "condition"
    assert plan.to_dict()["step_intents"][0]["branches"][0]["key"] == "present"


def test_non_condition_branches_are_repaired_with_a_diagnostic() -> None:
    payload = _base(
        step_intents=[
            {
                "semantic_key": "confirm",
                "name": "确认",
                "purpose": "请确认摘要",
                "operation_kind": "approval",
                "branches": [{"when": "approved"}],
            }
        ]
    )
    repaired, notes = bounded_repair_semantic_plan(payload)
    assert "dropped_invalid_branches:0" in notes
    plan = AgentSemanticPlanV1.from_dict(repaired)
    assert "branches" not in plan.to_dict()["step_intents"][0]


def test_condition_requires_two_declared_branches() -> None:
    payload = _base(
        step_intents=[
            {
                **_step("gate", "条件", 'input != ""', "condition"),
                "branches": [{"key": "only", "label": "Only"}],
            }
        ]
    )
    try:
        AgentSemanticPlanV1.from_dict(payload)
    except ContractValidationError as exc:
        assert "exactly two branches" in str(exc)
        return
    raise AssertionError("condition branch cardinality must be enforced")


def test_malformed_step_intent_is_rejected() -> None:
    payload = _base(step_intents=[{"name": "确认"}])
    try:
        AgentSemanticPlanV1.from_dict(payload)
    except ContractValidationError as exc:
        assert "step_intents[0]" in str(exc)
        assert "missing field" in str(exc)
        return
    raise AssertionError("malformed step intents must be rejected")


def test_invalid_operation_kind_is_rejected_without_alias_bypass() -> None:
    payload = _base(step_intents=[_step("review", "复核", "复核摘要", "human_review")])
    try:
        AgentSemanticPlanV1.from_dict(payload)
    except ContractValidationError as exc:
        assert "operation_kind is not supported" in str(exc)
        return
    raise AssertionError("unknown operation_kind must be rejected")


def test_invalid_operation_kind_alias_is_repaired() -> None:
    payload = _base(
        step_intents=[_step("confirm", "确认", "请确认摘要", "human_approval")]
    )
    repaired, notes = bounded_repair_semantic_plan(payload)
    assert any(item.startswith("aliased_operation_kind") for item in notes)
    plan = AgentSemanticPlanV1.from_dict(repaired)
    assert plan.step_intents[0].operation_kind == "approval"


def test_unknown_dependency_is_repaired_by_drop_and_casefold() -> None:
    payload = _base(
        step_intents=[
            _step("summary", "摘要", "生成摘要", "model"),
            _step(
                "confirm",
                "确认",
                "请确认摘要",
                "approval",
                depends_on=["SUMMARY", "missing"],
            ),
        ]
    )
    repaired, notes = bounded_repair_semantic_plan(payload)
    assert any(item.startswith("dropped_unknown_dependency") for item in notes)
    plan = AgentSemanticPlanV1.from_dict(repaired)
    assert plan.step_intents[1].depends_on == ("summary",)


def test_missing_semantic_key_is_filled_from_name() -> None:
    payload = _base(
        step_intents=[
            {
                "name": "Contract Summary",
                "purpose": "生成摘要",
                "operation_kind": "model",
            }
        ]
    )
    repaired, notes = bounded_repair_semantic_plan(payload)
    assert any(item.startswith("filled_semantic_key") for item in notes)
    plan = AgentSemanticPlanV1.from_dict(repaired)
    assert plan.step_intents[0].semantic_key == "contract_summary"


def test_v1_simple_plan_remains_compatible() -> None:
    plan = AgentSemanticPlanV1.from_dict(
        _base(
            goal="Translate the source text.",
            suggested_name="翻译 Agent",
            description="Translate user text.",
            inputs=[{"name": "text", "type": "string"}],
            outputs=[{"name": "translation", "type": "string"}],
            steps=["翻译"],
        )
    )
    assert plan.step_intents == ()
    compiled = compile_semantic_plan(plan, _empty_context())
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    types = [node["component_type"] for node in compiled.blueprint.to_dict()["nodes"]]
    assert types == ["Start", "Model", "Output"]


def test_no_silent_v1_when_approval_was_observed() -> None:
    try:
        reject_silent_v1_degradation(
            obligations=frozenset({"approval", "verification"}),
            operation_kinds=("model",),
            approval_points=(),
        )
    except ContractValidationError as exc:
        assert classify_plan_error(exc) == "silent_v1_degradation"
        return
    raise AssertionError("complex duties must not collapse to V1")


def test_no_silent_v1_when_multiple_models_were_observed() -> None:
    try:
        reject_silent_v1_degradation(
            obligations=frozenset({"multi_model"}),
            operation_kinds=("model",),
            approval_points=(),
        )
    except ContractValidationError as exc:
        assert classify_plan_error(exc) == "silent_v1_degradation"
        return
    raise AssertionError("multi-model duties must not collapse to V1")


def test_graph_obligations_include_capability_and_multi_model() -> None:
    payload = _base(
        step_intents=[
            _step("read", "读取", "读取项目文件", "capability"),
            _step("summary", "总结", "总结资料", "model", depends_on=["read"]),
            _step("risk", "风险", "分析风险", "model", depends_on=["summary"]),
        ]
    )
    assert graph_obligations(payload) == frozenset({"capability", "multi_model"})


def test_graph_obligations_keep_a_real_input_to_output_transform() -> None:
    payload = _base(
        inputs=[{"name": "text", "type": "string"}],
        outputs=[{"name": "normalized", "type": "string"}],
        step_intents=[
            {
                **_step("normalize", "Normalize", "Normalize source text", "transform"),
                "output_mapping": {"normalized": "{{text}}"},
            }
        ],
    )
    assert graph_obligations(payload) == frozenset({"transform"})


def test_graph_obligations_include_declared_branch_semantics() -> None:
    payload = _base(
        step_intents=[
            {
                **_step("gate", "分类", "分类输入", "condition"),
                "branches": [
                    {"key": "a", "label": "A"},
                    {"key": "b", "label": "B"},
                ],
            },
            {
                **_step("approve_a", "A approval", "确认 A", "approval", ["gate"]),
                "branch_condition": "gate",
                "branch_key": "a",
            },
        ]
    )
    assert graph_obligations(payload) == frozenset({"condition", "approval", "branch"})


def test_approval_points_satisfy_approval_obligation() -> None:
    reject_silent_v1_degradation(
        obligations=frozenset({"approval"}),
        operation_kinds=("model",),
        approval_points=("请确认摘要",),
    )


def test_graph_obligations_ignore_user_text() -> None:
    payload = _base(
        approval_points=["请确认合同摘要包含甲方名称"],
        step_intents=[
            _step("confirm", "确认", "请确认", "approval"),
        ],
    )
    assert graph_obligations(payload) == frozenset({"approval"})
    shape = semantic_plan_shape(payload)
    assert "请确认" not in str(shape)
    assert shape["operation_kinds"] == ["approval"]


def test_mfjs_projected_plan_schema_keeps_branch_contract_and_enums() -> None:
    original = _plan_schema()
    projected = project_moonshot_json_schema(original)
    properties = projected["properties"]["step_intents"]["items"]["properties"]
    assert "branches" in properties
    assert "condition_expression" in properties
    assert "branch_condition" in properties
    assert "branch_key" in properties
    assert "output_mapping" in properties
    assert "inputs" in properties and "outputs" in properties
    assert set(properties["branches"]["items"]["properties"]) == {"key", "label"}
    typed_inputs = properties["inputs"]["items"]["properties"]
    assert "name" in typed_inputs and "type" in typed_inputs
    mapping = properties["output_mapping"]
    assert "output" in mapping["description"].casefold()
    assert (
        "supported comparison over a declared Agent input"
        in (properties["operation_kind"]["description"])
    )
    dumped = json.dumps(projected)
    assert "$ref" not in dumped
    assert "oneOf" not in dumped
    kinds = projected["properties"]["step_intents"]["items"]["properties"][
        "operation_kind"
    ]
    assert kinds["type"] == "string"
    assert kinds["enum"] == [
        "model",
        "capability",
        "transform",
        "condition",
        "approval",
        "verification",
    ]
    assert "capability_requirement" in properties
    fmt = structured_response_format(
        derive_provider_capability_profile(FactorySettings()),
        name="agent_semantic_plan",
        schema=original,
    )
    assert (
        fmt["json_schema"]["schema"]["properties"]["step_intents"]["items"][
            "properties"
        ]["operation_kind"]["enum"]
        == kinds["enum"]
    )
    assert fmt["json_schema"]["schema"] == projected


def test_mfjs_projection_preserves_property_named_then() -> None:
    projected = project_moonshot_json_schema(
        {
            "type": "object",
            "properties": {
                "then": {"type": "string"},
                "when": {"type": "string", "enum": ["approved"]},
            },
            "required": ["when", "then"],
        }
    )
    assert projected["properties"]["then"] == {"type": "string"}
    assert projected["properties"]["when"]["enum"] == ["approved"]
    assert projected["properties"]["when"]["type"] == "string"


def test_typed_io_semantic_fields_parse_image_pdf_and_multiple() -> None:
    plan = AgentSemanticPlanV1.from_dict(
        _base(
            inputs=[
                {"name": "photo", "type": "image"},
                {"name": "photos", "type": "image", "multiple": True},
            ],
            outputs=[{"name": "analysis", "type": "object"}],
        )
    )
    assert plan.inputs[0].type == "image"
    assert plan.inputs[1].multiple is True
    assert plan.outputs[0].type == "object"
    try:
        AgentSemanticPlanV1.from_dict(
            _base(inputs=[{"name": "photo", "type": "artifact"}])
        )
    except ContractValidationError as exc:
        assert "type" in str(exc)
    else:
        raise AssertionError("compact artifact type must be rejected")


def test_policy_sentence_is_not_missing_capability() -> None:
    compiled = compile_semantic_plan(
        AgentSemanticPlanV1.from_dict(
            _base(
                capability_intents=[
                    "Do not add Tool, MCP, network, shell, filesystem, "
                    "browser, GitHub, HTTP, or web-search capabilities."
                ]
            )
        ),
        _empty_context(),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    types = [node["component_type"] for node in compiled.blueprint.to_dict()["nodes"]]
    assert "Tool" not in types


def test_planning_prompt_reuses_project_capabilities_without_hashes() -> None:
    digest = _planning_user_content(
        [
            {
                "name": "Filesystem Read",
                "resource_id": "veyra.tool.filesystem.read",
                "kind": "tool",
                "readiness": "ready",
            }
        ]
    )
    assert "Filesystem Read" in digest
    assert "veyra.tool.filesystem.read" in digest
    assert "a" * 64 not in digest
    assert "capability_requirement" in digest
    empty = _planning_user_content([])
    assert "no bound tools" in empty
    assert "branch_key to approved or rejected" in empty
    assert "typed data ports" in empty or "data edges" in empty
    assert "Do not place a condition on decision/confirm/choice" in empty
    assert "Do not store a photo as string" in empty
    assert "Image outputs use type image" in empty


def test_repairs_internal_names_condition_aliases_and_extra_branches() -> None:
    payload = _base(
        inputs=[
            {"name": "user-decision", "type": "string"},
            {"name": "selected revision", "type": "string"},
        ],
        step_intents=[
            {
                "semantic_key": "ask",
                "name": "判断信息",
                "purpose": "信息是否足够",
                "operation_kind": "condition",
                "condition_expression": "user_decision == yes",
                "branches": [
                    {"key": "true", "label": "继续"},
                    {"key": "false", "label": "追问"},
                ],
            },
            {
                "semantic_key": "again",
                "name": "再次判断",
                "purpose": "检查是否通过",
                "operation_kind": "condition",
                "condition_expression": "user_decision == yes",
                "branches": [
                    {"key": "true", "label": "输出"},
                    {"key": "false", "label": "修改"},
                ],
                "branch_condition": "again",
            },
        ],
    )
    repaired, notes = bounded_repair_semantic_plan(payload)
    names = [item["name"] for item in repaired["inputs"]]
    assert "selected revision" not in names
    assert any(item.startswith("field-") for item in names)
    assert "linearized_extra_branch" in notes
    assert "aligned_condition_field" in notes
    kept = repaired["step_intents"][0]
    assert kept["condition_expression"].startswith("user-decision")
    assert "branches" not in repaired["step_intents"][1]
