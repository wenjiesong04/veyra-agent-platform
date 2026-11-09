"""Typed planned predicates execute against actual compiled producer values."""

from dataclasses import replace
from typing import Any

import pytest

from tests.unit.local.test_gated_role_composition import _task
from veyra_agent_platform.contracts.task_structure import ExecutionBoundary, TaskStage
from veyra_agent_platform.local.builder.generate_product import generate_builder_product
from veyra_agent_platform.local.builder.task_structure_schema import (
    task_structure_projection,
)
from veyra_agent_platform.local.builder.workflow_bindings import bind_condition
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.service import _condition


class TypedPredicatePlanner:
    def __init__(self, path: str) -> None:
        task = _task()
        task = replace(
            task,
            stages=(
                task.stages[0],
                TaskStage(id="gate", summary="Continue only for ready results"),
                *task.stages[1:],
            ),
            execution_boundaries=(
                *task.execution_boundaries,
                ExecutionBoundary(
                    kind="condition",
                    stage="gate",
                    reason="Only a ready producer may continue",
                    required=True,
                    expression='review.outcome.status == "ready"',
                    branches=("ready", "stop"),
                ),
            ),
        )
        self.payload = task_structure_projection(task)
        self.payload["execution_boundaries"][-1]["expression"] = {
            "path": path,
            "operator": "==",
            "literal": "ready",
        }

    def complete_json(self, prompt: str, schema: Any) -> dict[str, Any]:
        del prompt, schema
        return self.payload


def test_typed_predicate_compiles_and_runs_against_the_producer_output() -> None:
    product = generate_builder_product(
        _task().goal,
        ResourceCatalog(),
        planner_provider=TypedPredicatePlanner("review.outcome.status"),
    )
    assert product.status == "review", product.diagnostics
    assert product.orchestration is not None
    node = next(
        node
        for node in product.orchestration.workflow["nodes"]
        if node["component_type"] == "Condition"
    )
    assert node["expression"] == 'review_outcome.status == "ready"'
    assert _condition(node["expression"], {"review_outcome": {"status": "ready"}})
    assert not _condition(
        node["expression"], {"review_outcome": {"status": "needs_input"}}
    )


def test_future_predicate_subject_cannot_be_published_as_a_candidate() -> None:
    product = generate_builder_product(
        _task().goal,
        ResourceCatalog(),
        planner_provider=TypedPredicatePlanner("write.saved_report.status"),
    )
    assert product.status == "blocked"
    assert product.source is None and product.orchestration is None
    assert any(
        "unavailable condition subject" in issue for issue in product.diagnostics
    )


def test_input_aliases_and_human_replies_share_the_binding_contract() -> None:
    expression = bind_condition(
        'inputs.material_path == "orders.csv"',
        {},
        {},
        {"material-path": "materialpath"},
    )
    assert _condition(expression, {"materialpath": "orders.csv"})
    expression = bind_condition(
        "choose.confirmed == true", {"choose.confirmed": "chooseconfirmed"}, {}, {}
    )
    assert _condition(expression, {"chooseconfirmed": True})
    assert not _condition(expression, {"chooseconfirmed": False})
    with pytest.raises(ValueError, match="unavailable condition subject"):
        bind_condition("input.missing == true", {}, {}, {"input": "unrelated"})
