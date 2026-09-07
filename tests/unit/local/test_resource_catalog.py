from __future__ import annotations

from veyra_agent_platform.local.resources import ResourceCatalog


def test_resource_catalog_has_unique_stable_references_and_hashes() -> None:
    catalog = ResourceCatalog()

    first = catalog.resources()["resources"]
    second = catalog.resources()["resources"]

    assert first == second
    assert len({resource["reference"] for resource in first}) == len(first)
    assert all(len(resource["content_hash"]) == 64 for resource in first)
    assert all(resource["content_hash"].islower() for resource in first)
    first[0]["spec"]["fields"].append("mutated")
    assert "mutated" not in catalog.resources()["resources"][0]["spec"]["fields"]
    assert catalog.resources()["resources"][0]["name"] == "Start"
    assert "ui" in catalog.detail("veyra.tool.filesystem.read", "1.0.0")["spec"]
    snapshot = next(
        item
        for item in catalog.factory_snapshot()
        if item["reference"] == "veyra.tool.filesystem.read@1.0.0"
    )
    assert "ui" not in snapshot["spec"]


def test_component_catalog_status_and_legacy_projection_are_honest() -> None:
    catalog = ResourceCatalog()
    components = catalog.resources(kind="component")["resources"]

    agent = next(resource for resource in components if resource["name"] == "Model")
    tool = next(resource for resource in components if resource["name"] == "Tool")
    approval = next(
        resource for resource in components if resource["name"] == "HumanApproval"
    )

    assert agent["availability"] == "requires_configuration"
    assert agent["runtime_status"] == "runtime_not_configured"
    assert agent["component_class"] == "primitive"
    assert {item["component_class"] for item in components} == {"primitive"}
    assert "AgentCall" in {item["name"] for item in components}
    assert tool["availability"] == "ready"
    assert tool["runtime_status"] == "supported"
    assert approval["availability"] == "ready"
    assert approval["runtime_status"] == "supported"
    assert all(
        resource["factory_selectable"]
        for resource in components
        if resource["name"] != "AgentCall"
    )
    assert not next(item for item in components if item["name"] == "AgentCall")[
        "factory_selectable"
    ]
    assert next(item for item in catalog.components() if item["type"] == "Tool") == {
        "type": "Tool",
        "fields": ["uses"],
        "output_ports": ["next"],
        "runtime_status": "supported",
        "component_class": "primitive",
    }


def test_skill_resources_await_runtime_provider_configuration() -> None:
    skills = ResourceCatalog().resources(kind="skill")["resources"]

    assert {skill["name"] for skill in skills} == {
        "Research Brief",
        "Document Analyzer",
        "Content Planner",
        "Need Extractor",
        "Evidence Ledger",
        "File Taxonomy",
    }
    assert {skill["runtime_status"] for skill in skills} == {"runtime_not_configured"}


def test_work_template_descriptors_point_at_forkable_agent_ids() -> None:
    templates = ResourceCatalog().resources(kind="template")["resources"]
    by_fork = {item["spec"]["template_id"]: item["name"] for item in templates}
    assert by_fork == {
        "veyra.starter-agent@1.0.0": "Starter Agent",
        "veyra.document-distiller@1.0.0": "文档提炼",
        "veyra.question-researcher@1.0.0": "问题研究",
        "veyra.file-sort-planner@1.0.0": "文件整理",
    }


def test_catalog_exposes_honest_tools_and_unconfigured_mcp() -> None:
    catalog = ResourceCatalog()
    tools = catalog.resources(kind="tool")["resources"]
    mcp = catalog.resources(kind="mcp_tool")["resources"]
    by_name = {resource["name"]: resource for resource in tools}

    assert by_name["Filesystem Read"]["availability"] == "ready"
    assert by_name["Filesystem Read"]["runtime_status"] == "supported"
    assert by_name["Filesystem Write"]["availability"] == "ready"
    assert by_name["Filesystem Write"]["runtime_status"] == "supported"
    assert by_name["Filesystem Write"]["factory_selectable"] is True
    assert by_name["GitHub Read"]["availability"] == "unavailable"
    assert by_name["GitHub Read"]["factory_selectable"] is False
    assert mcp[0]["availability"] == "requires_configuration"
    assert mcp[0]["factory_selectable"] is False
    snapshot = {item["reference"] for item in catalog.factory_snapshot()}
    assert "veyra.tool.filesystem.read@1.0.0" in snapshot
    assert "veyra.tool.filesystem.write@1.0.0" in snapshot
    assert "veyra.tool.github.read@1.0.0" not in snapshot
    assert catalog.by_reference("veyra.skill.research-brief@1.0.0")["kind"] == "skill"
