"""Fidelity and executable-contract checks for Builder products before review."""

from __future__ import annotations

from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.execution_plan import ExecutionPlan
from veyra_agent_platform.contracts.task_structure import TaskStructure
from veyra_agent_platform.contracts.workflow import WorkflowSource

from .agent_state import source_state_schema
from .workflow_orchestration import WorkflowOrchestration


def validate_product_fidelity(
    requirement: str,
    structure: TaskStructure,
    plan: ExecutionPlan,
    source: AgentSource | None,
    orchestration: WorkflowOrchestration | None,
) -> tuple[str, ...]:
    """Do not turn a valid JSON plan into an unsupported product promise."""
    issues: list[str] = []
    if structure.uncertainty:
        issues.append("task_requires_clarification")
        issues.extend(
            "Resolve this uncertainty as runtime inputs/questions if supported; "
            "retain genuinely unsupported duties: " + item
            for item in structure.uncertainty
        )
    if (
        structure.lifecycle.interaction != "single_run"
        and not any(
            step.kind in {"human_input", "human_approval"} for step in plan.steps
        )
        and not (source is not None and source.is_loop)
    ):
        issues.append("human_interaction_not_represented")
    if structure.lifecycle.persistent and structure.state is None:
        issues.append("persistent_state_not_represented")
    if plan.state is not None and source is not None:
        try:
            if source_state_schema(source) != plan.state.to_dict():
                issues.append("persistent_state_contract_not_compiled")
        except (ValueError, TypeError):
            issues.append("persistent_state_contract_not_compiled")
    agents = (
        (source,)
        if source is not None
        else (orchestration.companions if orchestration is not None else ())
    )
    for agent in agents:
        if not agent.is_loop:
            issues.append("generated_agent_must_use_loop")
        if requirement.strip() not in agent.instructions:
            issues.append("complete_requirement_not_in_instructions")
        for criterion in (*structure.constraints, *structure.success_criteria):
            if criterion not in agent.instructions:
                issues.append("task_constraint_not_in_instructions")
    boundary_steps = {
        "human_input": "human_input",
        "human_approval": "human_approval",
        "state": "state_write",
        "verification": "verifier",
        "condition": "condition",
    }
    for boundary in structure.execution_boundaries:
        if not boundary.required or boundary.approval_class == "tool":
            continue
        expected = boundary_steps.get(boundary.kind)
        if boundary.kind == "human_input" and source is not None and source.is_loop:
            continue
        if expected and not any(step.kind == expected for step in plan.steps):
            issues.append(f"required_boundary_not_represented:{boundary.stage}")
    if orchestration is not None:
        payload: dict[str, Any] = dict(orchestration.workflow)
        payload.pop("companion_agent_ids", None)
        try:
            WorkflowSource.from_dict(payload)
        except (ValueError, TypeError) as exc:
            issues.append(f"workflow_contract_invalid:{exc}")
    return tuple(dict.fromkeys(issues))
