from __future__ import annotations

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.local.builder.agent_loop_compiler import compile_loop_agent
from veyra_agent_platform.local.builder.specification import infer_agent_specification
from veyra_agent_platform.local.library.resource_truth import (
    annotate_resource_plan,
    bind_status_for,
    catalog_lock_pins,
    catalog_tool,
)
from veyra_agent_platform.local.resources import ResourceCatalog


def test_web_search_will_bind_when_project_has_no_pin() -> None:
    catalog = ResourceCatalog()
    search = catalog_tool(catalog, "veyra.tool.web.search")
    assert search is not None
    assert bind_status_for(search, project_resources=[]) == "will_bind"


def test_web_search_already_bound_when_project_pin_matches() -> None:
    catalog = ResourceCatalog()
    search = catalog.detail("veyra.tool.web.search", "1.0.0")
    pinned = {
        **search,
        "scope": "project",
        "bound_content_hash": search["content_hash"],
        "binding_status": "current",
    }
    assert bind_status_for(search, project_resources=[pinned]) == "already_bound"


def test_http_request_requires_host_configuration() -> None:
    catalog = ResourceCatalog()
    http = catalog.detail("veyra.tool.http.request", "1.0.0")
    assert bind_status_for(http, project_resources=[]) == "requires_configuration"


def test_annotate_resource_plan_adds_bind_status() -> None:
    catalog = ResourceCatalog()
    search = catalog.detail("veyra.tool.web.search", "1.0.0")
    plan = annotate_resource_plan(
        [
            {
                "reference": search["reference"],
                "kind": "tool",
                "availability": search["availability"],
                "runtime_status": search["runtime_status"],
            }
        ],
        catalog=catalog,
        project_resources=[],
    )
    assert plan[0]["bind_status"] == "will_bind"
    assert plan[0]["name"] == "Web Search"


def test_disabled_catalog_skill_is_unavailable() -> None:
    catalog = ResourceCatalog()
    skill = catalog.detail("veyra.skill.research-brief", "1.0.0")
    blocked = {**skill, "availability": "disabled"}
    assert bind_status_for(blocked, project_resources=[]) == "unavailable"


def test_catalog_lock_pins_include_tools_not_runtime_profile() -> None:
    catalog = ResourceCatalog()
    requirement = "创建一个研究助手，可以搜索网页并整理成报告。"
    source = compile_loop_agent(
        infer_agent_specification(requirement), catalog, requirement=requirement
    )
    pins = catalog_lock_pins(source, catalog)
    assert pins
    assert all(item["kind"] == "tool" for item in pins)
    assert all("web.search" in item["reference"] for item in pins)
    assert source.lock[pins[0]["reference"]] == pins[0]["content_hash"]
    AgentSource.from_dict(source.to_dict())
