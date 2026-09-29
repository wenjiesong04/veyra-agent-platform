"""Decide product shape from TaskStructure. Occupations are not features."""

from __future__ import annotations

from veyra_agent_platform.contracts.execution_plan import ProductShapeDecision
from veyra_agent_platform.contracts.task_structure import TaskStructure

_STRUCTURAL = {
    "condition",
    "human_approval",
    "human_input",
    "state",
    "verification",
}


def decide_product_shape(structure: TaskStructure) -> ProductShapeDecision:
    """Shape is an analysis result. User wording is only a preference."""

    surface = structure.user_requested_surface
    kinds = {item.kind for item in structure.execution_boundaries}
    business_approval = any(
        item.kind == "human_approval" and item.approval_class != "tool"
        for item in structure.execution_boundaries
    )
    structural = bool(kinds & _STRUCTURAL) or business_approval
    reasoning = "reasoning" in kinds
    distinct_agents = _distinct_agent_roles(structure)
    warnings: list[str] = []

    if structure.user_shape_override == "PURE_AGENT":
        if structural:
            warnings.append(
                "User forced a single Agent. Business approval, persistent "
                "state, and deterministic branches will not be native nodes."
            )
        return ProductShapeDecision(
            shape="PURE_AGENT",
            status="decided",
            reason="User explicitly requested a simple Agent",
            warnings=tuple(warnings),
            user_requested_surface=surface,
            downgraded=bool(structural),
        )

    if not reasoning and not structural:
        return ProductShapeDecision(
            shape="PURE_AGENT",
            status="decided",
            reason="No structural boundaries; a reasoning loop is enough",
            user_requested_surface=surface,
        )

    if structural and not reasoning:
        return ProductShapeDecision(
            shape="WORKFLOW",
            status="decided",
            reason="Deterministic steps dominate; the model is not the decider",
            user_requested_surface=surface,
        )

    if structural and reasoning:
        if distinct_agents >= 4:
            return ProductShapeDecision(
                shape="MULTI_AGENT_WORKFLOW",
                status="decided",
                reason=(
                    "Independent capability roles plus structural boundaries "
                    "justify companion Agents inside a Workflow"
                ),
                user_requested_surface=surface,
            )
        return ProductShapeDecision(
            shape="AGENT_WORKFLOW",
            status="decided",
            reason=(
                "The task needs both model reasoning and native "
                "Condition / HumanApproval / State / Verifier structure"
            ),
            user_requested_surface=surface,
        )

    return ProductShapeDecision(
        shape="PURE_AGENT",
        status="decided",
        reason="Reasoning and tools fit a single Agent loop",
        user_requested_surface=surface,
    )


def _distinct_agent_roles(structure: TaskStructure) -> int:
    roles = {
        item.id
        for item in structure.actors
        if item.id not in {"main", "editor"}
        and set(item.capabilities) - {"text_generation", "structured_output"}
    }
    return len(roles)
