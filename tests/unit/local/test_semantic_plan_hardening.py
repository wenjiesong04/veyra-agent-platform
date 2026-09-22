from __future__ import annotations

import json
from copy import deepcopy

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
)
from veyra_agent_platform.local.factory.structured_schema import (
    project_moonshot_json_schema,
)


def _base(**changes: object) -> dict[str, object]:
    payload = deepcopy(VALID_SEMANTIC_PLAN)
    payload.update(changes)
    return payload


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
    assert "branch_condition" in properties
    assert "branch_key" in properties
    assert "output_mapping" in properties
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
