"""Native loop duties and actual typed handoffs determine product shape."""

from dataclasses import replace

import pytest

from tests.unit.local.test_gated_role_composition import _Planner, _task
from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.task_structure import (
    ExecutionBoundary,
    StateRequirement,
    TaskActor,
    TaskIOField,
    TaskLifecycle,
    TaskStage,
    TaskStructure,
)
from veyra_agent_platform.local.builder.agent_state import source_state_schema
from veyra_agent_platform.local.builder.execution_planner import compile_execution_plan
from veyra_agent_platform.local.builder.generate_product import generate_builder_product
from veyra_agent_platform.local.builder.product_shape import decide_product_shape
from veyra_agent_platform.local.builder.task_planner import validate_task_structure
from veyra_agent_platform.local.resources import ResourceCatalog


def _stateful_agent() -> TaskStructure:
    return TaskStructure(
        schema_version="1.0",
        goal="Manage user-selected records and retain their status across runs",
        summary="One autonomous role chooses its entity operations",
        actors=(
            TaskActor(id="main", role="assistant", capabilities=("text_generation",)),
        ),
        stages=(
            TaskStage(id="manage", summary="Inspect and update records", actor="main"),
        ),
        entities=("CaseRecord",),
        inputs=(TaskIOField(name="request", type="string"),),
        outputs=(TaskIOField(name="result", type="string"),),
        execution_boundaries=(
            ExecutionBoundary(
                kind="state", stage="manage", entity="CaseRecord", reason="Keep records"
            ),
            ExecutionBoundary(
                kind="human_input",
                stage="manage",
                reason="Clarify missing facts",
                question="Which record should I update?",
            ),
        ),
        lifecycle=TaskLifecycle(persistent=True, interaction="persistent_task"),
        orchestration_complexity="single",
        uncertainty=(),
        state=StateRequirement(
            entity="CaseRecord",
            identity="entity_id",
            scope="entity",
            fields={"status": "string"},
            statuses=("open", "done"),
        ),
    )


def test_state_and_questions_owned_by_one_role_compose_a_real_loop() -> None:
    structure = _stateful_agent()
    product = generate_builder_product(
        structure.goal, ResourceCatalog(), planner_provider=_Planner(structure)
    )
    assert product.status == "review", product.diagnostics
    assert product.source is not None and product.source.is_loop
    assert product.orchestration is None
    assert source_state_schema(product.source) == structure.state.to_dict()
    assert "Which record should I update?" in product.source.instructions
    tools = set(product.source.permissions.tools)
    assert {
        "veyra.tool.entity.query",
        "veyra.tool.entity.read",
        "veyra.tool.entity.write",
    } <= tools
    assert "veyra.tool.entity.history" in tools
    assert all(
        binding["reference"] in product.source.lock
        for binding in product.source.ui["bindings"].values()
    )


@pytest.mark.parametrize("kind", ["verification", "human_approval"])
def test_external_checks_and_business_approval_remain_workflow_gates(kind: str) -> None:
    structure = _stateful_agent()
    boundary = ExecutionBoundary(
        kind=kind,
        stage="gate",
        reason="A required independent gate",
        checks=("output.not_empty",) if kind == "verification" else (),
        approval_class="business" if kind == "human_approval" else None,
    )
    structure = replace(
        structure, execution_boundaries=(*structure.execution_boundaries, boundary)
    )
    assert decide_product_shape(structure).shape == "AGENT_WORKFLOW"


def test_state_with_its_own_stage_remains_a_deterministic_workflow_step() -> None:
    structure = _stateful_agent()
    structure = replace(
        structure,
        stages=(
            *structure.stages,
            TaskStage(id="save", summary="Persist the approved value"),
        ),
        execution_boundaries=(
            replace(structure.execution_boundaries[0], stage="save"),
        ),
    )
    assert decide_product_shape(structure).shape == "AGENT_WORKFLOW"


def test_two_text_only_roles_with_declared_handoff_do_not_collapse() -> None:
    original = _task()
    reader, writer = original.actors
    structure = replace(
        original,
        actors=(
            replace(reader, id="main", capabilities=("text_generation",)),
            replace(writer, id="editor", capabilities=("text_generation",)),
        ),
        stages=(
            replace(original.stages[0], actor="main"),
            replace(original.stages[-1], actor="editor"),
        ),
        execution_boundaries=(),
        constraints=(),
        success_criteria=(),
        filesystem_write_roots=(),
        lifecycle=TaskLifecycle(persistent=False, interaction="single_run"),
    )
    product = generate_builder_product(
        structure.goal, ResourceCatalog(), planner_provider=_Planner(structure)
    )
    assert product.status == "review", product.diagnostics
    assert product.plan.product_shape == "MULTI_AGENT_WORKFLOW"
    assert {actor.id for actor in product.plan.actors} == {"main", "editor"}
    assert len(product.orchestration.companions) == 2
    calls = {
        node["id"]: node
        for node in product.orchestration.workflow["nodes"]
        if node["component_type"] == "AgentCall"
    }
    assert (
        calls["write"]["input_mapping"]["report-text"]
        == calls["review"]["output_mapping"]["report-text"]
    )


def test_single_loop_may_use_prior_notes_but_cannot_read_future_stages() -> None:
    structure = _stateful_agent()
    structure = replace(
        structure,
        state=None,
        execution_boundaries=(),
        lifecycle=TaskLifecycle(persistent=False, interaction="single_run"),
        actors=(
            replace(
                structure.actors[0],
                inputs=(TaskIOField(name="context", type="object"),),
            ),
        ),
        stages=(
            TaskStage(id="inspect", summary="Inspect", actor="main"),
            TaskStage(
                id="summarize",
                summary="Summarize",
                actor="main",
                input_sources={"context": "inspect.note"},
            ),
        ),
    )
    validate_task_structure(structure)
    assert compile_execution_plan(structure).product_shape == "PURE_AGENT"
    future = replace(
        structure,
        stages=(
            replace(structure.stages[0], input_sources={"context": "summarize.note"}),
            structure.stages[1],
        ),
    )
    with pytest.raises(ContractValidationError, match="unavailable stage"):
        validate_task_structure(future)


def test_actor_question_does_not_become_post_call_input_or_another_roles_duty() -> None:
    original = _task()
    question = ExecutionBoundary(
        kind="human_input",
        stage="review",
        reason="Clarify only when needed",
        question="Which source column should I use?",
    )
    structure = replace(
        original, execution_boundaries=(*original.execution_boundaries, question)
    )
    product = generate_builder_product(
        structure.goal, ResourceCatalog(), planner_provider=_Planner(structure)
    )
    assert product.status == "review", product.diagnostics
    assert not any(step.kind == "human_input" for step in product.plan.steps)
    reader, writer = product.orchestration.companions
    assert question.question in reader.instructions
    assert question.question not in writer.instructions


@pytest.mark.parametrize("actor_stage", ["manage", "manage_records"])
def test_external_verifier_does_not_duplicate_native_state(actor_stage: str) -> None:
    structure = _stateful_agent()
    structure = replace(
        structure,
        stages=(
            replace(structure.stages[0], id=actor_stage),
            TaskStage(id="check", summary="Check output"),
        ),
        execution_boundaries=(
            *(
                replace(boundary, stage=actor_stage)
                for boundary in structure.execution_boundaries
            ),
            ExecutionBoundary(
                kind="verification",
                stage="check",
                reason="Independent check",
                checks=("output.not_empty",),
            ),
        ),
    )
    product = generate_builder_product(
        structure.goal, ResourceCatalog(), planner_provider=_Planner(structure)
    )
    assert product.status == "review", product.diagnostics
    assert product.source is None and product.plan.product_shape == "AGENT_WORKFLOW"
    assert not any(
        step.kind in {"state_write", "human_input"} for step in product.plan.steps
    )
    agent = product.orchestration.companions[0]
    assert source_state_schema(agent) == structure.state.to_dict()
    assert "veyra.tool.entity.query" in agent.permissions.tools
    assert "veyra.tool.entity.write" in agent.permissions.tools
    assert "Which record should I update?" in agent.instructions


def test_business_gate_cannot_be_appended_to_a_complete_actor_call() -> None:
    structure = _stateful_agent()
    structure = replace(
        structure,
        execution_boundaries=(
            *structure.execution_boundaries,
            ExecutionBoundary(
                kind="human_approval",
                stage="manage",
                reason="Approve before effects",
                approval_class="business",
                capability="entity_write",
            ),
        ),
    )
    with pytest.raises(ValueError, match="business_gate_needs_independent_stage"):
        compile_execution_plan(structure)
    with pytest.raises(ValueError, match="business_gate_needs_independent_stage"):
        validate_task_structure(structure)


def test_explicitly_gated_capability_cannot_be_owned_by_pre_gate_actor() -> None:
    original = _task()
    structure = replace(
        original,
        actors=(
            replace(
                original.actors[0],
                capabilities=(*original.actors[0].capabilities, "workspace_write"),
            ),
            original.actors[1],
        ),
        execution_boundaries=tuple(
            replace(boundary, capability="workspace_write")
            if boundary.kind == "human_approval"
            and boundary.approval_class == "business"
            else boundary
            for boundary in original.execution_boundaries
        ),
    )
    with pytest.raises(ValueError, match="gated_capability_reachable_before_approval"):
        validate_task_structure(structure)


def test_derived_state_write_cannot_bypass_business_gate() -> None:
    structure = _stateful_agent()
    structure = replace(
        structure,
        stages=(
            *structure.stages,
            TaskStage(id="approve", summary="Approve the update"),
        ),
        execution_boundaries=(
            *structure.execution_boundaries,
            ExecutionBoundary(
                kind="human_approval",
                stage="approve",
                reason="Approve before any update",
                approval_class="business",
                capability="entity_write",
            ),
        ),
    )
    assert structure.actors[0].capabilities == ("text_generation",)
    for check in (validate_task_structure, compile_execution_plan):
        with pytest.raises(
            ValueError, match="gated_capability_reachable_before_approval"
        ):
            check(structure)
    product = generate_builder_product(
        structure.goal, ResourceCatalog(), planner_provider=_Planner(structure)
    )
    assert product.status == "blocked" and product.source is None
    assert product.orchestration is None
