"""Decide product shape from TaskStructure. Occupations are not features."""

from __future__ import annotations

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.execution_plan import ProductShapeDecision
from veyra_agent_platform.contracts.task_structure import (
    ExecutionBoundary,
    TaskActor,
    TaskStructure,
)


def stage_key(stage_id: str) -> str:
    """Match the case/underscore aliases accepted by task reference binding."""
    return stage_id.casefold().replace("_", "-")


def native_loop_state(structure: TaskStructure, stage_id: str) -> bool:
    """State owned by the same autonomous role uses the existing entity tools."""
    if structure.state is None or len(structure.actors) != 1:
        return False
    actor_id = structure.actors[0].id
    return any(
        stage_key(stage.id) == stage_key(stage_id) and stage.actor == actor_id
        for stage in structure.stages
    )


def native_loop_input(structure: TaskStructure, stage_id: str) -> bool:
    """A question attached to an actor belongs to its autonomous invocation."""
    return any(
        stage_key(stage.id) == stage_key(stage_id) and bool(stage.actor)
        for stage in structure.stages
    )


def effective_actor_capabilities(
    structure: TaskStructure, actor: TaskActor
) -> tuple[str, ...]:
    caps = list(actor.capabilities)
    if structure.state is not None and any(
        boundary.kind == "state"
        and boundary.entity == structure.state.entity
        and native_loop_state(structure, boundary.stage)
        and any(
            stage_key(stage.id) == stage_key(boundary.stage) and stage.actor == actor.id
            for stage in structure.stages
        )
        for boundary in structure.execution_boundaries
    ):
        caps.extend(("entity_query", "entity_read", "entity_write"))
        if structure.state.revision:
            caps.append("entity_history")
    return tuple(dict.fromkeys(caps))


def native_loop_verification(structure: TaskStructure, stage_id: str) -> bool:
    """An actor-owned delivery check uses its same-run finalization gate."""
    return native_loop_input(structure, stage_id)


def validate_business_gate_ownership(structure: TaskStructure) -> None:
    """Check the same derived capabilities used by companion composition."""
    caps = {
        actor.id: effective_actor_capabilities(structure, actor)
        for actor in structure.actors
    }
    for boundary in structure.execution_boundaries:
        if boundary.kind != "human_approval" or boundary.approval_class == "tool":
            continue
        gate = next(
            (
                i
                for i, stage in enumerate(structure.stages)
                if stage_key(stage.id) == stage_key(boundary.stage)
            ),
            None,
        )
        if gate is None:
            continue
        if structure.stages[gate].actor:
            raise ContractValidationError(
                "business_gate_needs_independent_stage: "
                + boundary.stage
                + "; separate a readonly producer, the user gate, and the effect stage"
            )
        if boundary.capability and any(
            boundary.capability in caps.get(stage.actor, ())
            for stage in structure.stages[:gate]
        ):
            raise ContractValidationError(
                "gated_capability_reachable_before_approval: "
                + boundary.capability
                + "; remove it from pre-gate actors and bind its effect after approval"
            )


def decide_product_shape(structure: TaskStructure) -> ProductShapeDecision:
    """Shape is an analysis result. User wording is only a preference."""

    surface = structure.user_requested_surface
    kinds = {item.kind for item in structure.execution_boundaries}
    workflow_boundaries = [
        item
        for item in structure.execution_boundaries
        if _needs_workflow_boundary(structure, item)
    ]
    reasoning = "reasoning" in kinds or any(stage.actor for stage in structure.stages)
    distinct_agents = _distinct_agent_roles(structure)
    structural = bool(workflow_boundaries) or distinct_agents > 1
    warnings: list[str] = []
    required_structure = any(item.required for item in workflow_boundaries)

    if structure.user_shape_override == "PURE_AGENT":
        if not required_structure:
            return ProductShapeDecision(
                shape="PURE_AGENT",
                status="decided",
                reason="User requested one Agent; no required external boundaries",
                warnings=("Independent roles are combined in one Agent.",)
                if distinct_agents > 1
                else (),
                user_requested_surface=surface,
                downgraded=bool(structural),
            )
        warnings.append(
            "The single-Agent preference cannot remove required execution "
            "boundaries; the smallest compatible Workflow preserves them."
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
            warnings=tuple(warnings),
            user_requested_surface=surface,
        )

    if structural and reasoning:
        if distinct_agents > 1:
            return ProductShapeDecision(
                shape="MULTI_AGENT_WORKFLOW",
                status="decided",
                reason=(
                    "Independent capability roles plus structural boundaries "
                    "justify companion Agents inside a Workflow"
                ),
                warnings=tuple(warnings),
                user_requested_surface=surface,
            )
        return ProductShapeDecision(
            shape="AGENT_WORKFLOW",
            status="decided",
            reason=(
                "The task needs both model reasoning and native "
                "Condition / HumanApproval / State / Verifier structure"
            ),
            warnings=tuple(warnings),
            user_requested_surface=surface,
        )

    return ProductShapeDecision(
        shape="PURE_AGENT",
        status="decided",
        reason="Reasoning and tools fit a single Agent loop",
        user_requested_surface=surface,
    )


def _distinct_agent_roles(structure: TaskStructure) -> int:
    roles = {stage.actor for stage in structure.stages if stage.actor}
    if not roles and structure.orchestration_complexity == "multi_actor":
        roles = {item.id for item in structure.actors}
    return len(roles)


def _needs_workflow_boundary(
    structure: TaskStructure, boundary: ExecutionBoundary
) -> bool:
    if boundary.kind == "human_approval":
        return boundary.approval_class != "tool"
    if boundary.kind == "human_input":
        return len(structure.actors) > 1 and not native_loop_input(
            structure, boundary.stage
        )
    if boundary.kind == "state":
        return not (
            structure.state is not None
            and native_loop_state(structure, boundary.stage)
            and boundary.entity == structure.state.entity
        )
    if boundary.kind == "verification":
        return not native_loop_verification(structure, boundary.stage)
    return boundary.kind == "condition"
