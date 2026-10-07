"""Builder Generation Architecture V2: structure before product shape."""

from __future__ import annotations

from dataclasses import replace

from veyra_agent_platform.contracts.common import SCHEMA_VERSION, new_uuid7
from veyra_agent_platform.contracts.task_structure import (
    ExecutionBoundary,
    TaskActor,
    TaskIOField,
    TaskLifecycle,
    TaskStage,
    TaskStructure,
)
from veyra_agent_platform.local.builder.execution_planner import compile_execution_plan
from veyra_agent_platform.local.builder.generate_product import (
    generate_builder_product,
    proposal_preview,
)
from veyra_agent_platform.local.builder.model_requirements import (
    derive_model_requirements,
)
from veyra_agent_platform.local.builder.product_shape import decide_product_shape
from veyra_agent_platform.local.builder.task_planner import plan_task_structure
from veyra_agent_platform.local.builder.workflow_orchestration import (
    materialize_workflow_source,
)
from veyra_agent_platform.local.factory.service import _model_setup_required
from veyra_agent_platform.local.resources import ResourceCatalog

TRANSLATION = "帮我做一个中英翻译 Agent"
RESEARCH = "帮我做一个研究助手，可以搜索网页并整理报告"
WORKSPACE = "帮我做一个可以查看和修改项目文件的开发助手，写文件前需要确认"
SECONDHAND = (
    "帮我做一个二手商品整理和上架助手。"
    "我会一次上传很多照片。"
    "它要识别商品、查价格、写介绍。"
    "型号看不出来就问我。"
    "价格要让我确认。"
    "每件商品状态和价格历史都要保存。"
)
GIFT = (
    "帮我做一个礼品包装设计助手。"
    "用户上传商品图片。"
    "分析商品以后生成 3 个设计方向。"
    "用户选定方案以后再生成最终设计。"
    "最后还要生成效果图。"
)
DOCUMENT = "上传一份合同。提取关键信息。如果金额超过 10 万让我审批。确认后存档。"
ENGINEER = (
    "帮我做一个可以读取项目、搜索代码、修改文件、运行测试的开发助手。"
    "修改和执行危险命令前必须确认。"
)
CRM = (
    "帮我管理客户线索。"
    "每个客户有状态。"
    "我以后会不断更新联系人、阶段和备注。"
    "成交以后改成已完成。"
)


def _kinds(structure) -> set[str]:
    return {item.kind for item in structure.execution_boundaries}


def _plan(text: str):
    result = plan_task_structure(text)
    assert result.structure is not None, result.diagnostics
    return result.structure


def test_translation_is_pure_agent() -> None:
    structure = _plan(TRANSLATION)
    decision = decide_product_shape(structure)
    assert decision.shape == "PURE_AGENT"
    assert "tool" not in _kinds(structure)
    assert "state" not in _kinds(structure)
    assert "human_approval" not in _kinds(structure)
    plan = compile_execution_plan(structure, decision=decision)
    assert [item.kind for item in plan.steps] == ["start", "agent_call", "output"]


def test_research_stays_a_single_agent() -> None:
    structure = _plan(RESEARCH)
    decision = decide_product_shape(structure)
    assert decision.shape == "PURE_AGENT"
    assert any(
        item.capability == "web_search" for item in structure.execution_boundaries
    )
    assert "condition" not in _kinds(structure)
    assert "state" not in _kinds(structure)
    model_requirements = derive_model_requirements(
        structure, compile_execution_plan(structure)
    )
    assert model_requirements[0].required == ("text_generation",)


def test_workspace_editor_uses_tool_approval_not_business_approval() -> None:
    structure = _plan(WORKSPACE)
    decision = decide_product_shape(structure)
    assert decision.shape == "PURE_AGENT"
    tools = {
        item.capability
        for item in structure.execution_boundaries
        if item.kind == "tool"
    }
    assert {"workspace_read", "workspace_write"} <= tools
    assert any(item.approval_class == "tool" for item in structure.execution_boundaries)
    assert not any(
        item.kind == "human_approval" and item.approval_class != "tool"
        for item in structure.execution_boundaries
    )


def test_secondhand_listing_is_agent_workflow() -> None:
    structure = _plan(SECONDHAND)
    decision = decide_product_shape(structure)
    assert decision.shape == "AGENT_WORKFLOW"
    images = next(item for item in structure.inputs if item.type == "image")
    assert images.multiple is True
    kinds = _kinds(structure)
    assert {
        "condition",
        "human_input",
        "human_approval",
        "state",
        "verification",
    } <= kinds
    assert structure.state is not None
    assert structure.state.entity == "SecondhandItem"
    plan = compile_execution_plan(structure, decision=decision)
    step_kinds = {item.kind for item in plan.steps}
    assert {
        "condition",
        "human_input",
        "human_approval",
        "state_write",
        "verifier",
    } <= step_kinds
    assert len(plan.actors) >= 2


def test_gift_packaging_requires_image_generation() -> None:
    structure = _plan(GIFT)
    decision = decide_product_shape(structure)
    assert decision.shape == "AGENT_WORKFLOW"
    product = generate_builder_product(GIFT, ResourceCatalog())
    assert product.resolved is not None
    missing_resources = {item.capability for item in product.resolved.missing_required}
    assert "image_generation" not in missing_resources
    assert product.status == "review"
    assert product.blocked_reason == ""
    image_requirement = next(
        item for item in product.model_requirements if item.slot == "image"
    )
    assert "image_generation" in image_requirement.required
    assert "Producing images requires image_generation" in image_requirement.reason
    assert "image generation language" in image_requirement.source
    image_resolution = next(
        item for item in product.model_resolutions if item.slot == "image"
    )
    assert image_resolution.status.value == "needs_setup"
    preview = proposal_preview(product)
    assert preview["models"][-1]["slot"] == "image"
    assert preview["models"][-1]["issue"]["missing"] == ["image_generation"]


def test_optional_model_capability_remains_optional_through_planning() -> None:
    structure = _plan(GIFT)
    structure = replace(
        structure,
        execution_boundaries=tuple(
            replace(item, required=False)
            if item.capability == "image_generation"
            else item
            for item in structure.execution_boundaries
        ),
        outputs=tuple(
            replace(item, required=False) if item.type == "image" else item
            for item in structure.outputs
        ),
    )
    plan = compile_execution_plan(structure)

    image_requirement = next(
        item
        for item in derive_model_requirements(structure, plan)
        if item.slot == "image"
    )

    assert image_requirement.required == ()
    assert image_requirement.optional == ("image_generation",)
    assert image_requirement.required_for_run is False


def test_optional_model_execution_needs_setup_until_fallback_is_compiled() -> None:
    preview = {
        "models": [
            {
                "slot": "image",
                "required": [],
                "optional": ["image_generation"],
                "status": "needs_setup",
                "issue": {
                    "code": "optional_model_capability_unavailable",
                },
            }
        ]
    }

    assert _model_setup_required(preview)


def test_missing_non_model_capability_still_uses_resource_resolver() -> None:
    product = generate_builder_product(
        "创建一个 Agent，需要 capability: unregistered_domain_tool。",
        ResourceCatalog(),
    )

    assert product.resolved is not None
    assert "unregistered_domain_tool" in {
        item.capability for item in product.resolved.missing_required
    }


def test_document_approval_has_condition_and_business_approval() -> None:
    structure = _plan(DOCUMENT)
    decision = decide_product_shape(structure)
    assert decision.shape in {"WORKFLOW", "AGENT_WORKFLOW"}
    assert any(item.kind == "condition" for item in structure.execution_boundaries)
    assert any(
        item.kind == "human_approval" and item.approval_class == "business"
        for item in structure.execution_boundaries
    )
    assert any(item.type in {"document", "pdf"} for item in structure.inputs)


def test_software_engineer_is_pure_agent_with_tool_approval() -> None:
    structure = _plan(ENGINEER)
    assert decide_product_shape(structure).shape == "PURE_AGENT"
    caps = {
        item.capability for item in structure.execution_boundaries if item.capability
    }
    assert {
        "workspace_read",
        "workspace_search",
        "workspace_write",
        "shell_exec",
    } <= caps
    assert any(item.approval_class == "tool" for item in structure.execution_boundaries)
    assert "condition" not in _kinds(structure)
    assert "verification" not in _kinds(structure)


def test_named_capability_is_extracted_without_occupation_maps() -> None:
    structure = _plan(
        "创建一个 Agent。capability: comparative_risk_method。"
        "它需要一种当前 Veyra 没有的比较风险方法。"
    )
    assert decide_product_shape(structure).shape == "PURE_AGENT"
    assert any(
        item.capability == "comparative_risk_method"
        for item in structure.execution_boundaries
    )


def test_v1_acceptance_texts_keep_capability_language() -> None:
    research = _plan(
        "创建一个研究分析助手。搜索公开资料。"
        "阅读当前项目中的研究资料。使用合适的研究方法。整理证据。输出结构化研究报告。"
    )
    assert decide_product_shape(research).shape == "PURE_AGENT"
    research_caps = {
        item.capability for item in research.execution_boundaries if item.capability
    }
    assert {
        "web_search",
        "project_knowledge",
        "research_planning",
        "evidence_synthesis",
    } <= research_caps
    engineer = _plan(
        "创建一个软件工程助手。搜索当前项目文件。阅读代码。修改指定文件。"
        "运行测试。根据测试失败继续修复。写文件和运行命令前让我确认。"
    )
    assert decide_product_shape(engineer).shape == "PURE_AGENT"
    engineer_caps = {
        item.capability for item in engineer.execution_boundaries if item.capability
    }
    assert {
        "workspace_search",
        "workspace_read",
        "workspace_write",
        "shell_exec",
    } <= engineer_caps
    assert "verification" not in _kinds(engineer)
    packaging = _plan(
        "创建一个包装分析助手。用户上传一个产品图片。"
        "Agent 根据图片和项目里的品牌规范，分析包装视觉并输出结构化分析报告。"
    )
    assert decide_product_shape(packaging).shape == "PURE_AGENT"
    packaging_caps = {
        item.capability for item in packaging.execution_boundaries if item.capability
    }
    assert {"project_knowledge", "document_analysis"} <= packaging_caps
    assert "image_generation" not in packaging_caps
    assert any(
        item.name == "analysis" and item.type == "object" for item in packaging.outputs
    )
    assert any(
        item.name == "report" and item.type == "object" for item in research.outputs
    )
    assert any(
        item.name == "result" and item.type == "string" for item in engineer.outputs
    )


def test_persistent_crm_has_state() -> None:
    structure = _plan(CRM)
    decision = decide_product_shape(structure)
    assert decision.shape in {"WORKFLOW", "AGENT_WORKFLOW"}
    assert structure.state is not None
    assert structure.state.entity == "CustomerLead"
    assert "state" in _kinds(structure)


def test_negative_packaging_industry_is_not_a_designer() -> None:
    structure = _plan("帮我研究包装产业")
    assert decide_product_shape(structure).shape == "PURE_AGENT"
    assert not any(
        item.capability == "image_generation" for item in structure.execution_boundaries
    )
    assert not any(item.type == "image" for item in structure.inputs)


def test_negative_packaging_completeness_is_not_gift_design() -> None:
    structure = _plan("帮我分析商品包装是否完整")
    assert not any(
        item.capability == "image_generation" for item in structure.execution_boundaries
    )
    assert "human_approval" not in _kinds(structure)


def test_negative_search_translation_tools_is_not_a_translator() -> None:
    structure = _plan("帮我搜索翻译工具")
    outputs = {item.name for item in structure.outputs}
    assert "translation" not in outputs


def test_negative_software_engineer_report_does_not_bind_shell() -> None:
    structure = _plan("这是一个 software engineer 的研究报告")
    caps = {
        item.capability for item in structure.execution_boundaries if item.capability
    }
    assert "workspace_write" not in caps
    assert "shell_exec" not in caps


def test_planner_stability_unknown_model_is_condition_plus_input() -> None:
    phrases = (
        "型号不知道就问我",
        "识别不了型号时请向我确认",
        "无法确定具体型号时停下来让我补充",
    )
    for text in phrases:
        kinds = _kinds(_plan(f"整理商品。{text}"))
        assert "condition" in kinds
        assert "human_input" in kinds


def test_soft_if_does_not_become_a_condition() -> None:
    structure = _plan("帮我翻译这段话，如果你觉得可以的话用更自然的英文。")
    assert "condition" not in _kinds(structure)


def test_user_can_force_a_simple_agent_with_a_warning() -> None:
    structure = _plan(SECONDHAND + "不要 Workflow，就做一个简单 Agent")
    decision = decide_product_shape(structure)
    assert decision.shape == "PURE_AGENT"
    assert decision.downgraded is True
    assert decision.warnings


def test_saying_agent_does_not_lock_secondhand_to_pure_agent() -> None:
    structure = _plan(SECONDHAND)
    assert structure.user_requested_surface == "agent"
    assert decide_product_shape(structure).shape == "AGENT_WORKFLOW"


def test_independent_capability_roles_become_multi_agent_workflow() -> None:
    structure = TaskStructure(
        schema_version=SCHEMA_VERSION,
        goal="Independent capability stages with a business gate",
        summary="Four roles that should not collapse into one Agent",
        actors=(
            TaskActor(id="analyst", role="analyst", capabilities=("vision",)),
            TaskActor(id="researcher", role="researcher", capabilities=("web_search",)),
            TaskActor(
                id="writer",
                role="writer",
                capabilities=("text_generation", "document_analysis"),
            ),
            TaskActor(id="reviewer", role="reviewer", capabilities=("workspace_read",)),
        ),
        stages=(
            TaskStage(id="analyze", summary="Analyze"),
            TaskStage(id="research", summary="Research"),
            TaskStage(id="write", summary="Write"),
            TaskStage(id="review", summary="Review"),
        ),
        entities=(),
        inputs=(TaskIOField(name="request", type="string"),),
        outputs=(TaskIOField(name="result", type="string"),),
        execution_boundaries=(
            ExecutionBoundary(kind="reasoning", stage="analyze", reason="model"),
            ExecutionBoundary(
                kind="human_approval",
                stage="review",
                reason="must confirm before continue",
                approval_class="business",
            ),
        ),
        lifecycle=TaskLifecycle(persistent=False, interaction="multi_turn"),
        orchestration_complexity="multi_actor",
        uncertainty=(),
    )
    decision = decide_product_shape(structure)
    assert decision.shape == "MULTI_AGENT_WORKFLOW"
    plan = compile_execution_plan(structure, decision=decision)
    assert plan.product_shape == "MULTI_AGENT_WORKFLOW"
    assert len(plan.actors) >= 4
    primary_requirements = {
        item.actor_id: item
        for item in derive_model_requirements(structure, plan)
        if item.slot == "primary"
    }
    assert "image_input" in primary_requirements["analyst"].required
    assert "image_input" not in primary_requirements["writer"].required
    assert "text_generation" in primary_requirements["writer"].required


def test_golden_normalized_shapes() -> None:
    expected = {
        TRANSLATION: "PURE_AGENT",
        RESEARCH: "PURE_AGENT",
        WORKSPACE: "PURE_AGENT",
        SECONDHAND: "AGENT_WORKFLOW",
        GIFT: "AGENT_WORKFLOW",
        DOCUMENT: "AGENT_WORKFLOW",
        ENGINEER: "PURE_AGENT",
        CRM: "WORKFLOW",
    }
    for text, shape in expected.items():
        structure = _plan(text)
        payload = structure.to_dict()
        restored = type(structure).from_dict(payload)
        assert restored.goal
        assert decide_product_shape(restored).shape == shape
        plan = compile_execution_plan(restored)
        assert plan.to_dict()["shape"]["shape"] == shape


def test_secondhand_compose_is_not_a_single_model_prompt() -> None:
    product = generate_builder_product(SECONDHAND, ResourceCatalog())
    assert product.orchestration is not None
    types = [node["component_type"] for node in product.orchestration.workflow["nodes"]]
    assert types[0] == "Start"
    assert "Condition" in types
    assert "HumanApproval" in types
    assert "Verifier" in types
    assert types.count("AgentCall") >= 2
    assert types[-1] == "Output"
    assert "Model" not in types
    versions = {item.agent_id: new_uuid7() for item in product.orchestration.companions}
    hashes = {
        item.agent_id: item.source_hash for item in product.orchestration.companions
    }
    source = materialize_workflow_source(
        product.orchestration, versions, source_hashes=hashes
    )
    assert any(node.review == "input" for node in source.nodes if node.review)
