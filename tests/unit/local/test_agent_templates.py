from __future__ import annotations

import pytest

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.local.projects.layout import DEFAULT_CANVAS_NOTE_ID
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.templates import (
    DOCUMENT_DISTILLER_TEMPLATE_ID,
    FILE_SORT_PLANNER_TEMPLATE_ID,
    QUESTION_RESEARCHER_TEMPLATE_ID,
    STARTER_TEMPLATE_ID,
    AgentTemplateCatalog,
    AgentTemplateError,
)


def test_starter_template_is_an_agent_internal_graph() -> None:
    starter = AgentTemplateCatalog().source(STARTER_TEMPLATE_ID)
    assert [node.component_type.value for node in starter.nodes] == [
        "Start",
        "Model",
        "Output",
    ]


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

    assert distiller.inputs["source"].compact_type == "string"
    assert distiller.inputs["need"].compact_type == "string"
    assert distiller.outputs["brief"].compact_type == "string"
    assert researcher.inputs["question"].compact_type == "string"
    assert researcher.inputs["notes"].compact_type == "string"
    assert planner.inputs["listing"].compact_type == "string"
    assert planner.inputs["goal"].compact_type == "string"
    assert planner.outputs["plan"].compact_type == "string"

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
        assert source.skill_refs == tuple(descriptor["spec"]["skill_references"])
        binding_refs = {
            binding["reference"]
            for binding in (source.ui.get("bindings") or {}).values()
            if binding["kind"] == "skill"
        }
        assert binding_refs == set(source.skill_refs)
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


def test_templates_include_a_default_canvas_note() -> None:
    catalog = AgentTemplateCatalog()
    for template_id in (
        STARTER_TEMPLATE_ID,
        DOCUMENT_DISTILLER_TEMPLATE_ID,
        QUESTION_RESEARCHER_TEMPLATE_ID,
        FILE_SORT_PLANNER_TEMPLATE_ID,
    ):
        source = catalog.source(template_id)
        note = (source.ui.get("notes") or {}).get(DEFAULT_CANVAS_NOTE_ID)
        assert note is not None
        assert note["text"]
        assert note["y"] == -220
        without = source.to_dict()
        without["ui"].pop("notes", None)
        kept = AgentSource.from_dict(without)
        assert source.behavior_hash == kept.behavior_hash


def test_unknown_template_is_rejected() -> None:
    with pytest.raises(AgentTemplateError, match="unknown Agent template"):
        AgentTemplateCatalog().source("veyra.missing@1.0.0")
