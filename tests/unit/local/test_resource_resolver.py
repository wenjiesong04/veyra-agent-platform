from __future__ import annotations

from copy import deepcopy

from veyra_agent_platform.contracts.capability import CapabilityRequirement
from veyra_agent_platform.local.builder.agent_composer import compose_loop_agent
from veyra_agent_platform.local.builder.capability_requirements import (
    claimed_resource_references,
    derive_capability_requirements,
)
from veyra_agent_platform.local.builder.specification import infer_agent_specification
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.resources.resolver import ResourceResolver

_TRANSLATE = "创建一个中英文翻译助手。用户输入一段文本，Agent 翻译成目标语言。"
_RESEARCH = (
    "创建一个研究助手。它可以搜索公开网页，结合当前 Project Knowledge，"
    "整理证据并输出结构化研究报告。"
)
_WORKSPACE_READ = (
    "创建一个工作区分析助手。它可以搜索项目文件，读取相关文件，但不能修改文件。"
)
_WORKSPACE_WRITE = (
    "创建一个代码修改助手。它需要搜索、读取和修改 Project 文件，"
    "写入之前必须获得用户批准。"
)
_IMAGE = "创建一个可以直接生成最终包装设计图片的 Agent。"
_GITHUB = "创建一个助手，读取 GitHub repository 中的文件内容。"


def _resolve(
    requirement: str,
    *,
    project_resources: list | None = None,
    knowledge_inventory: list | None = None,
    catalog_resources: list | None = None,
    secret_configured=None,
):
    catalog = ResourceCatalog()
    spec = infer_agent_specification(requirement)
    requirements = derive_capability_requirements(spec, requirement)
    plan = ResourceResolver(catalog, secret_configured=secret_configured).resolve(
        spec,
        requirements,
        project_resources=project_resources or [],
        knowledge_inventory=knowledge_inventory or [],
        catalog_resources=catalog_resources,
        requirement_text=requirement,
    )
    return spec, plan, catalog


def _by_capability(resources, capability: str):
    return [item for item in resources if capability in item.capabilities]


def test_exact_capability_match_selects_web_search() -> None:
    _spec, plan, catalog = _resolve("创建一个助手，可以搜索公开网页。")
    selected = _by_capability(plan.selected, "web_search")
    assert selected
    resource = catalog.by_reference(selected[0].reference)
    assert "web_search" in resource["capabilities"]
    assert selected[0].bind_status == "will_bind"


def test_already_bound_is_preferred_over_a_second_binding() -> None:
    catalog = ResourceCatalog()
    search = catalog.detail("veyra.tool.web.search", "1.0.0")
    skill = catalog.detail("veyra.skill.research-brief", "1.0.0")
    owned = [
        {
            **search,
            "scope": "project",
            "bound_content_hash": search["content_hash"],
            "binding_status": "current",
        },
        {
            **skill,
            "scope": "project",
            "bound_content_hash": skill["content_hash"],
            "binding_status": "current",
        },
    ]
    _spec, plan, _catalog = _resolve(_RESEARCH, project_resources=owned)
    search_plan = _by_capability(plan.selected, "web_search")[0]
    skill_plan = _by_capability(plan.selected, "research_planning")[0]
    assert search_plan.bind_status == "already_bound"
    assert skill_plan.bind_status == "already_bound"
    assert search_plan.content_hash == search["content_hash"]
    assert len(_by_capability(plan.selected, "web_search")) == 1


def test_needs_configuration_for_github_without_secret() -> None:
    spec = infer_agent_specification(_GITHUB)
    requirements = derive_capability_requirements(spec, _GITHUB)
    if not any(item.capability == "github_read" for item in requirements):
        requirements = (
            *requirements,
            CapabilityRequirement(
                capability="github_read",
                required=True,
                network="required",
                side_effect="read",
            ),
        )
    plan = ResourceResolver(ResourceCatalog()).resolve(
        spec, requirements, requirement_text=_GITHUB
    )
    assert plan.needs_configuration
    assert all("github_read" in item.capabilities for item in plan.needs_configuration)
    source = compose_loop_agent(spec, plan, requirement=_GITHUB)
    github = plan.needs_configuration[0]
    assert source.lock[github.reference] == github.content_hash
    assert github.resource_id in source.permissions.tools
    assert not _by_capability(plan.selected, "web_search")
    assert not _by_capability(plan.selected, "github_read")


def test_missing_required_image_generation() -> None:
    _spec, plan, _catalog = _resolve(_IMAGE)
    assert any(item.capability == "image_generation" for item in plan.missing_required)
    assert not any("image" in item.resource_id for item in plan.selected)


def test_unavailable_and_design_only_are_rejected() -> None:
    catalog = ResourceCatalog()
    snapshot = list(catalog.resources()["resources"])
    search = next(
        item for item in snapshot if item["resource_id"] == "veyra.tool.web.search"
    )
    blocked = deepcopy(search)
    blocked["availability"] = "unavailable"
    template = next(item for item in snapshot if item["kind"] == "template")
    templated = deepcopy(template)
    templated["capabilities"] = ["web_search"]
    templated["loop_compatible"] = False
    others = [
        item
        for item in snapshot
        if item["resource_id"] not in {search["resource_id"], template["resource_id"]}
    ]
    spec = infer_agent_specification("创建一个助手，可以搜索公开网页。")
    requirements = derive_capability_requirements(spec, spec.goal)
    plan = ResourceResolver(catalog).resolve(
        spec,
        requirements,
        catalog_resources=[blocked, templated, *others],
        requirement_text=spec.goal,
    )
    assert not _by_capability(plan.selected, "web_search")
    assert any(item.capability == "web_search" for item in plan.missing_required)


def test_factory_selectable_false_is_rejected() -> None:
    catalog = ResourceCatalog()
    mcp = catalog.detail("veyra.mcp.call", "1.0.0")
    assert mcp["factory_selectable"] is False
    spec = infer_agent_specification("创建一个助手。")
    plan = ResourceResolver(catalog).resolve(
        spec,
        (
            CapabilityRequirement(
                capability="mcp_call", required=True, network="required"
            ),
        ),
    )
    assert not plan.selected
    assert any(item.capability == "mcp_call" for item in plan.missing_required)


def test_deterministic_tie_break_prefers_specific_then_stable_id() -> None:
    catalog = ResourceCatalog()
    search = catalog.detail("veyra.tool.web.search", "1.0.0")
    generic = deepcopy(search)
    generic["resource_id"] = "veyra.tool.aaa.generic"
    generic["reference"] = "veyra.tool.aaa.generic@1.0.0"
    generic["capabilities"] = ["web_search", "http_request"]
    generic["name"] = "Generic Search"
    specific = deepcopy(search)
    specific["resource_id"] = "veyra.tool.zzz.specific"
    specific["reference"] = "veyra.tool.zzz.specific@1.0.0"
    specific["capabilities"] = ["web_search"]
    specific["name"] = "Specific Search"
    spec = infer_agent_specification("创建一个助手，可以搜索公开网页。")
    requirements = derive_capability_requirements(spec, spec.goal)
    plan = ResourceResolver(catalog).resolve(
        spec,
        requirements,
        catalog_resources=[generic, specific],
        requirement_text=spec.goal,
    )
    chosen = _by_capability(plan.selected, "web_search")[0]
    assert chosen.resource_id == "veyra.tool.zzz.specific"


def test_metadata_driven_selection_follows_capability_tags() -> None:
    catalog = ResourceCatalog()
    snapshot = list(catalog.resources()["resources"])
    mutated = []
    for item in snapshot:
        copy = deepcopy(item)
        if copy["resource_id"] == "veyra.tool.web.search":
            copy["capabilities"] = []
        if copy["resource_id"] == "veyra.tool.filesystem.search":
            copy["capabilities"] = ["web_search"]
        mutated.append(copy)
    spec = infer_agent_specification("创建一个助手，可以搜索公开网页。")
    requirements = derive_capability_requirements(spec, spec.goal)
    plan = ResourceResolver(catalog).resolve(
        spec,
        requirements,
        catalog_resources=mutated,
        requirement_text=spec.goal,
    )
    chosen = _by_capability(plan.selected, "web_search")[0]
    assert chosen.resource_id == "veyra.tool.filesystem.search"


def test_hallucinated_resource_ids_are_rejected() -> None:
    requirement = "创建一个翻译助手，使用 veyra.tool.fake.super_search。"
    spec = infer_agent_specification(requirement)
    claimed = claimed_resource_references(requirement)
    assert "veyra.tool.fake.super_search" in claimed
    plan = ResourceResolver(ResourceCatalog()).resolve(
        spec,
        derive_capability_requirements(spec, requirement),
        claimed_references=claimed,
        requirement_text=requirement,
    )
    source = compose_loop_agent(spec, plan, requirement=requirement)
    assert "veyra.tool.fake.super_search" not in source.lock
    assert "veyra.tool.fake.super_search" in plan.rejected_references


def test_translation_does_not_over_assemble() -> None:
    spec, plan, _catalog = _resolve(_TRANSLATE)
    source = compose_loop_agent(spec, plan, requirement=_TRANSLATE)
    tools = [
        item
        for item in (source.ui.get("bindings") or {}).values()
        if item.get("kind") in {"tool", "mcp_tool"}
    ]
    assert tools == []
    assert source.skill_refs == ()
    assert source.knowledge_refs == ()
    assert source.permissions.tools == ()
    assert source.permissions.network_hosts == ()
    assert plan.selected == ()


def test_research_assembles_search_skill_and_knowledge() -> None:
    knowledge = [
        {
            "knowledge_id": "01234567-89ab-7cde-89ab-0123456789ab",
            "version": "1.0.0",
            "name": "Notes",
            "source_file_hash": "a" * 64,
            "processing": {"index_status": "indexed"},
        }
    ]
    spec, plan, catalog = _resolve(_RESEARCH, knowledge_inventory=knowledge)
    source = compose_loop_agent(spec, plan, requirement=_RESEARCH)
    search = _by_capability(plan.selected, "web_search")
    skills = [item for item in plan.selected if item.kind == "skill"]
    assert search
    assert "web_search" in catalog.by_reference(search[0].reference)["capabilities"]
    assert any("research_planning" in item.capabilities for item in skills)
    assert plan.knowledge.status == "available"
    assert source.knowledge_refs
    assert source.skill_refs


def test_workspace_read_only_excludes_write_and_shell() -> None:
    spec, plan, _catalog = _resolve(_WORKSPACE_READ)
    source = compose_loop_agent(spec, plan, requirement=_WORKSPACE_READ)
    ids = {item.resource_id for item in plan.selected}
    assert "veyra.tool.filesystem.search" in ids
    assert "veyra.tool.filesystem.read" in ids
    assert "veyra.tool.filesystem.write" not in ids
    assert "veyra.tool.shell.exec" not in ids
    assert source.permissions.filesystem_write_roots == ()
    assert "project" in source.permissions.filesystem_read_roots


def test_workspace_editor_requires_write_approval_without_shell() -> None:
    spec, plan, catalog = _resolve(_WORKSPACE_WRITE)
    source = compose_loop_agent(spec, plan, requirement=_WORKSPACE_WRITE)
    ids = {item.resource_id for item in plan.selected}
    assert "veyra.tool.filesystem.search" in ids
    assert "veyra.tool.filesystem.read" in ids
    assert "veyra.tool.filesystem.write" in ids
    assert "veyra.tool.shell.exec" not in ids
    write = catalog.detail("veyra.tool.filesystem.write", "1.0.0")
    assert write["spec"]["approval_required"] is True
    assert "project" in source.permissions.filesystem_write_roots


def test_natural_language_requests_select_capabilities_not_occupations() -> None:
    research = (
        "创建一个研究分析助手。它需要：搜索公开资料；阅读当前项目中的研究资料；"
        "使用合适的研究方法；整理证据；输出结构化研究报告。"
    )
    spec, plan, catalog = _resolve(
        research,
        knowledge_inventory=[
            {
                "knowledge_id": "01234567-89ab-7cde-89ab-0123456789ab",
                "version": "1.0.0",
                "name": "market_notes.md",
                "source_file_hash": "a" * 64,
                "processing": {"index_status": "indexed"},
            }
        ],
    )
    names = {item.capability for item in derive_capability_requirements(spec, research)}
    assert {
        "web_search",
        "project_knowledge",
        "research_planning",
        "evidence_synthesis",
    } <= names
    assert "image_generation" not in names
    ids = {item.resource_id for item in plan.selected}
    assert "veyra.tool.web.search" in ids
    assert "veyra.skill.research-brief" in ids
    assert "veyra.skill.evidence-ledger" in ids
    assert plan.knowledge.status == "available"
    assert catalog.detail("veyra.tool.web.search", "1.0.0")["reference"]

    engineer = (
        "创建一个软件工程助手。它需要：搜索当前项目文件；阅读代码；修改指定文件；"
        "运行测试；根据测试失败继续修复；写文件和运行命令前让我确认。"
    )
    spec, plan, _catalog = _resolve(engineer)
    ids = {item.resource_id for item in plan.selected}
    assert ids >= {
        "veyra.tool.filesystem.search",
        "veyra.tool.filesystem.read",
        "veyra.tool.filesystem.write",
        "veyra.tool.shell.exec",
    }
    assert "veyra.tool.web.search" not in ids
    assert "veyra.tool.browser.navigate" not in ids
    assert "veyra.tool.github.read" not in ids

    packaging = (
        "创建一个包装分析助手。用户上传一个产品图片，Agent 根据图片和项目里的品牌规范，"
        "分析：包装视觉、材质、色彩、品牌一致性、改进建议。输出结构化分析报告。"
    )
    spec, plan, _catalog = _resolve(
        packaging,
        knowledge_inventory=[
            {
                "knowledge_id": "01234567-89ab-7cde-89ab-0123456789ac",
                "version": "1.0.0",
                "name": "brand_guidelines.md",
                "source_file_hash": "b" * 64,
                "processing": {"index_status": "indexed"},
            }
        ],
    )
    names = {
        item.capability for item in derive_capability_requirements(spec, packaging)
    }
    assert "image_generation" not in names
    assert "project_knowledge" in names
    assert any(item.type == "image" for item in spec.inputs)
    assert not any(item.type == "image" for item in spec.outputs)
    assert plan.knowledge.status == "available"
    assert any("document-analyzer" in item.resource_id for item in plan.selected)


def test_capability_requirements_do_not_bind_resource_ids() -> None:
    spec = infer_agent_specification(_RESEARCH)
    requirements = derive_capability_requirements(spec, _RESEARCH)
    blob = " ".join(item.capability for item in requirements)
    assert "veyra.tool." not in blob
    assert any(item.capability == "web_search" for item in requirements)


def test_resource_plan_round_trip() -> None:
    _spec, plan, _catalog = _resolve(_RESEARCH)
    restored = type(plan).from_dict(plan.to_dict())
    assert restored.to_dict() == plan.to_dict()
