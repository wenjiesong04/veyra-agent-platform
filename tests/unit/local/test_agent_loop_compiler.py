from __future__ import annotations

from veyra_agent_platform.contracts.agent import AgentBlueprint, ComponentType
from veyra_agent_platform.local.builder.agent_loop_compiler import (
    compile_loop_agent,
    loop_agent_blueprint_payload,
)
from veyra_agent_platform.local.builder.specification import infer_agent_specification
from veyra_agent_platform.local.factory.compiler import resource_plan
from veyra_agent_platform.local.library.resource_truth import annotate_resource_plan
from veyra_agent_platform.local.resources import ResourceCatalog


def test_translation_agent_is_a_loop_not_a_dag() -> None:
    spec = infer_agent_specification("创建一个翻译助手，把中文翻译成自然英语。")
    source = compile_loop_agent(spec, ResourceCatalog(), requirement=spec.goal)
    assert source.is_loop
    assert source.name == "Translation Agent"
    types = {node.component_type for node in source.nodes}
    assert types == {ComponentType.START, ComponentType.MODEL, ComponentType.OUTPUT}
    assert ComponentType.CONDITION not in types
    assert ComponentType.HUMAN_APPROVAL not in types
    assert set(source.inputs) == {"text"}
    assert set(source.outputs) == {"translation"}


def test_research_agent_binds_search_as_capability() -> None:
    requirement = "创建一个研究助手，可以搜索网页并整理成报告。"
    spec = infer_agent_specification(requirement)
    source = compile_loop_agent(spec, ResourceCatalog(), requirement=requirement)
    assert source.is_loop
    assert source.name == "Research Agent"
    bindings = source.ui.get("bindings") or {}
    assert any(
        item.get("kind") == "tool" and "web.search" in str(item.get("reference") or "")
        for item in bindings.values()
    )
    assert ComponentType.TOOL not in {node.component_type for node in source.nodes}


def test_packaging_designer_declares_image_contract() -> None:
    requirement = (
        "创建一个礼品包装设计助手。"
        "用户上传物品图片并告诉它场合、收礼人和风格。"
        "它可以分析图片、参考设计知识，并生成包装方案和包装效果图。"
    )
    spec = infer_agent_specification(requirement)
    source = compile_loop_agent(spec, ResourceCatalog(), requirement=requirement)
    assert source.is_loop
    assert source.name == "Packaging Designer Agent"
    assert (
        "itemimage" in source.inputs
        or "item-image" in source.inputs
        or "productimage" in source.inputs
    )
    assert any(field.compact_type == "image" for field in source.inputs.values())
    assert any(field.compact_type == "object" for field in source.outputs.values())
    assert any(field.compact_type == "image" for field in source.outputs.values())
    assert ComponentType.CONDITION not in {node.component_type for node in source.nodes}


def test_meeting_notes_keep_named_outputs() -> None:
    spec = infer_agent_specification(
        "创建会议纪要整理 Agent，输入会议记录，输出摘要、决定和待办事项。"
    )
    source = compile_loop_agent(spec, ResourceCatalog(), requirement=spec.goal)
    prompt = source.instructions
    assert "摘要" in prompt
    assert "决定" in prompt
    assert "待办" in prompt
    assert set(source.outputs) == {"summary", "decisions", "todos"}


def test_compile_loop_reuses_project_pin_instead_of_inventing_a_new_lock() -> None:
    catalog = ResourceCatalog()
    search = catalog.detail("veyra.tool.web.search", "1.0.0")
    requirement = "创建一个研究助手，可以搜索网页并整理成报告。"
    spec = infer_agent_specification(requirement)
    owned = [
        {
            **search,
            "scope": "project",
            "bound_content_hash": search["content_hash"],
            "binding_status": "current",
        }
    ]
    source = compile_loop_agent(
        spec, catalog, requirement=requirement, project_resources=owned
    )
    assert source.lock[search["reference"]] == search["content_hash"]
    without = compile_loop_agent(spec, catalog, requirement=requirement)
    assert without.lock[search["reference"]] == search["content_hash"]


def test_compile_loop_binds_skill_from_capability_metadata() -> None:
    catalog = ResourceCatalog()
    skill = catalog.detail("veyra.skill.research-brief", "1.0.0")
    owned = [
        {
            **skill,
            "scope": "project",
            "bound_content_hash": skill["content_hash"],
            "binding_status": "current",
        }
    ]
    planned = compile_loop_agent(
        infer_agent_specification("创建一个助手，输出结构化研究报告。"),
        catalog,
        requirement="创建一个助手，输出结构化研究报告。",
        project_resources=owned,
    )
    assert skill["reference"] in planned.skill_refs
    silent = compile_loop_agent(
        infer_agent_specification("创建一个翻译助手，把中文翻译成自然英语。"),
        catalog,
        requirement="创建一个翻译助手，把中文翻译成自然英语。",
        project_resources=owned,
    )
    assert silent.skill_refs == ()


def test_compile_loop_does_not_use_hardcoded_capability_tool_map() -> None:
    import veyra_agent_platform.local.builder.agent_loop_compiler as compiler

    assert not hasattr(compiler, "_CAPABILITY_TOOLS")
    assert not hasattr(compiler, "_select_tools")


def test_loop_blueprint_payload_exposes_bindings_in_resource_plan() -> None:
    catalog = ResourceCatalog()
    requirement = "创建一个研究助手，可以搜索网页并整理成报告。"
    source = compile_loop_agent(
        infer_agent_specification(requirement), catalog, requirement=requirement
    )
    payload = loop_agent_blueprint_payload(source)
    assert payload["required_capabilities"]["tool_refs"] == []
    blueprint = AgentBlueprint.from_dict(payload)
    plan = annotate_resource_plan(
        resource_plan(blueprint, catalog),
        catalog=catalog,
        project_resources=[],
    )
    search = next(item for item in plan if "web.search" in item["reference"])
    assert search["bind_status"] == "will_bind"
    assert search["name"] == "Web Search"
