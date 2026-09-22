from __future__ import annotations

from copy import deepcopy

from tests.integration.local.test_factory_routes import VALID_SEMANTIC_PLAN
from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import ContractValidationError, new_uuid7
from veyra_agent_platform.contracts.semantic_plan import AgentSemanticPlanV1
from veyra_agent_platform.local.builder.knowledge_binding import knowledge_reference
from veyra_agent_platform.local.builder.resource_binding import (
    FILESYSTEM_READ_RESOURCE_ID,
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
            steps=["Detect language", "Translate"],
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
    prompt = payload["nodes"][1]["system_prompt"]
    assert "包装" not in prompt
    assert "decisions" in prompt
    assert "todos" in prompt


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
    prompt = payload["nodes"][1]["system_prompt"]
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
) -> dict[str, object]:
    payload: dict[str, object] = {
        "semantic_key": key,
        "name": name,
        "purpose": purpose,
        "operation_kind": kind,
    }
    if depends_on:
        payload["depends_on"] = depends_on
    return payload


def _empty_context() -> object:
    return builder_project_context(
        project_id="project",
        knowledge=[],
        project_resources=[],
        catalog_resources=[],
    )


def test_v1_plan_without_step_intents_stays_three_nodes() -> None:
    compiled = compile_semantic_plan(_plan(), _empty_context())
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
                _step(
                    "gate",
                    "是否就绪",
                    "ready == true",
                    "condition",
                    depends_on=["shape"],
                ),
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


def test_pdf_and_image_generation_are_truthful_missing_capabilities() -> None:
    pdf_in = compile_semantic_plan(
        _plan(
            inputs=[{"name": "report", "type": "pdf"}],
            outputs=[{"name": "summary", "type": "string"}],
            capability_intents=[],
        ),
        _empty_context(),
    )
    assert pdf_in.status == "missing_capability"
    assert pdf_in.blueprint is None
    assert pdf_in.missing[0]["kind"] == "pdf_parser"
    assert pdf_in.missing[0]["proposal"]["executable"] is False

    pdf_out = compile_semantic_plan(
        _plan(
            inputs=[{"name": "text", "type": "string"}],
            outputs=[{"name": "report", "type": "pdf"}],
            capability_intents=[],
        ),
        _empty_context(),
    )
    assert pdf_out.status == "missing_capability"
    assert pdf_out.missing[0]["kind"] == "pdf_renderer"

    image_out = compile_semantic_plan(
        _plan(
            inputs=[{"name": "prompt", "type": "string"}],
            outputs=[{"name": "picture", "type": "image"}],
            capability_intents=[],
        ),
        _empty_context(),
    )
    assert image_out.status == "missing_capability"
    assert image_out.missing[0]["kind"] == "image_generation"


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
    assert compiled.status == "missing_capability"
    assert compiled.blueprint is None
    assert compiled.missing[0]["kind"] == "pdf_parser"


def test_multiple_image_inputs_compile_to_artifact_descriptor() -> None:
    compiled = compile_semantic_plan(
        _plan(
            inputs=[{"name": "photos", "type": "image", "multiple": True}],
            outputs=[{"name": "analysis", "type": "object"}],
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
