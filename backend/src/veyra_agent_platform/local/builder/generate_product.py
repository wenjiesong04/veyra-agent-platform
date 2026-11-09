"""Factory generation V2: TaskStructure → shape → plan → resolve → compose."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from veyra_agent_platform.contracts.agent import DEFAULT_MAX_TURNS, AgentSource
from veyra_agent_platform.contracts.agent_spec import AgentSpecification
from veyra_agent_platform.contracts.execution_plan import ExecutionPlan
from veyra_agent_platform.contracts.filesystem_scope import path_in_project_scopes
from veyra_agent_platform.contracts.resource_plan import ResourcePlan
from veyra_agent_platform.contracts.task_structure import TaskStructure
from veyra_agent_platform.local.builder.composite_composer import (
    compose_execution_product,
    specification_from_plan,
)
from veyra_agent_platform.local.builder.execution_planner import compile_execution_plan
from veyra_agent_platform.local.builder.model_requirements import (
    derive_model_requirements,
)
from veyra_agent_platform.local.builder.operation_events import (
    CAPABILITIES_RESOLVED,
    CAPABILITIES_STARTED,
    COMPILE_COMPLETED,
    COMPILE_STARTED,
    SEMANTIC_PLAN_COMPLETED,
    SEMANTIC_PLAN_STARTED,
    SPECIFICATION_COMPLETED,
    VALIDATION_COMPLETED,
    VALIDATION_STARTED,
)
from veyra_agent_platform.local.builder.plan_resources import resolve_plan_resources
from veyra_agent_platform.local.builder.product_shape import decide_product_shape
from veyra_agent_platform.local.builder.product_validation import (
    validate_product_fidelity,
)
from veyra_agent_platform.local.builder.task_planner import (
    PlannerProvider,
    normalize_task_structure,
    plan_task_structure,
    required_task_duties,
    validate_task_structure,
)
from veyra_agent_platform.local.builder.task_structure_schema import (
    task_structure_payload,
    task_structure_projection,
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
    initial_model_turns: int = DEFAULT_MAX_TURNS,
    on_stage: Callable[[str, dict[str, str]], None] | None = None,
) -> GenerationProduct:
    def stage(kind: str, facts: dict[str, str] | None = None) -> None:
        if on_stage is not None:
            on_stage(kind, facts or {})

    stage(SEMANTIC_PLAN_STARTED)
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
    stage(SPECIFICATION_COMPLETED)
    stage(SEMANTIC_PLAN_COMPLETED)
    options = dict(
        project_resources=project_resources,
        knowledge_inventory=knowledge_inventory,
        secret_configured=secret_configured,
        model_profiles=model_profiles,
        model_bindings=model_bindings,
        model_defaults=model_defaults,
        initial_model_turns=initial_model_turns,
        catalog_snapshot=getattr(planner_provider, "resource_snapshot", None),
        require_grounded_skills=bool(
            getattr(planner_provider, "requires_skill_grounding", False)
        ),
        on_stage=stage,
    )
    product: GenerationProduct | None = None
    repair_limit = getattr(planner_provider, "max_repairs", 3)
    if repair_limit is None:
        repair_limit = getattr(planner_provider, "max_requests", 3)
    for attempt in range(repair_limit + 1):
        coverage_repair = False
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
                stage(VALIDATION_STARTED, {"phase": "coverage_review"})
                gaps = planner_review(requirement, candidate)
            except (ValueError, TypeError, KeyError) as exc:
                diagnostic = getattr(exc, "safe_repair_diagnostic", None)
                return replace(
                    product,
                    status="blocked",
                    source=None,
                    orchestration=None,
                    diagnostics=(
                        diagnostic[:1_600]
                        if isinstance(diagnostic, str)
                        else "coverage_review_invalid",
                    ),
                    blocked_reason="product_fidelity_invalid",
                )
            if gaps:
                coverage_repair = True
                product = replace(
                    product,
                    status="blocked",
                    source=None,
                    orchestration=None,
                    diagnostics=tuple(gaps),
                    blocked_reason="product_fidelity_invalid",
                )
        if product.status == "review":
            stage(
                VALIDATION_COMPLETED,
                {"phase": "coverage_review" if planner_review else "structural"},
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
            or attempt == repair_limit
            or (
                structure.uncertainty
                and product.blocked_reason == "product_fidelity_invalid"
            )
        ):
            if attempt == repair_limit and repairable and product.status != "review":
                return replace(
                    product,
                    diagnostics=(
                        "planner_repair_limit_reached; retained_ir=last_validated",
                        *product.diagnostics,
                    ),
                )
            return product
        try:
            payload = planner_repair(
                json.dumps(task_structure_projection(structure), ensure_ascii=False),
                "; ".join(product.diagnostics),
            )
            next_structure = normalize_task_structure(
                TaskStructure.from_dict(task_structure_payload(payload))
            )
            if not coverage_repair:
                # Format/binding repairs preserve the plan's duties. Semantic
                # corrections instead re-enter coverage against the original task.
                next_structure = replace(
                    next_structure,
                    constraints=tuple(
                        dict.fromkeys(
                            (*structure.constraints, *next_structure.constraints)
                        )
                    ),
                    success_criteria=tuple(
                        dict.fromkeys(
                            (
                                *structure.success_criteria,
                                *next_structure.success_criteria,
                            )
                        )
                    ),
                )
                if required_task_duties(structure) - required_task_duties(
                    next_structure
                ):
                    return replace(
                        product,
                        diagnostics=(
                            *product.diagnostics,
                            "repair_removed_required_duty",
                        ),
                        blocked_reason="product_fidelity_invalid",
                    )
            if structure.filesystem_write_roots and (
                not next_structure.filesystem_write_roots
                or any(
                    not path_in_project_scopes(
                        "." if root == "project" else root.removeprefix("project/"),
                        structure.filesystem_write_roots,
                        allow_root=True,
                    )
                    for root in next_structure.filesystem_write_roots
                )
            ):
                return replace(
                    product,
                    diagnostics=(*product.diagnostics, "repair_widened_write_scope"),
                    blocked_reason="product_fidelity_invalid",
                )
            validate_task_structure(next_structure)
            if next_structure.to_dict() == structure.to_dict():
                return replace(
                    product,
                    diagnostics=(*product.diagnostics, "planner_repair_no_progress"),
                )
            structure = next_structure
        except (ValueError, TypeError, KeyError) as exc:
            # Provider/model values and arbitrary exception text are not diagnostics.
            diagnostic = getattr(exc, "safe_repair_diagnostic", None)
            if not isinstance(diagnostic, str):
                diagnostic = "planner_repair_invalid"
            return replace(
                product,
                diagnostics=(
                    diagnostic[:1_600] + "; retained_ir=last_validated",
                    *product.diagnostics,
                ),
            )
    assert product is not None
    return product


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
    catalog_snapshot: Any = None,
    require_grounded_skills: bool = False,
    initial_model_turns: int = DEFAULT_MAX_TURNS,
    on_stage: Callable[[str, dict[str, str]], None] | None = None,
) -> GenerationProduct:
    def stage(kind: str, facts: dict[str, str] | None = None) -> None:
        if on_stage is not None:
            on_stage(kind, facts or {})

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
    stage(CAPABILITIES_STARTED)
    model_requirements = derive_model_requirements(structure, plan)
    model_resolutions = ModelResolver.resolve(
        model_requirements,
        model_profiles,
        model_bindings or {},
        model_defaults,
    )
    try:
        resolved, actor_resources = resolve_plan_resources(
            plan,
            structure,
            ResourceResolver(catalog, secret_configured=secret_configured),
            requirement=requirement,
            project_resources=project_resources or [],
            knowledge_inventory=knowledge_inventory or [],
            catalog_snapshot=catalog_snapshot,
        )
    except (ValueError, TypeError) as exc:
        return GenerationProduct(
            "blocked",
            structure,
            plan,
            spec,
            None,
            None,
            None,
            (str(exc),),
            "execution_plan_invalid",
        )
    declared_methods = {item.reference for item in structure.skill_choices}
    stage(CAPABILITIES_RESOLVED, {"missing_count": str(len(resolved.missing_required))})
    unread_methods = tuple(
        item.reference
        for item in (*resolved.selected, *resolved.needs_configuration)
        if item.kind == "skill" and item.reference not in declared_methods
    )
    if require_grounded_skills and unread_methods:
        return GenerationProduct(
            "blocked",
            structure,
            plan,
            spec,
            None,
            None,
            resolved,
            (
                "Declare needed skill_choices before composition so their actual "
                "methods can be read: " + ", ".join(unread_methods),
            ),
            "execution_plan_invalid",
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
        stage(COMPILE_STARTED)
        source, orchestration = compose_execution_product(
            plan,
            resolved,
            requirement=requirement,
            entity_tool=entity_tool,
            actor_resources=actor_resources,
            initial_model_turns=initial_model_turns,
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
    stage(COMPILE_COMPLETED)
    stage(VALIDATION_STARTED, {"phase": "structural"})
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
        "skill_choices": [item.to_dict() for item in structure.skill_choices],
        "filesystem_write_roots": list(structure.filesystem_write_roots),
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
