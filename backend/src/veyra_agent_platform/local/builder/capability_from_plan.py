"""Derive CapabilityRequirements from ExecutionPlan. Never emit resource IDs."""

from __future__ import annotations

from veyra_agent_platform.contracts.capability import CapabilityRequirement
from veyra_agent_platform.contracts.execution_plan import ExecutionPlan
from veyra_agent_platform.local.builder.capability_requirements import (
    requirement_for,
)

_MODEL_ONLY = {
    "vision",
    "text_generation",
    "structured_output",
    "tool_calling",
    "human_approval",
}


def derive_plan_capabilities(plan: ExecutionPlan) -> tuple[CapabilityRequirement, ...]:
    names = list(plan.capabilities)
    if plan.state is not None:
        names.extend(("entity_query", "entity_read", "entity_write"))
        if plan.state.revision:
            names.append("entity_history")
    for actor in plan.actors:
        names.extend(actor.capabilities)
    unique = list(
        dict.fromkeys(name for name in names if name and name not in _MODEL_ONLY)
    )
    # image_generation stays required so missing is honest.
    return tuple(requirement_for(name) for name in unique)


def merge_spec_and_plan_requirements(
    plan: ExecutionPlan,
    specification_text: str = "",
) -> tuple[CapabilityRequirement, ...]:
    del specification_text
    return derive_plan_capabilities(plan)


def loop_requirements_from_plan(
    plan: ExecutionPlan,
) -> tuple[CapabilityRequirement, ...]:
    """PURE_AGENT path: plan capabilities only, no occupation heuristics."""

    return derive_plan_capabilities(plan)
