from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.builder.generate_product import generate_builder_product
from veyra_agent_platform.local.builder.workflow_orchestration import (
    materialize_workflow_source,
)
from veyra_agent_platform.local.resources import ResourceCatalog

REQUIREMENT = (
    "根据商品照片给出三个可比较的包装方案，等待我选择，再按选中的方案出图。"
    "保留预算和材料限制。"
)


def field(name: str, kind: str, source: str = "") -> dict[str, Any]:
    return {"name": name, "type": kind, "required": True, "source": source}


def design_plan() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "goal": "Three packaging options and a chosen image",
        "summary": REQUIREMENT,
        "actors": [
            {
                "id": "planner",
                "role": "analyzer",
                "capabilities": ["vision"],
                "reason": "Create three options within budget",
                "inputs": [field("image", "image")],
                "outputs": [field("options", "object")],
            },
            {
                "id": "renderer",
                "role": "renderer",
                "capabilities": ["image_generation"],
                "reason": "Render only the selected option",
                "inputs": [field("analysis", "object"), field("selection", "string")],
                "outputs": [field("render", "image"), field("result", "object")],
            },
        ],
        "stages": [
            {
                "id": "draft",
                "actor": "planner",
                "summary": "Create three choices",
                "input_sources": {"image": "input.image"},
            },
            {"id": "choose", "summary": "Wait for the user's selection"},
            {
                "id": "render",
                "actor": "renderer",
                "summary": "Render chosen design",
                "input_sources": {
                    "analysis": "draft.options",
                    "selection": "choose.selection",
                },
            },
            {"id": "verify", "summary": "Verify complete outputs"},
        ],
        "inputs": [field("image", "image")],
        "outputs": [
            field("render", "image", "render.render"),
            field("result", "object", "render.result"),
        ],
        "execution_boundaries": [
            {"kind": "multimodal", "stage": "draft", "reason": "Understand the image"},
            {
                "kind": "human_input",
                "stage": "choose",
                "reason": "User must choose",
                "question": "选择哪个方案？",
                "expected_schema": {"selection": "string"},
            },
            {
                "kind": "tool",
                "stage": "render",
                "reason": "Generate final image",
                "capability": "image_generation",
            },
            {
                "kind": "verification",
                "stage": "verify",
                "reason": "Check outputs",
                "checks": [
                    "output.not_empty",
                    "required_fields:result",
                    "schema_valid",
                ],
            },
        ],
        "lifecycle": {"persistent": False, "interaction": "multi_turn"},
        "orchestration_complexity": "multi_actor",
        "uncertainty": [],
        "constraints": ["Never render before the user chooses"],
        "success_criteria": ["Preserve the chosen option and budget"],
    }


class Planner:
    def __init__(self, value: dict[str, Any]):
        self.value = value

    def complete_json(self, prompt: str, schema: object) -> dict[str, Any]:
        return deepcopy(self.value)


def test_semantic_roles_receive_full_goal_and_typed_handoff() -> None:
    product = generate_builder_product(
        REQUIREMENT, ResourceCatalog(), planner_provider=Planner(design_plan())
    )
    assert product.status == "review", product.diagnostics
    assert product.orchestration is not None
    agents = product.orchestration.companions
    for source in agents:
        assert REQUIREMENT in source.instructions
        assert "Never render before the user chooses" in source.instructions
        assert source.is_loop
    nodes = product.orchestration.workflow["nodes"]
    draft = next(n for n in nodes if n["id"] == "draft")
    render = next(n for n in nodes if n["id"] == "render")
    assert render["input_mapping"]["analysis"] == draft["output_mapping"]["options"]
    assert (
        render["input_mapping"]["selection"]
        in next(n for n in nodes if n.get("review") == "input")["inputs"]
        if any("review" in n for n in nodes)
        else False
    )
    materialized = materialize_workflow_source(
        product.orchestration,
        {a.agent_id: new_uuid7() for a in agents},
        source_hashes={a.agent_id: a.source_hash for a in agents},
    )
    assert materialized.outputs["render"].artifact_kind == "image"
    assert materialized.outputs["result"].compact_type == "object"


@pytest.mark.parametrize(
    "reference", ["missing.options", "draft.missing", "render.result"]
)
def test_unknown_and_future_stage_sources_are_not_reviewable(reference: str) -> None:
    payload = design_plan()
    payload["stages"][2]["input_sources"]["analysis"] = reference
    product = generate_builder_product(
        REQUIREMENT, ResourceCatalog(), planner_provider=Planner(payload)
    )
    assert product.status == "blocked"
    assert product.source is None and product.orchestration is None


def test_unsupported_interaction_is_not_silently_reduced() -> None:
    payload = design_plan()
    payload["uncertainty"] = [
        "Continuous same-run revisions require unsupported looping"
    ]
    product = generate_builder_product(
        REQUIREMENT, ResourceCatalog(), planner_provider=Planner(payload)
    )
    assert product.status == "blocked"
    assert "task_requires_clarification" in product.diagnostics


def test_pure_agent_retains_the_planned_procedure_in_its_loop_instructions() -> None:
    payload = {
        "schema_version": "1.0",
        "goal": "Compare supplied options",
        "summary": "Compare and ask on ambiguity",
        "actors": [
            {"id": "reviewer", "role": "reviewer", "capabilities": ["text_generation"]}
        ],
        "stages": [
            {
                "id": "inspect",
                "actor": "reviewer",
                "summary": (
                    "Compare each supplied option against the user's ranked priorities"
                ),
                "source": "Supplied option specifications",
            },
            {
                "id": "clarify",
                "summary": "Ask for missing facts before making a recommendation",
            },
        ],
        "inputs": [field("request", "string")],
        "outputs": [field("result", "object")],
        "execution_boundaries": [],
        "lifecycle": {"persistent": False, "interaction": "multi_turn"},
        "orchestration_complexity": "single",
        "uncertainty": [],
    }
    product = generate_builder_product(
        "Compare options and ask on ambiguity",
        ResourceCatalog(),
        planner_provider=Planner(payload),
    )
    assert product.status == "review", product.diagnostics
    assert product.source.is_loop
    assert len(product.source.nodes) == 3
    for stage in payload["stages"]:
        assert stage["summary"] in product.source.instructions
    assert "Supplied option specifications" in product.source.instructions


def test_coverage_gap_requires_repair_instead_of_review() -> None:
    reviews = []
    repairs = []

    def review(requirement: str, candidate: dict[str, Any]) -> tuple[str, ...]:
        reviews.append(candidate)
        return ("The choices must carry budget evidence",) if len(reviews) == 1 else ()

    def repair(previous: str, diagnostic: str) -> dict[str, Any]:
        repairs.append(diagnostic)
        return design_plan()

    product = generate_builder_product(
        REQUIREMENT,
        ResourceCatalog(),
        planner_provider=Planner(design_plan()),
        planner_repair=repair,
        planner_review=review,
    )
    assert product.status == "review", product.diagnostics
    assert len(repairs) == 1 and len(reviews) == 2
    assert "budget evidence" in repairs[0]


def test_repair_cannot_remove_a_required_human_duty() -> None:
    def repair(previous: str, diagnostic: str) -> dict[str, Any]:
        payload = design_plan()
        payload["execution_boundaries"] = [
            item
            for item in payload["execution_boundaries"]
            if item["kind"] != "human_input"
        ]
        return payload

    product = generate_builder_product(
        REQUIREMENT,
        ResourceCatalog(),
        planner_provider=Planner(design_plan()),
        planner_repair=repair,
        planner_review=lambda requirement, candidate: ("Missing choice",),
    )
    assert product.status == "blocked"
    assert "repair_removed_required_duty" in product.diagnostics
    assert "Missing choice" in product.diagnostics


def test_repair_rephrasing_keeps_original_obligations_in_compiled_instructions() -> (
    None
):
    original = design_plan()
    repaired = design_plan()
    repaired["constraints"] = ["Use the revised budget throughout the options"]
    repaired["success_criteria"] = ["Deliver the confirmed design with cost evidence"]
    reviews = []

    def review(requirement: str, candidate: dict[str, Any]) -> tuple[str, ...]:
        reviews.append(candidate)
        return ("Improve cost evidence",) if len(reviews) == 1 else ()

    product = generate_builder_product(
        REQUIREMENT,
        ResourceCatalog(),
        planner_provider=Planner(original),
        planner_repair=lambda previous, diagnostic: repaired,
        planner_review=review,
    )
    assert product.status == "review", product.diagnostics
    instructions = "\n".join(
        agent.instructions for agent in product.orchestration.companions
    )
    for duty in (
        *original.get("constraints", []),
        *original.get("success_criteria", []),
        *repaired["constraints"],
        *repaired["success_criteria"],
    ):
        assert duty in instructions


def test_same_run_context_does_not_require_an_entity_tool() -> None:
    requirement = "先问需求，给我三个方案，让我选择和修改，确认后交付。"
    payload = {
        "schema_version": "1.0",
        "goal": "Interactive proposal assistant",
        "summary": requirement,
        "actors": [
            {"id": "advisor", "role": "advisor", "capabilities": ["text_generation"]}
        ],
        "stages": [{"id": "conversation", "actor": "advisor", "summary": requirement}],
        "inputs": [field("request", "string")],
        "outputs": [field("result", "object")],
        "execution_boundaries": [
            {
                "kind": "human_input",
                "stage": "conversation",
                "reason": "User choices",
                "question": "请补充需求或选择方案",
                "expected_schema": {"reply": "string"},
            }
        ],
        "lifecycle": {"persistent": False, "interaction": "multi_turn"},
        "orchestration_complexity": "single",
        "uncertainty": [],
        "state": {
            "entity": "proposal",
            "identity": "run",
            "scope": "conversation",
            "fields": {"selection": "string"},
            "statuses": [],
            "revision": False,
        },
        "constraints": ["Do not deliver before confirmation"],
    }
    product = generate_builder_product(
        requirement, ResourceCatalog(), planner_provider=Planner(payload)
    )
    assert product.status == "review", product.diagnostics
    assert product.source is not None and product.source.is_loop
    assert product.plan is not None and product.plan.state is None
    assert product.plan.task["state"]["scope"] == "conversation"
    assert requirement in product.source.instructions
    assert not product.source.permissions.tools

    # Autonomous questions need no fixed DAG gate: the native loop can ask based
    # on its full instructions. Coverage review and live Runtime verify behavior.
    payload["execution_boundaries"] = []
    autonomous = generate_builder_product(
        requirement, ResourceCatalog(), planner_provider=Planner(payload)
    )
    assert autonomous.status == "review", autonomous.diagnostics
    assert autonomous.source is not None and autonomous.source.is_loop

    # Changing this promise to stored records must not use native conversation memory.
    payload["lifecycle"]["persistent"] = True
    payload["state"]["scope"] = "project"
    stored = generate_builder_product(
        requirement, ResourceCatalog(), planner_provider=Planner(payload)
    )
    assert stored.status == "blocked" and stored.source is None
    assert "identity" in " ".join(stored.diagnostics)
