"""Compile TaskStructure + shape into a typed ExecutionPlan."""

from __future__ import annotations

import re

from veyra_agent_platform.contracts.common import SCHEMA_VERSION
from veyra_agent_platform.contracts.execution_plan import (
    ExecutionPlan,
    PlanActor,
    PlanStep,
    ProductShapeDecision,
    task_payload,
)
from veyra_agent_platform.contracts.task_structure import (
    ExecutionBoundary,
    TaskStructure,
)

from .product_shape import decide_product_shape


def _nid(value: str) -> str:
    text = re.sub(r"[^a-z0-9_]", "", value.casefold().replace("-", "_"))
    return (text or "step")[:63]


def compile_execution_plan(
    structure: TaskStructure,
    *,
    decision: ProductShapeDecision | None = None,
) -> ExecutionPlan:
    shape = decision or decide_product_shape(structure)
    if shape.status != "decided":
        return ExecutionPlan(
            schema_version=SCHEMA_VERSION,
            shape=shape,
            task=task_payload(structure),
            actors=(),
            steps=(),
            inputs=structure.inputs,
            outputs=structure.outputs,
            state=structure.state,
            capabilities=_capabilities(structure),
            tool_approvals=_tool_approvals(structure),
            business_approvals=_business_approvals(structure),
            missing_capabilities=(),
            interaction=structure.lifecycle.interaction,
        )
    actors = _actors(structure, shape.shape)
    steps = _steps(structure, shape.shape, actors)
    return ExecutionPlan(
        schema_version=SCHEMA_VERSION,
        shape=shape,
        task=task_payload(structure),
        actors=actors,
        steps=steps,
        inputs=structure.inputs,
        outputs=structure.outputs,
        state=structure.state,
        capabilities=_capabilities(structure),
        tool_approvals=_tool_approvals(structure),
        business_approvals=_business_approvals(structure),
        missing_capabilities=(),
        interaction=structure.lifecycle.interaction,
    )


def _actors(structure: TaskStructure, shape: str) -> tuple[PlanActor, ...]:
    if shape == "PURE_AGENT":
        caps = _capabilities(structure)
        name = structure.goal[:40] or "Agent"
        return (
            PlanActor(
                id="main",
                kind="agent",
                name=name,
                capabilities=caps,
                brief=structure.summary[:400],
            ),
        )
    if shape == "WORKFLOW":
        return ()
    actors: list[PlanActor] = []
    for item in structure.actors:
        if item.id == "main" and len(structure.actors) > 1:
            continue
        actors.append(
            PlanActor(
                id=item.id,
                kind="agent",
                name=_actor_name(item.role, item.id),
                capabilities=item.capabilities,
                brief=item.reason or item.role,
            )
        )
    if not actors:
        actors.append(
            PlanActor(
                id="main",
                kind="agent",
                name=structure.goal[:40] or "Agent",
                capabilities=_capabilities(structure),
                brief=structure.summary[:400],
            )
        )
    return tuple(actors)


def _actor_name(role: str, actor_id: str) -> str:
    labels = {
        "analyzer": "Analyzer",
        "researcher": "Researcher",
        "writer": "Writer",
        "renderer": "Renderer",
        "editor": "Editor",
        "assistant": "Assistant",
    }
    return labels.get(role, actor_id.replace("-", " ").title())


def _steps(
    structure: TaskStructure,
    shape: str,
    actors: tuple[PlanActor, ...],
) -> tuple[PlanStep, ...]:
    if shape == "PURE_AGENT":
        return (
            PlanStep(id="start", kind="start", why="Run begins"),
            PlanStep(
                id="reason",
                kind="agent_call",
                agent="main",
                why="A single Agent loop owns reasoning and tools",
            ),
            PlanStep(id="output", kind="output", why="Return the declared outputs"),
        )
    vision = next((item.id for item in actors if "vision" in item.capabilities), "")
    search = next(
        (item.id for item in actors if "web_search" in item.capabilities),
        "",
    )
    renderer = next(
        (item.id for item in actors if "image_generation" in item.capabilities),
        "",
    )
    writer = next((item.id for item in actors if item.id == "writer"), "")
    default_agent = actors[0].id if actors else ""
    backbone: list[PlanStep] = [PlanStep(id="start", kind="start", why="Run begins")]
    side: list[PlanStep] = []
    if vision:
        backbone.append(
            PlanStep(
                id="identify",
                kind="agent_call",
                agent=vision,
                why="Vision reasoning extracts structured facts",
                source=_source(structure, "multimodal"),
            )
        )
    elif default_agent and shape != "WORKFLOW":
        backbone.append(
            PlanStep(
                id="analyze",
                kind="agent_call",
                agent=default_agent,
                why="A companion Agent performs the reasoning stage",
                source=_source(structure, "reasoning"),
            )
        )
    for boundary in structure.execution_boundaries:
        if boundary.kind == "condition":
            human = _matching_input(structure, boundary)
            false_target = _nid(human.stage) if human else "output"
            backbone.append(
                PlanStep(
                    id=_nid(boundary.stage),
                    kind="condition",
                    why=boundary.reason,
                    expression=boundary.expression,
                    source=boundary.source,
                    on_false=false_target,
                )
            )
            if human is not None and not any(
                item.id == _nid(human.stage) for item in side
            ):
                side.append(
                    PlanStep(
                        id=_nid(human.stage),
                        kind="human_input",
                        why=human.reason,
                        question=human.question,
                        expected_schema=human.expected_schema,
                        source=human.source,
                    )
                )
        elif boundary.kind == "tool" and boundary.capability == "web_search" and search:
            if not any(item.id == "research" for item in backbone):
                backbone.append(
                    PlanStep(
                        id="research",
                        kind="agent_call",
                        agent=search,
                        why=boundary.reason,
                        source=boundary.source,
                    )
                )
        elif (
            boundary.kind == "tool"
            and boundary.capability == "image_generation"
            and renderer
        ):
            if not any(item.id == "render" for item in backbone):
                backbone.append(
                    PlanStep(
                        id="render",
                        kind="agent_call",
                        agent=renderer,
                        why=boundary.reason,
                        capability="image_generation",
                        source=boundary.source,
                    )
                )
        elif boundary.kind == "human_approval" and boundary.approval_class != "tool":
            backbone.append(
                PlanStep(
                    id=_nid(boundary.stage),
                    kind="human_approval",
                    why=boundary.reason,
                    prompt=boundary.reason,
                    source=boundary.source,
                )
            )
        elif boundary.kind == "state":
            if not any(item.id == "seed_state" for item in backbone):
                backbone.append(
                    PlanStep(
                        id="seed_state",
                        kind="transform",
                        why="Bind the persistent entity type before writing",
                        entity=boundary.entity,
                        source=boundary.source,
                    )
                )
            backbone.append(
                PlanStep(
                    id=_nid(boundary.stage),
                    kind="state_write",
                    why=boundary.reason,
                    entity=boundary.entity,
                    source=boundary.source,
                )
            )
        elif boundary.kind == "verification":
            backbone.append(
                PlanStep(
                    id=_nid(boundary.stage),
                    kind="verifier",
                    why=boundary.reason,
                    checks=boundary.checks,
                    source=boundary.source,
                )
            )
    if writer and not any(item.id == "compose" for item in backbone):
        index = next(
            (
                i
                for i, item in enumerate(backbone)
                if item.kind in {"human_approval", "state_write", "verifier"}
            ),
            len(backbone),
        )
        backbone.insert(
            index,
            PlanStep(
                id="compose",
                kind="agent_call",
                agent="writer",
                why="A writing role turns research into user-facing copy",
                source=_source(structure, "reasoning"),
            ),
        )
    if backbone[-1].kind != "output":
        backbone.append(PlanStep(id="output", kind="output", why="Return outputs"))
    _retarget_skip_approval(backbone)
    return _wire(backbone, side)


def _retarget_skip_approval(backbone: list[PlanStep]) -> None:
    for index, step in enumerate(backbone):
        if step.kind != "condition" or step.id not in {"amount_gate", "threshold_gate"}:
            continue
        approval = next(
            (item for item in backbone[index + 1 :] if item.kind == "human_approval"),
            None,
        )
        if approval is None:
            continue
        after = next(
            (
                item
                for item in backbone[index + 1 :]
                if item.id != approval.id and item.kind != "human_approval"
            ),
            None,
        )
        backbone[index] = PlanStep(
            id=step.id,
            kind=step.kind,
            why=step.why,
            expression=step.expression,
            source=step.source,
            on_true=approval.id,
            on_false=after.id if after is not None else "output",
        )


def _wire(backbone: list[PlanStep], side: list[PlanStep]) -> tuple[PlanStep, ...]:
    wired: list[PlanStep] = []
    for index, step in enumerate(backbone):
        nxt = backbone[index + 1].id if index + 1 < len(backbone) else ""
        on_next = nxt
        on_true = step.on_true
        on_false = step.on_false
        on_approved = step.on_approved
        on_rejected = step.on_rejected
        if step.kind == "condition":
            on_true = step.on_true or nxt or "output"
            on_false = step.on_false or "output"
            on_next = on_true
        elif step.kind == "human_approval":
            on_approved = nxt or "output"
            on_rejected = "output"
            on_next = on_approved
        elif step.kind == "verifier":
            on_true = nxt or "output"
            on_false = "output"
            on_next = on_true
        elif step.kind != "output":
            on_next = nxt or "output"
        wired.append(
            PlanStep(
                id=step.id,
                kind=step.kind,
                why=step.why,
                agent=step.agent,
                expression=step.expression,
                question=step.question,
                prompt=step.prompt,
                checks=step.checks,
                entity=step.entity,
                capability=step.capability,
                source=step.source,
                expected_schema=step.expected_schema,
                on_true=on_true,
                on_false=on_false,
                on_approved=on_approved,
                on_rejected=on_rejected,
                on_next=on_next,
            )
        )
    extras: list[PlanStep] = []
    for step in side:
        owner = next(
            (item for item in wired if item.on_false == step.id),
            None,
        )
        resume = owner.on_true if owner is not None else "output"
        extras.append(
            PlanStep(
                id=step.id,
                kind=step.kind,
                why=step.why,
                question=step.question,
                expected_schema=step.expected_schema,
                source=step.source,
                on_approved=resume,
                on_rejected="output",
                on_next=resume,
            )
        )
    ordered = list(wired)
    for item in extras:
        owner_index = next(
            (i for i, step in enumerate(ordered) if step.on_false == item.id),
            len(ordered) - 1,
        )
        ordered.insert(owner_index + 1, item)
    return tuple(ordered)


def _matching_input(
    structure: TaskStructure, boundary: ExecutionBoundary
) -> ExecutionBoundary | None:
    wanted = {
        "information_check": "request_missing",
        "image_quality": "request_new_images",
    }.get(_nid(boundary.stage))
    if wanted:
        for item in structure.execution_boundaries:
            if item.kind == "human_input" and _nid(item.stage) == wanted:
                return item
    if _nid(boundary.stage) in {"amount_gate", "threshold_gate"}:
        return None
    return None


def _boundary(structure: TaskStructure, kind: str) -> ExecutionBoundary | None:
    for item in structure.execution_boundaries:
        if item.kind == kind:
            return item
    return None


def _source(structure: TaskStructure, kind: str) -> str:
    item = _boundary(structure, kind)
    return item.source if item is not None else ""


def _capabilities(structure: TaskStructure) -> tuple[str, ...]:
    names: list[str] = []
    for item in structure.execution_boundaries:
        if item.capability:
            names.append(item.capability)
        if item.kind == "multimodal":
            names.append("vision")
        if item.kind == "state":
            names.extend(("entity_read", "entity_write"))
    if any(field.type == "image" for field in structure.inputs):
        names.append("vision")
    unique = list(dict.fromkeys(name for name in names if name))
    return tuple(unique)


def _tool_approvals(structure: TaskStructure) -> tuple[str, ...]:
    return tuple(
        item.capability
        for item in structure.execution_boundaries
        if item.approval_class == "tool" and item.capability
    )


def _business_approvals(structure: TaskStructure) -> tuple[str, ...]:
    return tuple(
        item.stage
        for item in structure.execution_boundaries
        if item.kind == "human_approval" and item.approval_class != "tool"
    )
