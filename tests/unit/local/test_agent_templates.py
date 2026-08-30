from __future__ import annotations

import pytest

from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.templates import (
    DOCUMENT_DISTILLER_TEMPLATE_ID,
    FILE_SORT_PLANNER_TEMPLATE_ID,
    QUESTION_RESEARCHER_TEMPLATE_ID,
    STARTER_TEMPLATE_ID,
    AgentTemplateCatalog,
    AgentTemplateError,
)


def test_work_templates_are_local_llm_graphs_with_compiled_skills() -> None:
    catalog = ResourceCatalog()
    templates = AgentTemplateCatalog(catalog)
    metadata = {item["template_id"]: item for item in templates.metadata()}
    descriptors = {
        item["spec"]["template_id"]: item
        for item in catalog.resources(kind="template")["resources"]
    }

    assert list(metadata) == [
        STARTER_TEMPLATE_ID,
        DOCUMENT_DISTILLER_TEMPLATE_ID,
        QUESTION_RESEARCHER_TEMPLATE_ID,
        FILE_SORT_PLANNER_TEMPLATE_ID,
    ]
    assert set(metadata) == set(descriptors)

    distiller = templates.source(DOCUMENT_DISTILLER_TEMPLATE_ID)
    researcher = templates.source(QUESTION_RESEARCHER_TEMPLATE_ID)
    planner = templates.source(FILE_SORT_PLANNER_TEMPLATE_ID)

    assert distiller.inputs == {"source": "string", "need": "string"}
    assert distiller.outputs == {"brief": "string"}
    assert researcher.inputs == {"question": "string", "notes": "string"}
    assert planner.inputs == {"listing": "string", "goal": "string"}
    assert planner.outputs == {"plan": "string"}

    for source, template_id in (
        (distiller, DOCUMENT_DISTILLER_TEMPLATE_ID),
        (researcher, QUESTION_RESEARCHER_TEMPLATE_ID),
        (planner, FILE_SORT_PLANNER_TEMPLATE_ID),
    ):
        descriptor = descriptors[template_id]
        prompt = source.nodes[1].system_prompt or ""
        assert source.name == descriptor["name"]
        assert source.description == descriptor["description"]
        assert [node.component_type.value for node in source.nodes] == [
            "Start",
            "Agent",
            "Output",
        ]
        assert source.permissions.tools == ()
        for skill_ref in descriptor["spec"]["skill_references"]:
            skill = catalog.by_reference(skill_ref)
            assert f"[{skill['name']}]" in prompt
            assert source.lock[skill_ref] == skill["content_hash"]


def test_instantiate_assigns_a_new_agent_id_without_tools() -> None:
    catalog = AgentTemplateCatalog()
    forked = catalog.instantiate(
        template_id=DOCUMENT_DISTILLER_TEMPLATE_ID,
        slug="my-distiller",
        name="我的提炼",
        description="项目专用提炼",
    )
    original = catalog.source(DOCUMENT_DISTILLER_TEMPLATE_ID)
    assert forked.agent_id != original.agent_id
    assert forked.slug == "my-distiller"
    assert forked.name == "我的提炼"
    assert forked.nodes[1].system_prompt == original.nodes[1].system_prompt


def test_unknown_template_is_rejected() -> None:
    with pytest.raises(AgentTemplateError, match="unknown Agent template"):
        AgentTemplateCatalog().source("veyra.missing@1.0.0")
