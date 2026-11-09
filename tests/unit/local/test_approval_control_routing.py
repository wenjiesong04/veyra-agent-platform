"""Approval decisions are control ports; rejected delivery is a Stop terminal."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from veyra_agent_platform.contracts.task_structure import TaskStructure
from veyra_agent_platform.local.builder.execution_planner import compile_execution_plan
from veyra_agent_platform.local.builder.generate_product import generate_builder_product
from veyra_agent_platform.local.builder.task_planner import normalize_task_structure
from veyra_agent_platform.local.builder.task_structure_schema import (
    task_structure_payload,
)
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.service import _interpolate


def approval_task(path="confirm.approved", operator="==", literal=True):
    def port(name, kind="string", source=""):
        return {"name": name, "type": kind, "required": True, "source": source}

    return {
        "schema_version": "1.0",
        "goal": "Analyze and independently review material, then approve delivery",
        "summary": "Two roles, source references, and explicit human confirmation",
        "actors": [
            {
                "id": "analyst",
                "role": "analyst",
                "reason": "Extract facts and contradictions",
                "capabilities": ["text_generation"],
                "inputs": [port("raw")],
                "outputs": [port("analysis")],
            },
            {
                "id": "reviewer",
                "role": "reviewer",
                "reason": "Compare analysis with original text",
                "capabilities": ["text_generation"],
                "inputs": [port("raw"), port("analysis")],
                "outputs": [
                    port("report"),
                    port("issues", "array"),
                    port("ready", "boolean"),
                ],
            },
        ],
        "stages": [
            {
                "id": "analyze",
                "actor": "analyst",
                "summary": "Analyze source",
                "input_sources": {"raw": "input.raw"},
            },
            {
                "id": "review",
                "actor": "reviewer",
                "summary": "Review against source",
                "input_sources": {"raw": "input.raw", "analysis": "analyze.analysis"},
            },
            {
                "id": "confirm",
                "summary": "Approve or stop",
                "input_sources": {"report": "review.report", "issues": "review.issues"},
            },
        ],
        "inputs": [port("raw")],
        "outputs": [port("report", source="review.report")],
        "execution_boundaries": [
            {
                "kind": "human_approval",
                "stage": "confirm",
                "approval_class": "business",
                "reason": "Delivery requires a decision",
                "question": "Approve this reviewed report?",
                "required": True,
                "expected_schema": {"approved": "boolean"},
            },
            {
                "kind": "condition",
                "stage": "confirm",
                "reason": "Approval delivers, rejection stops",
                "required": True,
                "expression": {"path": path, "operator": operator, "literal": literal},
                "branches": ["approved delivery", "rejected stop"],
            },
        ],
        "lifecycle": {"persistent": False, "interaction": "multi_turn"},
        "orchestration_complexity": "multi_actor",
        "constraints": ["Never deliver before approval"],
        "success_criteria": ["Reviewer receives both original material and analysis"],
        "uncertainty": [],
    }


class Planner:
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, prompt: str, schema: Any):
        return deepcopy(self.payload)


@pytest.mark.parametrize("path", ["confirm.approved", "confirm.rejected"])
@pytest.mark.parametrize("operator", ["==", "!="])
@pytest.mark.parametrize("literal", [True, False])
def test_approval_outcomes_compile_to_ports_not_data_conditions(
    path, operator, literal
):
    task = approval_task(path, operator, literal)
    product = generate_builder_product(
        task["goal"], ResourceCatalog(), planner_provider=Planner(task)
    )
    assert product.status == "review", product.diagnostics
    assert product.orchestration is not None
    source = product.orchestration.workflow
    assert len(product.orchestration.companions) == 2
    assert not any(node["component_type"] == "Condition" for node in source["nodes"])
    approval = next(
        node for node in source["nodes"] if node["component_type"] == "HumanApproval"
    )
    stop = next(node for node in source["nodes"] if node["component_type"] == "Stop")
    assert {"from": approval["id"], "port": "rejected", "to": stop["id"]} in source[
        "transitions"
    ]
    assert not any(edge["from"] == stop["id"] for edge in source["transitions"])
    review = next(node for node in source["nodes"] if node["id"] == "review")
    analyze = next(node for node in source["nodes"] if node["id"] == "analyze")
    assert review["input_mapping"]["raw"] == analyze["input_mapping"]["raw"]
    assert review["input_mapping"]["analysis"] == analyze["output_mapping"]["analysis"]
    prompt = _interpolate(
        approval["prompt"],
        {
            review["output_mapping"]["report"]: "Actual reviewed report",
            review["output_mapping"]["issues"]: ["Conflicting dates"],
        },
    )
    assert "Approve this reviewed report?" in prompt
    assert "Actual reviewed report" in prompt and "Conflicting dates" in prompt


def test_real_data_condition_is_not_folded_into_approval():
    task = approval_task("review.ready")
    product = generate_builder_product(
        task["goal"], ResourceCatalog(), planner_provider=Planner(task)
    )
    assert product.status == "review", product.diagnostics
    assert any(
        node["component_type"] == "Condition"
        for node in product.orchestration.workflow["nodes"]
    )


@pytest.mark.parametrize("path", ["future.approved", "confirm.unknown"])
def test_unknown_or_future_condition_subject_is_still_rejected(path):
    task = approval_task(path)
    product = generate_builder_product(
        task["goal"], ResourceCatalog(), planner_provider=Planner(task)
    )
    assert product.status == "blocked"
    assert any(
        "unavailable condition subject" in value for value in product.diagnostics
    )


@pytest.mark.parametrize("operator,literal", [("==", False), ("!=", True)])
def test_inverse_predicate_preserves_explicit_rejection_route(operator, literal):
    task = approval_task(operator=operator, literal=literal)
    task["stages"].append(
        {"id": "revise", "actor": "reviewer", "summary": "Explicit rejection action"}
    )
    task["execution_boundaries"][-1]["branches"] = ["revise", "output"]
    structure = normalize_task_structure(
        TaskStructure.from_dict(task_structure_payload(task))
    )
    plan = compile_execution_plan(structure)
    approval = next(step for step in plan.steps if step.kind == "human_approval")
    assert approval.on_approved == "output"
    assert approval.on_rejected == "revise"
    assert not any(step.kind == "stop" for step in plan.steps)


@pytest.mark.parametrize("branches", [["deliver", "revise"], ["revise", "deliver"]])
def test_ambiguous_approval_branches_cannot_execute_each_others_actions(branches):
    task = approval_task()
    task["stages"].extend(
        [
            {"id": "deliver", "actor": "reviewer", "summary": "Approved delivery"},
            {"id": "revise", "actor": "reviewer", "summary": "Rejected revision"},
        ]
    )
    task["execution_boundaries"][-1]["branches"] = branches
    product = generate_builder_product(
        task["goal"], ResourceCatalog(), planner_provider=Planner(task)
    )
    assert product.status == "blocked"
    assert product.orchestration is None
    assert "approval_branch_join_ambiguous" in " ".join(product.diagnostics)
