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


@pytest.mark.parametrize("reference", ["input.uploaded_image", "inputs.uploaded_image"])
def test_declared_input_aliases_resolve_to_the_same_typed_field(reference: str) -> None:
    payload = design_plan()
    payload["inputs"][0]["name"] = "uploaded_image"
    payload["stages"][0]["input_sources"]["image"] = reference
    product = generate_builder_product(
        REQUIREMENT, ResourceCatalog(), planner_provider=Planner(payload)
    )
    assert product.status == "review", product.diagnostics
    assert product.orchestration is not None
    draft = next(
        n for n in product.orchestration.workflow["nodes"] if n["id"] == "draft"
    )
    assert draft["input_mapping"]["image"] == "uploadedimage"


@pytest.mark.parametrize(
    "reference, diagnostic",
    [
        ("inputs.missing", "undeclared task input"),
        ("inputs../uploaded_image", "declared input or stage.port"),
    ],
)
def test_input_aliases_cannot_create_unknown_fields_or_accept_path_expressions(
    reference: str,
    diagnostic: str,
) -> None:
    payload = design_plan()
    payload["stages"][0]["input_sources"]["image"] = reference
    product = generate_builder_product(
        REQUIREMENT, ResourceCatalog(), planner_provider=Planner(payload)
    )
    assert product.status == "blocked" and product.source is None
    assert product.blocked_reason == "planner_invalid"
    assert any(diagnostic in item for item in product.diagnostics)


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
        updated = design_plan()
        updated["success_criteria"] = [
            "Every option includes its computed budget evidence"
        ]
        return updated

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


def test_unchanged_coverage_repair_stops_without_another_model_review() -> None:
    calls = []

    def review(requirement: str, candidate: dict[str, Any]) -> tuple[str, ...]:
        calls.append(candidate)
        return ("Required budget evidence is missing",)

    product = generate_builder_product(
        REQUIREMENT,
        ResourceCatalog(),
        planner_provider=Planner(design_plan()),
        planner_repair=lambda previous, diagnostic: design_plan(),
        planner_review=review,
    )
    assert product.status == "blocked"
    assert "planner_repair_no_progress" in product.diagnostics
    assert len(calls) == 1


def test_pure_agent_retains_actor_only_image_inputs_in_its_actual_source() -> None:
    payload = {
        "schema_version": "1.0",
        "goal": "Inspect a supplied product image",
        "summary": "A single autonomous role asks missing dimensions and designs",
        "actors": [
            {
                "id": "designer",
                "role": "Designer",
                "capabilities": ["text_generation"],
                "reason": "Inspect the supplied optional image",
                "inputs": [{"name": "item_image", "type": "image", "required": False}],
                "outputs": [{"name": "result", "type": "object"}],
            }
        ],
        "inputs": [{"name": "request", "type": "string"}],
        "outputs": [{"name": "result", "type": "object"}],
        "lifecycle": {"persistent": False, "interaction": "multi_turn"},
        "stages": [],
        "execution_boundaries": [],
    }
    product = generate_builder_product(
        "Inspect a supplied product image",
        ResourceCatalog(),
        planner_provider=Planner(payload),
    )
    assert product.status == "review", product.diagnostics
    assert product.source is not None and product.orchestration is None
    fields = product.source.inputs
    assert fields["request"].compact_type == "string"
    images = [field for field in fields.values() if field.artifact_kind == "image"]
    assert len(images) == 1 and not images[0].required


def test_semantic_repair_cannot_publish_a_still_missing_user_choice() -> None:
    reviews = []

    def review(requirement: str, candidate: dict[str, Any]) -> tuple[str, ...]:
        reviews.append(candidate)
        return ("Missing choice",)

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
        planner_review=review,
    )
    assert product.status == "blocked"
    assert "planner_repair_invalid; retained_ir=last_validated" in product.diagnostics
    assert "Missing choice" in product.diagnostics
    assert len(reviews) == 1
    assert product.source is None


@pytest.mark.parametrize("failure_type", [ValueError, TypeError, KeyError])
def test_coverage_repair_failure_preserves_a_safe_terminal_diagnostic(
    failure_type: type[Exception],
) -> None:
    private = "sk-private-repair-body"

    def repair(previous: str, diagnostic: str):
        raise failure_type(private)

    product = generate_builder_product(
        REQUIREMENT,
        ResourceCatalog(),
        planner_provider=Planner(design_plan()),
        planner_repair=repair,
        planner_review=lambda requirement, candidate: ("Missing writer",),
    )
    assert product.status == "blocked"
    assert product.diagnostics[0] == (
        "planner_repair_invalid; retained_ir=last_validated"
    )
    assert "Missing writer" in product.diagnostics
    assert private not in " ".join(product.diagnostics)
    assert product.structure is not None
    assert product.source is None and product.orchestration is None


def test_semantic_correction_rechecks_the_original_task_with_revised_obligations():
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
        *repaired["constraints"],
        *repaired["success_criteria"],
    ):
        assert duty in instructions
    assert len(reviews) == 2
    for agent in product.orchestration.companions:
        assert REQUIREMENT in agent.instructions
    assert any(
        node.get("review") == "input"
        for node in product.orchestration.workflow["nodes"]
    )


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
