from __future__ import annotations

from copy import deepcopy

from tests.integration.local.test_factory_routes import VALID_SEMANTIC_PLAN
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
    assert payload["outputs"] == {"summary": "string"}
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
    assert len(payload["outputs"]) == 1
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
