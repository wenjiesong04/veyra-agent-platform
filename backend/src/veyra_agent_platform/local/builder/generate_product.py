"""Factory generation V2: TaskStructure → shape → plan → resolve → compose."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.agent_spec import AgentSpecification
from veyra_agent_platform.contracts.execution_plan import ExecutionPlan
from veyra_agent_platform.contracts.resource_plan import ResourcePlan
from veyra_agent_platform.contracts.task_structure import TaskStructure
from veyra_agent_platform.local.builder.capability_from_plan import (
    derive_plan_capabilities,
)
from veyra_agent_platform.local.builder.composite_composer import (
    compose_execution_product,
    specification_from_plan,
)
from veyra_agent_platform.local.builder.execution_planner import compile_execution_plan
from veyra_agent_platform.local.builder.model_requirements import (
    derive_model_requirements,
)
from veyra_agent_platform.local.builder.product_shape import decide_product_shape
from veyra_agent_platform.local.builder.product_validation import (
    validate_product_fidelity,
)
from veyra_agent_platform.local.builder.task_planner import (
    PlannerProvider,
    normalize_task_structure,
    plan_task_structure,
    validate_task_structure,
)
from veyra_agent_platform.local.builder.task_structure_schema import (
    task_structure_payload,
)
from veyra_agent_platform.local.builder.workflow_orchestration import (
    WorkflowOrchestration,
)
from veyra_agent_platform.local.models.contracts import (
    ModelCapabilityRequirement,
    ModelProfile,
    ModelResolution,
    ModelRoleDefault,
)
from veyra_agent_platform.local.models.resolver import ModelResolver
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.resources.resolver import ResourceResolver


@dataclass(frozen=True)
class GenerationProduct:
    status: str
    structure: TaskStructure | None
    plan: ExecutionPlan | None
    specification: AgentSpecification | None
    source: AgentSource | None
    orchestration: WorkflowOrchestration | None
    resolved: ResourcePlan | None
    diagnostics: tuple[str, ...]
    blocked_reason: str = ""
    model_requirements: tuple[ModelCapabilityRequirement, ...] = ()
    model_resolutions: tuple[ModelResolution, ...] = ()


def generate_builder_product(
    requirement: str,
    catalog: ResourceCatalog,
    *,
    project_resources: list[dict[str, Any]] | None = None,
    knowledge_inventory: list[dict[str, Any]] | None = None,
    secret_configured: Any = None,
    model_profiles: Sequence[ModelProfile] = (),
    model_bindings: Mapping[str, Mapping[str, str]] | None = None,
    model_defaults: Sequence[ModelRoleDefault] = (),
    planner_provider: PlannerProvider | None = None,
    planner_repair: Any = None,
    planner_review: Any = None,
) -> GenerationProduct:
    planned = plan_task_structure(
        requirement, provider=planner_provider, repair=planner_repair
    )
    if planned.structure is None:
        return GenerationProduct(
            status="blocked",
            structure=None,
            plan=None,
            specification=None,
            source=None,
            orchestration=None,
            resolved=None,
            diagnostics=planned.diagnostics or ("planner_invalid",),
            blocked_reason="planner_invalid",
        )
    structure = planned.structure
    options = dict(
        project_resources=project_resources,
        knowledge_inventory=knowledge_inventory,
        secret_configured=secret_configured,
        model_profiles=model_profiles,
        model_bindings=model_bindings,
        model_defaults=model_defaults,
    )
    product: GenerationProduct | None = None
    for attempt in range(4):
        product = _generate_structured_product(
            requirement, catalog, structure, **options
        )
        if product.status == "review" and planner_review is not None:
            candidate = {
                "task_structure": structure.to_dict(),
                "execution_plan": product.plan.to_dict() if product.plan else None,
                "agent": product.source.to_dict() if product.source else None,
                "workflow": product.orchestration.workflow
                if product.orchestration
                else None,
                "companions": [
                    agent.to_dict() for agent in product.orchestration.companions
                ]
                if product.orchestration
                else [],
            }
            try:
                gaps = planner_review(requirement, candidate)
            except (ValueError, TypeError, KeyError):
                return replace(
                    product,
                    status="blocked",
                    source=None,
                    orchestration=None,
                    diagnostics=("coverage_review_invalid",),
                    blocked_reason="product_fidelity_invalid",
                )
            if gaps:
                product = replace(
                    product,
                    status="blocked",
                    source=None,
                    orchestration=None,
                    diagnostics=tuple(gaps),
                    blocked_reason="product_fidelity_invalid",
                )
        repairable = product.blocked_reason in {
            "execution_plan_invalid",
            "compose_failed",
            "compose_empty",
            "product_fidelity_invalid",
        }
        if (
            product.status == "review"
            or not repairable
            or planner_repair is None
            or attempt == 3
            or (
                structure.uncertainty
                and product.blocked_reason == "product_fidelity_invalid"
            )
        ):
            return product
        try:
            payload = planner_repair(
                json.dumps(structure.to_dict(), ensure_ascii=False),
                "; ".join(product.diagnostics),
            )
            next_structure = normalize_task_structure(
                TaskStructure.from_dict(task_structure_payload(payload))
            )
            # Repairs may rephrase prose. Keep the original obligations in the
            # compiled instructions instead of treating wording as lost semantics.
            next_structure = replace(
                next_structure,
                constraints=tuple(
                    dict.fromkeys((*structure.constraints, *next_structure.constraints))
                ),
                success_criteria=tuple(
                    dict.fromkeys(
                        (*structure.success_criteria, *next_structure.success_criteria)
                    )
                ),
            )
            if _required_duties(structure) - _required_duties(next_structure):
                return replace(
                    product,
                    diagnostics=(*product.diagnostics, "repair_removed_required_duty"),
                    blocked_reason="product_fidelity_invalid",
                )
            validate_task_structure(next_structure)
            structure = next_structure
        except (ValueError, TypeError, KeyError):
            return product
    assert product is not None
    return product


def _required_duties(structure: TaskStructure) -> set[tuple[str, str]]:
    duties: set[tuple[str, str]] = {
        (item.kind, item.source or item.reason)
        for item in structure.execution_boundaries
        if item.required
    }
    duties.update(("constraint", item) for item in structure.constraints)
    duties.update(("success_criterion", item) for item in structure.success_criteria)
    return duties


def _generate_structured_product(
    requirement: str,
    catalog: ResourceCatalog,
    structure: TaskStructure,
    *,
    project_resources: Any = None,
    knowledge_inventory: Any = None,
    secret_configured: Any = None,
    model_profiles: Any = (),
    model_bindings: Any = None,
    model_defaults: Any = (),
) -> GenerationProduct:
    decision = decide_product_shape(structure)
    if decision.status != "decided" or decision.shape == "UNSUPPORTED":
        return GenerationProduct(
            status="blocked",
            structure=structure,
            plan=None,
            specification=None,
            source=None,
            orchestration=None,
            resolved=None,
            diagnostics=(decision.blocked_reason or decision.reason,),
            blocked_reason=decision.blocked_reason or "unsupported_shape",
        )
    try:
        plan = compile_execution_plan(structure, decision=decision)
    except (ValueError, TypeError) as exc:
        return GenerationProduct(
            "blocked",
            structure,
            None,
            None,
            None,
            None,
            None,
            (str(exc),),
            "execution_plan_invalid",
        )
    spec = specification_from_plan(plan, requirement=requirement)
    model_requirements = derive_model_requirements(structure, plan)
    model_resolutions = ModelResolver.resolve(
        model_requirements,
        model_profiles,
        model_bindings or {},
        model_defaults,
    )
    requirements = tuple(
        item for item in derive_plan_capabilities(plan) if item.model_capability is None
    )
    resolved = ResourceResolver(catalog, secret_configured=secret_configured).resolve(
        spec,
        requirements,
        project_resources=project_resources or [],
        knowledge_inventory=knowledge_inventory or [],
        requirement_text=requirement,
    )
    entity_tool = None
    for item in (*resolved.selected, *resolved.needs_configuration):
        if "entity_write" in item.capabilities:
            entity_tool = {
                "reference": item.reference,
                "resource_id": item.resource_id,
                "content_hash": item.content_hash,
            }
            break
    if plan.state is not None and entity_tool is None:
        return GenerationProduct(
            status="blocked",
            structure=structure,
            plan=plan,
            specification=spec,
            source=None,
            orchestration=None,
            resolved=resolved,
            diagnostics=("state_requirement_unbound",),
            blocked_reason="State requirement cannot be represented",
            model_requirements=model_requirements,
            model_resolutions=model_resolutions,
        )
    try:
        source, orchestration = compose_execution_product(
            plan,
            resolved,
            requirement=requirement,
            entity_tool=entity_tool,
        )
    except (ValueError, TypeError) as exc:
        return GenerationProduct(
            status="blocked",
            structure=structure,
            plan=plan,
            specification=spec,
            source=None,
            orchestration=None,
            resolved=resolved,
            diagnostics=(str(exc),),
            blocked_reason="compose_failed",
            model_requirements=model_requirements,
            model_resolutions=model_resolutions,
        )
    if source is None and orchestration is None:
        return GenerationProduct(
            status="blocked",
            structure=structure,
            plan=plan,
            specification=spec,
            source=None,
            orchestration=None,
            resolved=resolved,
            diagnostics=("compose_empty",),
            blocked_reason="compose_empty",
            model_requirements=model_requirements,
            model_resolutions=model_resolutions,
        )
    fidelity = validate_product_fidelity(
        requirement, structure, plan, source, orchestration
    )
    if fidelity:
        return GenerationProduct(
            status="blocked",
            structure=structure,
            plan=plan,
            specification=spec,
            source=None,
            orchestration=None,
            resolved=resolved,
            diagnostics=fidelity,
            blocked_reason="product_fidelity_invalid",
            model_requirements=model_requirements,
            model_resolutions=model_resolutions,
        )
    return GenerationProduct(
        status="review",
        structure=structure,
        plan=plan,
        specification=spec,
        source=source,
        orchestration=orchestration,
        resolved=resolved,
        diagnostics=tuple(resolved.diagnostics),
        model_requirements=model_requirements,
        model_resolutions=model_resolutions,
    )


def proposal_preview(product: GenerationProduct) -> dict[str, Any]:
    plan = product.plan
    structure = product.structure
    if plan is None or structure is None:
        return {"status": product.status, "blocked_reason": product.blocked_reason}
    agents = [item.to_dict() for item in plan.actors]
    flow = [
        {
            "id": item.id,
            "kind": item.kind,
            "why": item.why,
            "source": item.source,
        }
        for item in plan.steps
    ]
    return {
        "product_shape": plan.shape.to_dict(),
        "agents": agents,
        "workflow": product.orchestration is not None,
        "persistent_state": None if plan.state is None else plan.state.to_dict(),
        "stages": [item.to_dict() for item in structure.stages],
        "flow": flow,
        "tool_approvals": list(plan.tool_approvals),
        "business_approvals": list(plan.business_approvals),
        "capabilities": list(plan.capabilities),
        "warnings": list(plan.shape.warnings),
        "missing_required": [
            item.to_dict()
            for item in (product.resolved.missing_required if product.resolved else [])
        ],
        "models": _model_preview(product),
    }


def _model_preview(product: GenerationProduct) -> list[dict[str, Any]]:
    previews: list[dict[str, Any]] = []
    for requirement, resolution in zip(
        product.model_requirements, product.model_resolutions, strict=True
    ):
        item: dict[str, Any] = {
            "slot": requirement.slot,
            "actor_id": requirement.actor_id,
            "required": list(requirement.required),
            "optional": list(requirement.optional),
            "reason": requirement.reason,
            "source": requirement.source,
            "status": resolution.status.value,
        }
        if resolution.selected_model_profile_id is not None:
            item["selected_model_profile_id"] = resolution.selected_model_profile_id
            item["selected_model_display_name"] = resolution.selected_model_display_name
            item["selected_provider_label"] = resolution.selected_provider_label
        if resolution.issue is not None:
            item["issue"] = resolution.issue.to_dict()
        else:
            item["issue"] = None
        previews.append(item)
    return previews
