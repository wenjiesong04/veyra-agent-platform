from copy import deepcopy
from dataclasses import replace

import pytest

from veyra_agent_platform.contracts.common import freeze_json
from veyra_agent_platform.contracts.task_structure import TaskStructure
from veyra_agent_platform.local.builder.composite_composer import (
    specification_from_plan,
)
from veyra_agent_platform.local.builder.execution_planner import compile_execution_plan
from veyra_agent_platform.local.builder.finalization_composer import actor_finalization
from veyra_agent_platform.local.builder.generate_product import generate_builder_product
from veyra_agent_platform.local.resources import ResourceCatalog


def _task(check="constraint_match:collect_facts.review_report.key_value == 1"):
    return {
        "schema_version": "1.0",
        "goal": "Review supplied facts without inventing information",
        "summary": "One autonomous role reviews facts and corrects its report",
        "actors": [
            {
                "id": "reviewer",
                "role": "Reviewer",
                "capabilities": ["text_generation"],
                "inputs": [{"name": "materials", "type": "string"}],
                "outputs": [{"name": "review_report", "type": "object"}],
            }
        ],
        "stages": [
            {"id": "collect_facts", "actor": "reviewer", "summary": "Review facts"}
        ],
        "inputs": [{"name": "materials", "type": "string"}],
        "outputs": [{"name": "review_report", "type": "object"}],
        "execution_boundaries": [
            {
                "kind": "verification",
                "stage": "collect_facts",
                "required": True,
                "reason": "Check the reported value against supplied facts",
                "checks": [check],
            }
        ],
        "lifecycle": {"persistent": False, "interaction": "single_run"},
        "orchestration_complexity": "single",
        "uncertainty": [],
    }


class Planner:
    def __init__(self, task):
        self.task = task

    def complete_json(self, prompt, schema):
        return deepcopy(self.task)


@pytest.mark.parametrize("stage", ["collect_facts", "collect-facts"])
@pytest.mark.parametrize("port", ["review_report", "review-report"])
def test_owned_stage_port_compiles_to_delivery_output_without_changing_nested_keys(
    stage, port
):
    product = generate_builder_product(
        "Review the supplied facts",
        ResourceCatalog(),
        planner_provider=Planner(
            _task(f"constraint_match:{stage}.{port}.key_value == 1")
        ),
    )
    assert product.status == "review", product.diagnostics
    assert product.source.finalization.checks == (
        "constraint_match:review-report.key_value == 1",
    )


def test_explicit_export_alias_binds_the_declared_producer():
    task = _task()
    task["outputs"] = [
        {
            "name": "published_report",
            "type": "object",
            "source": "collect_facts.review_report",
        }
    ]
    product = generate_builder_product(
        "Review facts", ResourceCatalog(), planner_provider=Planner(task)
    )
    assert product.status == "review", product.diagnostics
    assert product.source.finalization.checks == (
        "constraint_match:published-report.key_value == 1",
    )


def test_unknown_nested_output_source_cannot_fall_back_to_a_matching_name():
    task = _task()
    task["outputs"][0]["source"] = "foreign.review_report.payload"
    product = generate_builder_product(
        "Review facts", ResourceCatalog(), planner_provider=Planner(task)
    )
    assert product.status == "blocked" and product.source is None


def test_explicit_producer_source_disambiguates_a_same_named_export():
    task = _task()
    task["outputs"] = [
        {
            "name": "collect_facts",
            "type": "object",
            "source": "collect_facts.review_report",
        }
    ]
    product = generate_builder_product(
        "Review facts", ResourceCatalog(), planner_provider=Planner(task)
    )
    assert product.status == "review", product.diagnostics
    assert product.source.finalization.checks == (
        "constraint_match:collect-facts.key_value == 1",
    )


def test_inferred_binding_does_not_guess_between_a_root_and_stage_reference():
    task = _task("constraint_match:review_report.review_report.key_value == 1")
    task["stages"][0]["id"] = "review_report"
    task["execution_boundaries"][0]["stage"] = "review_report"
    product = generate_builder_product(
        "Review facts", ResourceCatalog(), planner_provider=Planner(task)
    )
    assert product.status == "blocked" and product.source is None
    assert any(
        "ambiguous delivery condition" in message for message in product.diagnostics
    )


@pytest.mark.parametrize("field", ["collect_facts.review_report", "review_report"])
def test_required_field_uses_the_same_declared_binding(field):
    product = generate_builder_product(
        "Review facts",
        ResourceCatalog(),
        planner_provider=Planner(_task(f"required_fields:{field}")),
    )
    assert product.status == "review", product.diagnostics
    assert product.source.finalization.checks == ("required_fields:review-report",)


@pytest.mark.parametrize(
    "reference", ["foreign.review_report.key_value", "collect_facts.unknown.key_value"]
)
def test_unknown_stage_or_port_is_not_guessed(reference):
    product = generate_builder_product(
        "Review facts",
        ResourceCatalog(),
        planner_provider=Planner(_task(f"constraint_match:{reference} == 1")),
    )
    assert product.status == "blocked" and product.source is None


@pytest.mark.parametrize("colliding_export", [False, True])
def test_other_role_output_cannot_satisfy_owned_delivery_check(colliding_export):
    payload = _task("constraint_match:other_stage.review_report.key_value == 1")
    if colliding_export:
        payload["outputs"] = [
            {
                "name": "other_stage",
                "type": "object",
                "source": "collect_facts.review_report",
            }
        ]
    structure = TaskStructure.from_dict(payload)
    base = compile_execution_plan(structure)
    original_actor = structure.actors[0]
    other = replace(original_actor, id="other")
    task = replace(
        structure,
        actors=(original_actor, other),
        stages=(
            *structure.stages,
            replace(structure.stages[0], id="other_stage", actor="other"),
        ),
    )
    plan = replace(base, task=freeze_json(task.to_dict()))
    owner = replace(base.actors[0], id="reviewer")
    with pytest.raises(ValueError, match="undeclared delivery condition"):
        actor_finalization(plan, specification_from_plan(base), owner)


def test_ambiguous_unqualified_export_does_not_choose_an_intermediate_stage():
    task = _task()
    task["stages"].append(
        {"id": "later", "actor": "reviewer", "summary": "Revise facts"}
    )
    product = generate_builder_product(
        "Review facts", ResourceCatalog(), planner_provider=Planner(task)
    )
    assert product.status == "blocked" and product.source is None


def test_native_question_needs_no_invented_catalog_tool():
    task = _task("required_fields:review_report")
    task["execution_boundaries"].append(
        {
            "kind": "human_input",
            "stage": "collect_facts",
            "required": True,
            "question": "Which fact is current?",
            "reason": "Resolve missing user facts",
            "capability": "ask_user",
        }
    )
    task["lifecycle"]["interaction"] = "multi_turn"
    product = generate_builder_product(
        "Review facts", ResourceCatalog(), planner_provider=Planner(task)
    )
    assert product.status == "review", product.diagnostics
    assert not any(
        item.capability == "ask_user" for item in product.resolved.missing_required
    )
    assert not product.source.permissions.tools
    assert product.source.is_loop


@pytest.mark.parametrize("required", [False, True])
def test_optional_follow_up_is_not_a_mandatory_delivery_gate(required):
    task = _task("required_fields:review_report")
    question = "Which fact should be corrected?"
    task["execution_boundaries"].append(
        {
            "kind": "human_input",
            "stage": "collect_facts",
            "required": required,
            "question": question,
            "reason": "Support a user correction",
        }
    )
    task["lifecycle"]["interaction"] = "multi_turn"
    product = generate_builder_product(
        "Report unknown facts; support later corrections",
        ResourceCatalog(),
        planner_provider=Planner(task),
    )
    assert product.status == "review", product.diagnostics
    assert product.source.is_loop
    assert question in product.source.instructions
    assert (
        "Optional follow-up, not a delivery prerequisite: " + question
        in product.source.instructions
    ) is (not required)
    gates = [
        item
        for item in product.source.finalization.criteria
        if item.startswith("Resolve this interaction")
    ]
    assert len(gates) == int(required)
    assert not product.source.permissions.tools
