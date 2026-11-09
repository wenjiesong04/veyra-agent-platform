"""Resolve exact task methods per actor without sharing child permissions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from veyra_agent_platform.contracts.execution_plan import ExecutionPlan
from veyra_agent_platform.contracts.resource_plan import ResourcePlan
from veyra_agent_platform.contracts.task_structure import TaskStructure
from veyra_agent_platform.local.resources.resolver import ResourceResolver

from .capability_from_plan import derive_plan_capabilities
from .composite_composer import specification_from_plan


def resolve_plan_resources(
    plan: ExecutionPlan,
    structure: TaskStructure,
    resolver: ResourceResolver,
    *,
    requirement: str,
    project_resources: Any = (),
    knowledge_inventory: Any = (),
    catalog_snapshot: Any = None,
) -> tuple[ResourcePlan, Mapping[str, ResourcePlan] | None]:
    requirements = tuple(
        item for item in derive_plan_capabilities(plan) if item.model_capability is None
    )
    options = dict(
        project_resources=project_resources,
        knowledge_inventory=knowledge_inventory,
        catalog_resources=catalog_snapshot,
        requirement_text=requirement,
    )
    spec = specification_from_plan(plan, requirement=requirement)
    if not structure.skill_choices or plan.product_shape == "PURE_AGENT":
        requested: dict[str, list[str]] = {}
        for choice in structure.skill_choices:
            requested.setdefault(choice.capability, []).append(choice.reference)
        return resolver.resolve(
            spec, requirements, requested_skills=requested, **options
        ), None

    actor_plans: dict[str, ResourcePlan] = {}
    for actor in plan.actors:
        requested = {}
        for choice in structure.skill_choices:
            if choice.actor == actor.id:
                requested.setdefault(choice.capability, []).append(choice.reference)
        actor_plans[actor.id] = resolver.resolve(
            specification_from_plan(plan, actor=actor, requirement=requirement),
            tuple(
                item for item in requirements if item.capability in actor.capabilities
            ),
            requested_skills=requested,
            **options,
        )
    actor_caps = {cap for actor in plan.actors for cap in actor.capabilities}
    graph_plan = resolver.resolve(
        spec,
        tuple(item for item in requirements if item.capability not in actor_caps),
        **options,
    )
    plans = [graph_plan, *actor_plans.values()]
    # A Project has one pin for a resource ID. Conflicting child versions need
    # review rather than a last-writer-wins union.
    refs: dict[str, str] = {}
    for scoped in plans:
        for item in (*scoped.selected, *scoped.needs_configuration):
            if item.resource_id in refs and refs[item.resource_id] != item.reference:
                raise ValueError(
                    "Selected actor methods require conflicting Project versions"
                )
            refs[item.resource_id] = item.reference
    fields = (
        "selected",
        "already_bound",
        "will_bind",
        "needs_configuration",
        "missing_required",
        "optional_unresolved",
        "diagnostics",
        "requirements",
        "rejected_references",
    )
    merged: dict[str, Any] = {}
    for field in fields:
        values: list[Any] = []
        for scoped in plans:
            for item in getattr(scoped, field):
                if item not in values:
                    values.append(item)
        merged[field] = tuple(values)
    merged["knowledge"] = next(
        (
            scoped.knowledge
            for scoped in plans
            if scoped.knowledge.status == "available"
        ),
        next(
            (
                scoped.knowledge
                for scoped in plans
                if scoped.knowledge.status != "not_requested"
            ),
            graph_plan.knowledge,
        ),
    )
    return replace(graph_plan, **merged), actor_plans
