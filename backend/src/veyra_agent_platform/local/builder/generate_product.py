"""Factory generation V2: TaskStructure → shape → plan → resolve → compose."""

from __future__ import annotations

from dataclasses import dataclass
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
from veyra_agent_platform.local.builder.product_shape import decide_product_shape
from veyra_agent_platform.local.builder.task_planner import plan_task_structure
from veyra_agent_platform.local.builder.workflow_orchestration import (
    WorkflowOrchestration,
)
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


def generate_builder_product(
    requirement: str,
    catalog: ResourceCatalog,
    *,
    project_resources: list[dict[str, Any]] | None = None,
    knowledge_inventory: list[dict[str, Any]] | None = None,
    secret_configured: Any = None,
) -> GenerationProduct:
    planned = plan_task_structure(requirement)
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
    plan = compile_execution_plan(structure, decision=decision)
    spec = specification_from_plan(plan, requirement=requirement)
    requirements = derive_plan_capabilities(plan)
    resolved = ResourceResolver(catalog, secret_configured=secret_configured).resolve(
        spec,
        requirements,
        project_resources=project_resources or [],
        knowledge_inventory=knowledge_inventory or [],
        requirement_text=requirement,
    )
    missing_required = [item.capability for item in resolved.missing_required]
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
        blocked_reason=(
            "missing_required:image_generation"
            if "image_generation" in missing_required
            else ""
        ),
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
    }
