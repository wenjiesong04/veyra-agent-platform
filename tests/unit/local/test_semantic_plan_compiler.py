from __future__ import annotations

from copy import deepcopy

from tests.integration.local.test_factory_routes import VALID_SEMANTIC_PLAN
from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import ContractValidationError, new_uuid7
from veyra_agent_platform.contracts.semantic_plan import AgentSemanticPlanV1
from veyra_agent_platform.local.builder.knowledge_binding import knowledge_reference
from veyra_agent_platform.local.builder.resource_binding import (
    FILESYSTEM_READ_RESOURCE_ID,
    project_capability_catalog,
    resolve_capability_intent,
)
from veyra_agent_platform.local.builder.semantic_compiler import (
    builder_project_context,
    compile_semantic_plan,
    finalize_compiled_source,
)
from veyra_agent_platform.local.factory.compiler import compile_blueprint
from veyra_agent_platform.local.resources import ResourceCatalog

REFERENCE = "veyra.tool.filesystem.read@1.0.0"
BOUND_HASH = "a" * 64
CATALOG_HASH = "c" * 64


def _simple_plan(**changes: object) -> AgentSemanticPlanV1:
    payload = deepcopy(VALID_SEMANTIC_PLAN)
    payload.update(
        {
            "goal": "Translate the source text into the target language.",
            "suggested_name": "翻译 Agent",
            "description": "Translate user text.",
            "inputs": [{"name": "text", "type": "string"}],
            "outputs": [{"name": "translation", "type": "string"}],
            "steps": ["翻译"],
            "capability_intents": [],
            "knowledge_intents": [],
            "approval_points": [],
            "success_criteria": ["Accurate translation"],
            "user_constraints": [],
        }
    )
    payload.update(changes)
    return AgentSemanticPlanV1.from_dict(payload)


def _plan(**changes: object) -> AgentSemanticPlanV1:
    payload = deepcopy(VALID_SEMANTIC_PLAN)
    payload.update(changes)
    return AgentSemanticPlanV1.from_dict(payload)


def _tool(*, bound: bool = True, reference: str = REFERENCE) -> dict[str, object]:
    return {
        "scope": "project" if bound else "used_unbound",
        "kind": "tool",
        "resource_id": FILESYSTEM_READ_RESOURCE_ID,
        "reference": reference,
        "name": "Filesystem Read",
        "bound_content_hash": BOUND_HASH if bound else None,
        "content_hash": CATALOG_HASH,
        "binding_status": "current" if bound else "unbound",
        "availability": "ready",
        "runtime_status": "supported",
        "required_permissions": {
            "network_hosts": [],
            "tools": ["veyra.tool.filesystem.read"],
            "filesystem_read_roots": ["project"],
            "filesystem_write_roots": [],
            "shell_workspace_only": False,
        },
    }


def _document(name: str) -> dict[str, object]:
    return {
        "knowledge_id": new_uuid7(),
        "name": name,
        "slug": name.casefold(),
        "version": "1.0.0",
        "source_file_hash": "b" * 64,
        "processing": {},
    }


def test_plan_rejects_veyra_internals() -> None:
    payload = deepcopy(VALID_SEMANTIC_PLAN)
    payload["goal"] = "a" * 64
    try:
        AgentSemanticPlanV1.from_dict(payload)
    except ContractValidationError:
        return
    raise AssertionError("resource hashes must not appear in a Semantic Plan")


def test_unique_filesystem_read_is_pinned() -> None:
    context = builder_project_context(
        project_id="project",
        knowledge=[],
        project_resources=[_tool()],
        catalog_resources=[_tool(bound=False)],
    )
    compiled = compile_semantic_plan(
        _plan(capability_intents=["读取项目文件"]), context
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    blueprint = compiled.blueprint.to_dict()
    assert blueprint["required_capabilities"]["tool_refs"] == [REFERENCE]
    assert blueprint["required_capabilities"]["skill_refs"] == []
    tool_node = next(
        node for node in blueprint["nodes"] if node["component_type"] == "Tool"
    )
    assert tool_node["uses"] == REFERENCE
    assert "veyra.tool.filesystem.read" in blueprint["requested_permissions"]["tools"]
    assert "project" in blueprint["requested_permissions"]["filesystem_read_roots"]

    source, _, _ = compile_blueprint(compiled.blueprint, ResourceCatalog())
    assert source.lock[REFERENCE] != BOUND_HASH
    pinned = finalize_compiled_source(source, context).to_dict()
    assert pinned["lock"][REFERENCE] == BOUND_HASH
    assert (
        "veyra.tool.filesystem.read"
        in pinned["extensions"]["veyra"]["permissions"]["tools"]
    )


def test_two_knowledge_mentions_require_clarification() -> None:
    context = builder_project_context(
        project_id="project",
        knowledge=[_document("毕业论文"), _document("毕业论文-旧版")],
        project_resources=[],
        catalog_resources=[],
    )
    compiled = compile_semantic_plan(
        _plan(knowledge_intents=["使用毕业论文资料"]), context
    )
    assert compiled.status == "clarification"
    assert compiled.blueprint is None
    assert "毕业论文" in (compiled.question or "")
    assert "毕业论文-旧版" in (compiled.question or "")


def test_unbound_filesystem_read_is_missing_capability() -> None:
    catalog = _tool(bound=False)
    catalog["scope"] = "catalog"
    context = builder_project_context(
        project_id="project",
        knowledge=[],
        project_resources=[],
        catalog_resources=[catalog],
    )
    compiled = compile_semantic_plan(
        _plan(capability_intents=["read project files"]), context
    )
    assert compiled.status == "missing_capability"
    assert compiled.blueprint is None
    assert compiled.missing[0]["reference"] == FILESYSTEM_READ_RESOURCE_ID
    assert compiled.missing[0]["proposal"]["executable"] is False
    assert compiled.missing[0]["proposal"]["action"] == "quarantined_resource_draft"


def test_uploaded_item_input_does_not_require_project_filesystem() -> None:
    catalog = _tool(bound=False)
    catalog["scope"] = "catalog"
    compiled = compile_semantic_plan(
        _plan(
            capability_intents=[
                "read files",
                "read uploaded files",
                "接受用户上传的物品图片",
            ]
        ),
        builder_project_context(
            project_id="project",
            knowledge=[],
            project_resources=[],
            catalog_resources=[catalog],
        ),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    assert compiled.blueprint.required_capabilities.tool_refs == ()


def test_compiler_does_not_invent_catalog_skills() -> None:
    compiled = compile_semantic_plan(
        _plan(),
        builder_project_context(
            project_id="project",
            knowledge=[],
            project_resources=[],
            catalog_resources=[],
        ),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    assert compiled.blueprint.required_capabilities.skill_refs == ()
    prompt = compiled.blueprint.to_dict()["nodes"][1]["system_prompt"]
    assert "research-brief" not in prompt


def test_translation_plan_compiles_without_gift_wrap_keywords() -> None:
    compiled = compile_semantic_plan(
        _plan(
            goal="Translate between Chinese and English.",
            suggested_name="中英文翻译 Agent",
            description="Translate user text.",
            inputs=[{"name": "text", "type": "string"}],
            outputs=[{"name": "translation", "type": "string"}],
            steps=["Translate"],
            capability_intents=[],
            knowledge_intents=[],
            success_criteria=["Accurate translation"],
        ),
        builder_project_context(
            project_id="project",
            knowledge=[],
            project_resources=[],
            catalog_resources=[],
        ),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    payload = compiled.blueprint.to_dict()
    assert payload["inputs"] == {"text": "string"}
    assert payload["outputs"] == {"translation": "string"}
    assert [node["component_type"] for node in payload["nodes"]] == [
        "Start",
        "Model",
        "Output",
    ]
    prompt = payload["nodes"][1]["system_prompt"]
    assert "包装" not in prompt
    assert "Translate" in prompt


def test_meeting_notes_plan_compiles_structured_io() -> None:
    compiled = compile_semantic_plan(
        _plan(
            goal="Turn meeting notes into a summary, decisions, and todos.",
            suggested_name="会议纪要整理 Agent",
            description="Structure meeting notes.",
            inputs=[{"name": "transcript", "type": "string"}],
            outputs=[
                {"name": "summary", "type": "string"},
                {"name": "decisions", "type": "string"},
                {"name": "todos", "type": "string"},
            ],
            steps=["Read the transcript", "Extract decisions", "List todos"],
            capability_intents=[],
            knowledge_intents=[],
            success_criteria=["Todos are actionable"],
        ),
        builder_project_context(
            project_id="project",
            knowledge=[],
            project_resources=[],
            catalog_resources=[],
        ),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    payload = compiled.blueprint.to_dict()
    assert payload["inputs"] == {"transcript": "string"}
    assert payload["outputs"] == {
        "summary": "string",
        "decisions": "string",
        "todos": "string",
    }
    types = [node["component_type"] for node in payload["nodes"]]
    assert types.count("Model") == 3
    prompt = "\n".join(
        node["system_prompt"]
        for node in payload["nodes"]
        if node["component_type"] == "Model"
    )
    assert "包装" not in prompt
    assert "summary (string)" in prompt
    assert "decisions" in prompt
    assert "decisions (string)" in prompt
    assert "todos" in prompt
    assert "todos (string)" in prompt
    assert "exactly these declared fields" in prompt
    prompts = [
        node["system_prompt"]
        for node in payload["nodes"]
        if node["component_type"] == "Model"
    ]
    assert "working result" in prompts[0]
    assert "exactly these declared fields" not in prompts[0]
    assert "exactly these declared fields" in prompts[-1]


def test_underscored_output_names_are_prompted_as_contract_slugs() -> None:
    compiled = compile_semantic_plan(
        _plan(
            goal="Design gift packaging.",
            suggested_name="Gift Packaging",
            description="Design packaging.",
            inputs=[{"name": "item_image", "type": "string"}],
            outputs=[
                {"name": "final_packaging_design", "type": "object"},
                {"name": "image_generation_prompts", "type": "array"},
            ],
            steps=["Analyze the item", "Draft concepts"],
            capability_intents=[],
            knowledge_intents=[],
            success_criteria=["Design is complete"],
        ),
        builder_project_context(
            project_id="project",
            knowledge=[],
            project_resources=[],
            catalog_resources=[],
        ),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    payload = compiled.blueprint.to_dict()
    assert payload["outputs"] == {
        "final-packaging-design": "object",
        "image-generation-prompts": "array",
    }
    prompt = "\n".join(
        node["system_prompt"]
        for node in payload["nodes"]
        if node["component_type"] == "Model"
    )
    assert "final-packaging-design (object)" in prompt
    assert "image-generation-prompts (array)" in prompt
    assert "- final_packaging_design" not in prompt
    assert "- image_generation_prompts" not in prompt


def test_meeting_notes_keeps_chinese_extra_outputs_in_prompt() -> None:
    compiled = compile_semantic_plan(
        _plan(
            goal="把会议记录整理成摘要、决定和待办。",
            suggested_name="会议纪要整理 Agent",
            description="整理会议纪要。",
            inputs=[{"name": "会议记录", "type": "string"}],
            outputs=[
                {"name": "摘要", "type": "string"},
                {"name": "决定", "type": "string"},
                {"name": "待办", "type": "string"},
            ],
            steps=["阅读记录", "提取决定", "列出待办"],
            capability_intents=[],
            knowledge_intents=[],
            success_criteria=["待办可执行"],
        ),
        builder_project_context(
            project_id="project",
            knowledge=[],
            project_resources=[],
            catalog_resources=[],
        ),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    payload = compiled.blueprint.to_dict()
    assert len(payload["outputs"]) == 3
    assert set(payload["outputs"].values()) == {"string"}
    types = [node["component_type"] for node in payload["nodes"]]
    assert types.count("Model") == 3
    prompt = "\n".join(
        node["system_prompt"]
        for node in payload["nodes"]
        if node["component_type"] == "Model"
    )
    assert "摘要" in prompt
    assert "决定" in prompt
    assert "待办" in prompt
    assert "包装" not in prompt


def test_knowledge_intent_pins_real_project_document() -> None:
    document = _document("毕业论文")
    compiled = compile_semantic_plan(
        _plan(knowledge_intents=["毕业论文"]),
        builder_project_context(
            project_id="project",
            knowledge=[document],
            project_resources=[],
            catalog_resources=[],
        ),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    reference = knowledge_reference(document)
    bindings = compiled.blueprint.to_dict()["ui_suggestions"]["bindings"]
    assert any(item["reference"] == reference for item in bindings.values())
    assert compiled.documents[0]["source_file_hash"] == document["source_file_hash"]
    assert document["knowledge_id"] not in compiled.blueprint.goal


def test_tool_intent_uses_project_resource_only() -> None:
    compiled = compile_semantic_plan(
        _plan(capability_intents=["read project files"]),
        builder_project_context(
            project_id="project",
            knowledge=[],
            project_resources=[_tool()],
            catalog_resources=[_tool(bound=False)],
        ),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    assert compiled.blueprint.required_capabilities.tool_refs == (REFERENCE,)


def _step(
    key: str,
    name: str,
    purpose: str,
    kind: str,
    depends_on: list[str] | None = None,
    capability_requirement: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "semantic_key": key,
        "name": name,
        "purpose": purpose,
        "operation_kind": kind,
    }
    if depends_on:
        payload["depends_on"] = depends_on
    if capability_requirement:
        payload["capability_requirement"] = capability_requirement
    if kind == "condition":
        payload["condition_expression"] = purpose
    return payload


def _empty_context() -> object:
    return builder_project_context(
        project_id="project",
        knowledge=[],
        project_resources=[],
        catalog_resources=[],
    )


def test_v1_plan_without_step_intents_stays_three_nodes() -> None:
    compiled = compile_semantic_plan(_simple_plan(), _empty_context())
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    types = [node["component_type"] for node in compiled.blueprint.to_dict()["nodes"]]
    assert types == ["Start", "Model", "Output"]
    assert "note_intro" in compiled.blueprint.to_dict()["ui_suggestions"]["notes"]


def test_duplicate_semantic_key_is_rejected() -> None:
    payload = deepcopy(VALID_SEMANTIC_PLAN)
    payload["step_intents"] = [
        _step("summary", "总结", "总结资料", "model"),
        _step("summary", "重复", "再总结", "model"),
    ]
    try:
        AgentSemanticPlanV1.from_dict(payload)
    except ContractValidationError as exc:
        assert "unique" in str(exc)
        return
    raise AssertionError("duplicate semantic keys must be rejected")


def test_unknown_dependency_is_rejected() -> None:
    payload = deepcopy(VALID_SEMANTIC_PLAN)
    payload["step_intents"] = [
        _step("summary", "总结", "总结资料", "model", depends_on=["missing"])
    ]
    try:
        AgentSemanticPlanV1.from_dict(payload)
    except ContractValidationError as exc:
        assert "unknown key" in str(exc)
        return
    raise AssertionError("unknown depends_on must be rejected")


def test_cycle_is_rejected() -> None:
    payload = deepcopy(VALID_SEMANTIC_PLAN)
    payload["step_intents"] = [
        _step("a", "A", "first", "model", depends_on=["b"]),
        _step("b", "B", "second", "model", depends_on=["a"]),
    ]
    try:
        AgentSemanticPlanV1.from_dict(payload)
    except ContractValidationError as exc:
        assert "cycle" in str(exc)
        return
    raise AssertionError("cycles must be rejected")


def test_multiple_model_steps_compile_separate_nodes() -> None:
    compiled = compile_semantic_plan(
        _plan(
            goal="Research helper.",
            suggested_name="研究助手",
            description="总结、风险、建议。",
            steps=["总结", "风险", "建议"],
            step_intents=[
                _step("summary", "总结资料", "先总结用户资料", "model"),
                _step(
                    "risk",
                    "风险分析",
                    "分析其中风险",
                    "model",
                    depends_on=["summary"],
                ),
                _step(
                    "advice",
                    "生成建议",
                    "生成行动建议",
                    "model",
                    depends_on=["risk"],
                ),
            ],
        ),
        _empty_context(),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    payload = compiled.blueprint.to_dict()
    models = [node for node in payload["nodes"] if node["component_type"] == "Model"]
    assert [node["id"] for node in models] == ["summary", "risk", "advice"]
    assert payload["ui_suggestions"]["labels"]["summary"] == "总结资料"
    assert "先总结用户资料" in models[0]["system_prompt"]
    assert "分析其中风险" in models[1]["system_prompt"]
    assert "生成行动建议" in models[2]["system_prompt"]
    assert "先总结用户资料" not in models[1]["system_prompt"]
    assert "AgentCall" not in [node["component_type"] for node in payload["nodes"]]


def test_human_approval_and_verifier_compile_real_nodes() -> None:
    compiled = compile_semantic_plan(
        _plan(
            inputs=[{"name": "contract", "type": "string"}],
            outputs=[{"name": "summary", "type": "string"}],
            steps=["摘要", "确认", "校验"],
            step_intents=[
                _step("summarize", "合同摘要", "生成合同摘要", "model"),
                _step(
                    "confirm",
                    "用户确认",
                    "请确认合同摘要",
                    "approval",
                    depends_on=["summarize"],
                ),
                _step(
                    "verify",
                    "结果检查",
                    "output is not empty and includes risks",
                    "verification",
                    depends_on=["confirm"],
                ),
            ],
        ),
        _empty_context(),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    payload = compiled.blueprint.to_dict()
    types = [node["component_type"] for node in payload["nodes"]]
    assert "HumanApproval" in types
    assert "Verifier" in types
    assert "Output" in types
    verifier = next(
        node for node in payload["nodes"] if node["component_type"] == "Verifier"
    )
    assert verifier["checks"] == ["output.not_empty"]
    assert payload["verification"]["required"] is True
    assert compiled.warnings  # unmapped risk-content check stays a warning


def test_unmapped_verification_does_not_fake_a_verifier() -> None:
    compiled = compile_semantic_plan(
        _plan(
            step_intents=[
                _step("write", "写摘要", "生成摘要", "model"),
                _step(
                    "verify",
                    "检查风险项",
                    "结果必须包含风险项和行动建议",
                    "verification",
                    depends_on=["write"],
                ),
            ]
        ),
        _empty_context(),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    types = [node["component_type"] for node in compiled.blueprint.to_dict()["nodes"]]
    assert "Verifier" not in types
    assert types.count("Model") == 2
    assert compiled.blueprint.verification.required is False
    assert any("unsupported_verification" in item for item in compiled.warnings)


def test_capability_step_compiles_project_tool() -> None:
    compiled = compile_semantic_plan(
        _plan(
            inputs=[{"name": "path", "type": "string"}],
            step_intents=[
                _step("read", "读取项目文件", "读取项目文件", "capability"),
                _step("summarize", "总结内容", "总结内容并生成结果", "model"),
            ],
        ),
        builder_project_context(
            project_id="project",
            knowledge=[],
            project_resources=[_tool()],
            catalog_resources=[_tool(bound=False)],
        ),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    payload = compiled.blueprint.to_dict()
    tool_node = next(
        node for node in payload["nodes"] if node["component_type"] == "Tool"
    )
    assert tool_node["uses"] == REFERENCE
    assert payload["requested_permissions"]["tools"] == ["veyra.tool.filesystem.read"]
    assert payload["requested_permissions"]["network_hosts"] == []
    source, _, _ = compile_blueprint(compiled.blueprint, ResourceCatalog())
    pinned = finalize_compiled_source(
        source,
        builder_project_context(
            project_id="project",
            knowledge=[],
            project_resources=[_tool()],
            catalog_resources=[_tool(bound=False)],
        ),
    ).to_dict()
    assert pinned["lock"][REFERENCE] == BOUND_HASH


def test_capability_step_without_project_tool_is_missing() -> None:
    catalog = _tool(bound=False)
    catalog["scope"] = "catalog"
    compiled = compile_semantic_plan(
        _plan(
            step_intents=[
                _step("read", "读取项目文件", "读取项目文件", "capability"),
                _step("summarize", "总结", "总结内容", "model"),
            ]
        ),
        builder_project_context(
            project_id="project",
            knowledge=[],
            project_resources=[],
            catalog_resources=[catalog],
        ),
    )
    assert compiled.status == "missing_capability"
    assert compiled.blueprint is None


def test_transform_and_condition_compile_canonical_nodes() -> None:
    compiled = compile_semantic_plan(
        _plan(
            inputs=[
                {"name": "text", "type": "string"},
                {"name": "ready", "type": "boolean"},
            ],
            outputs=[{"name": "result", "type": "string"}],
            step_intents=[
                _step("shape", "整理字段", "result: {{text}}", "transform"),
                {
                    **_step(
                        "gate",
                        "是否就绪",
                        "ready == true",
                        "condition",
                        depends_on=["shape"],
                    ),
                    "branches": [
                        {"key": "ready", "label": "Ready"},
                        {"key": "not_ready", "label": "Not ready"},
                    ],
                },
                _step(
                    "answer",
                    "生成结果",
                    "给出最终结果",
                    "model",
                    depends_on=["gate"],
                ),
            ],
        ),
        _empty_context(),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    payload = compiled.blueprint.to_dict()
    types = [node["component_type"] for node in payload["nodes"]]
    assert types == ["Start", "Transform", "Condition", "Model", "Output"]
    transform = next(
        node for node in payload["nodes"] if node["component_type"] == "Transform"
    )
    condition = next(
        node for node in payload["nodes"] if node["component_type"] == "Condition"
    )
    assert transform["mapping"] == {"result": "{{text}}"}
    assert condition["expression"] == "ready == true"
    ports = {(item["from"], item["port"]) for item in payload["transitions"]}
    assert ("gate", "true") in ports
    assert ("gate", "false") in ports


def test_two_branch_condition_keeps_branch_local_nodes_and_typed_outputs() -> None:
    compiled = compile_semantic_plan(
        _plan(
            inputs=[{"name": "request", "type": "string"}],
            outputs=[
                {"name": "kind", "type": "string"},
                {"name": "detail", "type": "string"},
            ],
            step_intents=[
                {
                    **_step("classify", "分类", 'request != ""', "condition"),
                    "branches": [
                        {"key": "alpha", "label": "Alpha"},
                        {"key": "beta", "label": "Beta"},
                    ],
                },
                {
                    **_step(
                        "approve_alpha",
                        "Alpha approval",
                        "Approve Alpha handling",
                        "approval",
                        depends_on=["classify"],
                    ),
                    "branch_condition": "classify",
                    "branch_key": "alpha",
                },
                {
                    **_step(
                        "shape_alpha",
                        "Alpha result",
                        "Build Alpha result",
                        "transform",
                        depends_on=["approve_alpha"],
                    ),
                    "branch_condition": "classify",
                    "branch_key": "alpha",
                    "output_mapping": {
                        "kind": "alpha",
                        "detail": "{{request}}",
                    },
                },
                {
                    **_step(
                        "approve_beta",
                        "Beta approval",
                        "Approve Beta handling",
                        "approval",
                        depends_on=["classify"],
                    ),
                    "branch_condition": "classify",
                    "branch_key": "beta",
                },
                {
                    **_step(
                        "shape_beta",
                        "Beta result",
                        "Build Beta result",
                        "transform",
                        depends_on=["approve_beta"],
                    ),
                    "branch_condition": "classify",
                    "branch_key": "beta",
                    "output_mapping": {
                        "kind": "beta",
                        "detail": "{{request}}",
                    },
                },
            ],
        ),
        _empty_context(),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    payload = compiled.blueprint.to_dict()
    types = [node["component_type"] for node in payload["nodes"]]
    assert types == [
        "Start",
        "Condition",
        "HumanApproval",
        "Transform",
        "HumanApproval",
        "Transform",
        "Output",
    ]
    assert payload["outputs"] == {"kind": "string", "detail": "string"}
    edges = {
        (item["from"], item["port"], item["to"]) for item in payload["transitions"]
    }
    assert ("classify", "true", "approve_alpha") in edges
    assert ("classify", "false", "approve_beta") in edges
    assert ("approve_alpha", "approved", "shape_alpha") in edges
    assert ("approve_beta", "approved", "shape_beta") in edges
    assert ("shape_alpha", "next", "output") in edges
    assert ("shape_beta", "next", "output") in edges
    assert ("approve_alpha", "approved", "approve_beta") not in edges
    assert payload["ui_suggestions"]["branch_labels"]["classify"] == {
        "true": "Alpha",
        "false": "Beta",
    }
    note = payload["ui_suggestions"]["notes"]["note_intro"]["text"]
    assert "Alpha" in note and "Beta" in note


def test_default_note_does_not_change_behavior_hash() -> None:
    compiled = compile_semantic_plan(_plan(), _empty_context())
    assert compiled.blueprint is not None
    source, _, _ = compile_blueprint(compiled.blueprint, ResourceCatalog())
    noted = source.to_dict()
    without = deepcopy(noted)
    without["ui"].pop("notes", None)
    kept = AgentSource.from_dict(without)
    assert source.behavior_hash == kept.behavior_hash
    assert source.source_hash != kept.source_hash


def test_note_deletion_remains_valid() -> None:
    compiled = compile_semantic_plan(_plan(), _empty_context())
    assert compiled.blueprint is not None
    source, _, _ = compile_blueprint(compiled.blueprint, ResourceCatalog())
    payload = source.to_dict()
    payload["ui"].pop("notes", None)
    AgentSource.from_dict(payload)


def test_single_model_step_intent_stays_start_model_output() -> None:
    compiled = compile_semantic_plan(
        _plan(
            goal="Create a Chinese-English translation Agent.",
            suggested_name="中英文翻译 Agent",
            description="Translate between Chinese and English.",
            steps=["翻译"],
            step_intents=[
                _step("translate", "翻译", "在中英文之间翻译用户输入", "model")
            ],
        ),
        _empty_context(),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    payload = compiled.blueprint.to_dict()
    assert [node["component_type"] for node in payload["nodes"]] == [
        "Start",
        "Model",
        "Output",
    ]
    assert payload["ui_suggestions"]["labels"]["translate"] == "翻译"
    assert "note_intro" in payload["ui_suggestions"]["notes"]


def test_does_not_overgrant_unrelated_catalog_tools() -> None:
    github = _tool(bound=False, reference="veyra.tool.github.read@1.0.0")
    github["resource_id"] = "veyra.tool.github.read"
    github["name"] = "GitHub Read"
    github["required_permissions"] = {
        "network_hosts": ["api.github.com"],
        "tools": ["veyra.tool.github.read"],
        "filesystem_read_roots": [],
        "filesystem_write_roots": [],
        "shell_workspace_only": False,
    }
    compiled = compile_semantic_plan(
        _plan(
            step_intents=[
                _step("read", "读取项目文件", "读取项目文件", "capability"),
                _step("summarize", "总结", "总结内容", "model"),
            ]
        ),
        builder_project_context(
            project_id="project",
            knowledge=[],
            project_resources=[_tool()],
            catalog_resources=[_tool(bound=False), github],
        ),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    permissions = compiled.blueprint.to_dict()["requested_permissions"]
    assert permissions["tools"] == ["veyra.tool.filesystem.read"]
    assert permissions["network_hosts"] == []
    assert "veyra.tool.github.read" not in permissions["tools"]


def test_image_to_text_keeps_image_input() -> None:
    compiled = compile_semantic_plan(
        _plan(
            inputs=[{"name": "product_image", "type": "image"}],
            outputs=[{"name": "description", "type": "string"}],
            steps=["描述图片"],
            capability_intents=[],
        ),
        _empty_context(),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    payload = compiled.blueprint.to_dict()
    assert payload["inputs"] == {"product-image": "image"}
    assert payload["outputs"] == {"description": "string"}
    assert "requires_runtime_image_input" in compiled.warnings
    assert [node["component_type"] for node in payload["nodes"]] == [
        "Start",
        "Model",
        "Output",
    ]


def test_pdf_input_compiles_with_document_extract() -> None:
    compiled = compile_semantic_plan(
        _plan(
            inputs=[{"name": "report", "type": "pdf"}],
            outputs=[{"name": "summary", "type": "string"}],
            capability_intents=[],
        ),
        _empty_context(),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    assert compiled.blueprint.to_dict()["inputs"] == {"report": "pdf"}
    assert "requires_runtime_document_extract" in compiled.warnings


def test_pdf_output_still_needs_a_renderer() -> None:
    compiled = compile_semantic_plan(
        _plan(
            inputs=[{"name": "text", "type": "string"}],
            outputs=[{"name": "report", "type": "pdf"}],
            capability_intents=[],
        ),
        _empty_context(),
    )
    assert compiled.status == "missing_capability"
    assert compiled.blueprint is None
    assert compiled.missing[0]["kind"] == "pdf_renderer"


def test_image_output_compiles_an_image_model() -> None:
    compiled = compile_semantic_plan(
        _plan(
            inputs=[{"name": "prompt", "type": "string"}],
            outputs=[{"name": "picture", "type": "image"}],
            steps=["生成图片"],
            capability_intents=[],
        ),
        _empty_context(),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    assert "requires_runtime_image_output" in compiled.warnings
    payload = compiled.blueprint.to_dict()
    models = [node for node in payload["nodes"] if node["component_type"] == "Model"]
    assert models[0]["model_ref"] == "model.image"
    assert models[0]["outputs"] == {"picture": "image"}


def test_mixed_outputs_append_an_image_generation_step() -> None:
    compiled = compile_semantic_plan(
        _plan(
            inputs=[{"name": "item", "type": "image"}],
            outputs=[
                {"name": "design", "type": "object"},
                {"name": "picture", "type": "image"},
            ],
            steps=["设计包装"],
            capability_intents=[],
        ),
        _empty_context(),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    payload = compiled.blueprint.to_dict()
    models = [node for node in payload["nodes"] if node["component_type"] == "Model"]
    assert models[0]["model_ref"] == "model.primary"
    assert models[-1]["model_ref"] == "model.image"
    assert models[-1]["outputs"] == {"picture": "image"}
    edges = {
        (edge["from"], edge["port"], edge["to"]) for edge in payload["transitions"]
    }
    assert (models[-1]["id"], "next", "output") in edges


def test_catalog_pdf_parser_is_not_auto_installed() -> None:
    catalog = _tool(bound=False, reference="demo.pdf_parser@1.0.0")
    catalog["resource_id"] = "demo.pdf_parser"
    catalog["name"] = "PDF Parser"
    compiled = compile_semantic_plan(
        _plan(
            inputs=[{"name": "report", "type": "pdf"}],
            outputs=[{"name": "summary", "type": "string"}],
            capability_intents=[],
        ),
        builder_project_context(
            project_id="project",
            knowledge=[],
            project_resources=[],
            catalog_resources=[catalog],
        ),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    types = [node["component_type"] for node in compiled.blueprint.to_dict()["nodes"]]
    assert "Tool" not in types
    assert "requires_runtime_document_extract" in compiled.warnings


def test_multiple_image_inputs_compile_to_artifact_descriptor() -> None:
    compiled = compile_semantic_plan(
        _plan(
            inputs=[{"name": "photos", "type": "image", "multiple": True}],
            outputs=[{"name": "analysis", "type": "object"}],
            steps=["分析图片"],
            capability_intents=[],
        ),
        _empty_context(),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    assert compiled.blueprint.to_dict()["inputs"] == {
        "photos": {
            "type": "artifact",
            "artifact_kind": "image",
            "multiple": True,
        }
    }


def test_multi_step_v1_plan_compiles_separate_model_nodes() -> None:
    compiled = compile_semantic_plan(_plan(), _empty_context())
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    types = [node["component_type"] for node in compiled.blueprint.to_dict()["nodes"]]
    assert types == ["Start", "Model", "Model", "Output"]
    labels = compiled.blueprint.to_dict()["ui_suggestions"]["labels"]
    assert "理解礼物与对象" in labels.values()
    assert "给出材料与步骤" in labels.values()


def test_duplicate_capability_intents_reuse_one_project_tool() -> None:
    compiled = compile_semantic_plan(
        _plan(
            steps=["读取文件", "总结内容"],
            capability_intents=["Filesystem Read", "veyra.tool.filesystem.read"],
        ),
        builder_project_context(
            project_id="project",
            knowledge=[],
            project_resources=[_tool()],
            catalog_resources=[_tool(bound=False)],
        ),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    payload = compiled.blueprint.to_dict()
    tools = [node for node in payload["nodes"] if node["component_type"] == "Tool"]
    assert len(tools) == 1
    assert tools[0]["uses"] == REFERENCE
    assert payload["requested_permissions"]["tools"] == ["veyra.tool.filesystem.read"]


def test_capability_requirement_reuses_unique_project_tool() -> None:
    http = _tool(bound=True, reference="veyra.tool.http.request@1.0.0")
    http["resource_id"] = "veyra.tool.http.request"
    http["name"] = "HTTP Request"
    http["required_permissions"] = {
        "network_hosts": ["example.com"],
        "tools": ["veyra.tool.http.request"],
        "filesystem_read_roots": [],
        "filesystem_write_roots": [],
        "shell_workspace_only": False,
    }
    catalog = dict(http)
    catalog["scope"] = "used_unbound"
    catalog["bound_content_hash"] = None
    catalog["binding_status"] = "unbound"
    compiled = compile_semantic_plan(
        _plan(
            step_intents=[
                _step(
                    "quote",
                    "运费查询",
                    "查询运费",
                    "capability",
                    capability_requirement="HTTP Request",
                ),
                _step(
                    "summarize",
                    "总结报价",
                    "总结报价",
                    "model",
                    depends_on=["quote"],
                ),
            ]
        ),
        builder_project_context(
            project_id="project",
            knowledge=[],
            project_resources=[http],
            catalog_resources=[catalog],
        ),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    payload = compiled.blueprint.to_dict()
    tools = [node for node in payload["nodes"] if node["component_type"] == "Tool"]
    assert [node["component_type"] for node in payload["nodes"]] == [
        "Start",
        "Tool",
        "Model",
        "Output",
    ]
    assert tools[0]["uses"] == "veyra.tool.http.request@1.0.0"
    assert payload["requested_permissions"]["tools"] == ["veyra.tool.http.request"]
    assert payload["ui_suggestions"]["labels"][tools[0]["id"]] == "运费查询"


def test_unready_project_capability_is_not_pretended_ready() -> None:
    resource = _tool()
    resource["availability"] = "requires_configuration"
    compiled = compile_semantic_plan(
        _simple_plan(capability_intents=["Filesystem Read"]),
        builder_project_context(
            project_id="project",
            knowledge=[],
            project_resources=[resource],
            catalog_resources=[_tool(bound=False)],
        ),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    assert any("requires_configuration" in item for item in compiled.warnings)
    tools = [
        node
        for node in compiled.blueprint.to_dict()["nodes"]
        if node["component_type"] == "Tool"
    ]
    assert len(tools) == 1


def test_capability_requirement_rejected_on_model_step() -> None:
    payload = deepcopy(VALID_SEMANTIC_PLAN)
    payload["step_intents"] = [
        _step(
            "summary",
            "总结",
            "总结资料",
            "model",
            capability_requirement="HTTP Request",
        )
    ]
    try:
        AgentSemanticPlanV1.from_dict(payload)
    except ContractValidationError as exc:
        assert "capability_requirement" in str(exc)
        return
    raise AssertionError("capability_requirement must not appear on model steps")


def _custom_component(*, version: str = "1.0.0") -> dict[str, object]:
    component_id = "018f4c2d-7b3a-7abc-8def-0123456789ab"
    return {
        "scope": "project",
        "binding_status": "current",
        "bound_content_hash": "b" * 64,
        "content_hash": "b" * 64,
        "kind": "component",
        "component_class": "composite",
        "resource_id": component_id,
        "reference": f"{component_id}@{version}",
        "version": version,
        "name": "Material Estimate",
        "availability": "ready",
        "runtime_status": "supported",
        "required_permissions": {
            "network_hosts": [],
            "tools": [],
            "filesystem_read_roots": [],
            "filesystem_write_roots": [],
            "shell_workspace_only": False,
        },
        "spec": {
            "implementation_kind": "transform",
            "inputs": {"quantity": "number"},
            "outputs": {"estimate": "number"},
        },
    }


def test_custom_component_capability_compiles_to_generic_locked_node() -> None:
    component = _custom_component()
    selected = resolve_capability_intent([component], [], "Material Estimate")
    assert selected.status == "resolved"
    assert selected.selected == component
    assert project_capability_catalog([component]) == [
        {
            "name": "Material Estimate",
            "resource_id": component["resource_id"],
            "kind": "component",
            "readiness": "ready",
        }
    ]

    compiled = compile_semantic_plan(
        _plan(
            step_intents=[
                _step(
                    "estimate",
                    "材料估算",
                    "估算材料数量",
                    "capability",
                    capability_requirement="Material Estimate",
                ),
                _step(
                    "report",
                    "生成报告",
                    "输出估算结果",
                    "model",
                    depends_on=["estimate"],
                ),
            ]
        ),
        builder_project_context(
            project_id="project",
            knowledge=[],
            project_resources=[component],
            catalog_resources=[],
        ),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    blueprint = compiled.blueprint.to_dict()
    custom_nodes = [
        node
        for node in blueprint["nodes"]
        if node["component_type"] == "CustomComponent"
    ]
    assert len(custom_nodes) == 1
    assert custom_nodes[0]["uses"] == component["reference"]
    assert blueprint["required_capabilities"]["tool_refs"] == []


def test_custom_component_versions_are_not_silently_preferred() -> None:
    first = _custom_component(version="1.0.0")
    second = _custom_component(version="1.0.1")
    match = resolve_capability_intent([first, second], [], "Material Estimate")
    assert match.status == "ambiguous"
    assert {item["reference"] for item in match.candidates} == {
        first["reference"],
        second["reference"],
    }


def test_approval_fork_wires_rejected_to_the_revise_model() -> None:
    compiled = compile_semantic_plan(
        _plan(
            inputs=[{"name": "item", "type": "string"}],
            outputs=[
                {
                    "name": "design",
                    "type": "object",
                    "description": "完整终稿，含材料与结构",
                }
            ],
            step_intents=[
                _step("draft", "草案", "写出三个方向", "model"),
                _step(
                    "choose",
                    "确认方向",
                    "请确认包装方向",
                    "approval",
                    depends_on=["draft"],
                ),
                {
                    **_step(
                        "finalize",
                        "终稿",
                        "写出完整终稿",
                        "model",
                        depends_on=["choose"],
                    ),
                    "branch_condition": "choose",
                    "branch_key": "approved",
                },
                {
                    **_step(
                        "revise",
                        "修改",
                        "按反对意见修改",
                        "model",
                        depends_on=["choose"],
                    ),
                    "branch_condition": "choose",
                    "branch_key": "rejected",
                },
            ],
        ),
        _empty_context(),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    payload = compiled.blueprint.to_dict()
    edges = {
        (edge["from"], edge["port"], edge["to"]) for edge in payload["transitions"]
    }
    assert ("choose", "approved", "finalize") in edges
    assert ("choose", "rejected", "revise") in edges
    assert ("choose", "rejected", "output") not in edges
    models = {
        node["id"]: node["system_prompt"]
        for node in payload["nodes"]
        if node["component_type"] == "Model"
    }
    assert "working result" in models["draft"]
    assert "exactly these declared fields" not in models["draft"]
    assert "完整终稿，含材料与结构" in models["finalize"]
    assert "earlier working notes" in models["finalize"]
    assert "draft" in models["finalize"]


def test_approval_then_confirm_condition_collapses_to_approval_ports() -> None:
    compiled = compile_semantic_plan(
        _plan(
            inputs=[
                {"name": "item", "type": "string"},
                {"name": "decision", "type": "string"},
            ],
            outputs=[{"name": "design", "type": "object"}],
            step_intents=[
                _step("draft", "草案", "写出方向", "model"),
                _step(
                    "choose",
                    "确认",
                    "请确认方向",
                    "approval",
                    depends_on=["draft"],
                ),
                {
                    **_step(
                        "route",
                        "分流",
                        'decision == "confirm"',
                        "condition",
                        depends_on=["choose"],
                    ),
                    "branches": [
                        {"key": "confirm", "label": "确认"},
                        {"key": "revise", "label": "修改"},
                    ],
                },
                {
                    **_step(
                        "finalize",
                        "终稿",
                        "写出终稿",
                        "model",
                        depends_on=["route"],
                    ),
                    "branch_condition": "route",
                    "branch_key": "confirm",
                },
                {
                    **_step(
                        "revise",
                        "修改",
                        "修改方案",
                        "model",
                        depends_on=["route"],
                    ),
                    "branch_condition": "route",
                    "branch_key": "revise",
                },
            ],
        ),
        _empty_context(),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    assert "collapsed_redundant_approval_condition" in compiled.warnings
    payload = compiled.blueprint.to_dict()
    types = [node["component_type"] for node in payload["nodes"]]
    assert "Condition" not in types
    edges = {
        (edge["from"], edge["port"], edge["to"]) for edge in payload["transitions"]
    }
    assert ("choose", "approved", "finalize") in edges
    assert ("choose", "rejected", "revise") in edges
