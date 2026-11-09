"""Compile TaskStructure + shape into a typed ExecutionPlan."""

from __future__ import annotations

import re
from dataclasses import replace

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
    TaskIOField,
    TaskStructure,
)

from .approval_routing import approval_outcome
from .product_shape import (
    decide_product_shape,
    effective_actor_capabilities,
    native_loop_input,
    native_loop_state,
    native_loop_verification,
    validate_business_gate_ownership,
)


def _nid(value: str) -> str:
    text = re.sub(r"[^a-z0-9_]", "", value.casefold().replace("-", "_"))
    return (text or "step")[:63]


def compile_execution_plan(
    structure: TaskStructure,
    *,
    decision: ProductShapeDecision | None = None,
) -> ExecutionPlan:
    validate_business_gate_ownership(structure)
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
        state=(
            None
            if shape.shape == "PURE_AGENT"
            and not structure.lifecycle.persistent
            and structure.state is not None
            and structure.state.scope in {"run", "conversation"}
            and not any(b.kind == "state" for b in structure.execution_boundaries)
            else structure.state
        ),
        capabilities=_capabilities(structure),
        tool_approvals=_tool_approvals(structure),
        business_approvals=_business_approvals(structure),
        missing_capabilities=(),
        interaction=structure.lifecycle.interaction,
    )


def _actors(structure: TaskStructure, shape: str) -> tuple[PlanActor, ...]:
    if shape == "PURE_AGENT":
        caps = _capabilities(structure)
        name = (
            structure.actors[0].role[:60]
            if structure.actors and structure.actors[0].role
            else structure.goal[:40] or "Agent"
        )
        return (
            PlanActor(
                id="main",
                kind="agent",
                name=name,
                capabilities=caps,
                brief=structure.summary[:400],
                inputs=_native_inputs(structure),
            ),
        )
    if shape == "WORKFLOW":
        return ()
    actors: list[PlanActor] = []
    scheduled = {stage.actor for stage in structure.stages if stage.actor}
    for item in structure.actors:
        if item.id == "main" and len(structure.actors) > 1 and item.id not in scheduled:
            continue
        actors.append(
            PlanActor(
                id=item.id,
                kind="agent",
                name=_actor_name(item.role, item.id),
                capabilities=effective_actor_capabilities(structure, item),
                brief=item.reason or item.role,
                inputs=item.inputs,
                outputs=item.outputs,
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


def _native_inputs(structure: TaskStructure) -> tuple[TaskIOField, ...]:
    if len(structure.actors) != 1:
        return structure.inputs
    fields = {item.name.replace("_", "-"): item for item in structure.inputs}
    for item in structure.actors[0].inputs:
        key = item.name.replace("_", "-")
        if key not in fields:
            fields[key] = item
        elif (fields[key].type, fields[key].multiple) != (item.type, item.multiple):
            raise ValueError("Task and autonomous role inputs have conflicting types")
    return tuple(fields.values())


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
    if any(stage.actor for stage in structure.stages):
        return _semantic_steps(structure, actors)
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
        elif boundary.kind == "human_input":
            if not any(item.id == _nid(boundary.stage) for item in side):
                backbone.append(_boundary_step(boundary))
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
    ids = {step.id for step in (*backbone, *side)}
    stop_id = "stop"
    suffix = 2
    while stop_id in ids:
        stop_id = f"stop_{suffix}"
        suffix += 1
    needs_stop = False
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
        elif step.kind in {"human_approval", "human_input"}:
            on_approved = step.on_approved or nxt or "output"
            on_rejected = step.on_rejected or (
                stop_id if step.kind == "human_approval" else "output"
            )
            needs_stop |= step.kind == "human_approval" and not step.on_rejected
            on_next = on_approved
        elif step.kind == "verifier":
            on_true = nxt or "output"
            on_false = "output"
            on_next = on_true
        elif step.kind not in {"output", "stop"}:
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
                input_sources=step.input_sources,
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
    if needs_stop:
        position = (
            len(ordered) - 1
            if ordered and ordered[-1].kind == "output"
            else len(ordered)
        )
        ordered.insert(
            position,
            PlanStep(id=stop_id, kind="stop", why="Rejection stops without delivery"),
        )
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
    # Legacy language plans have branch labels rather than executable stage ids.
    # Associate a following request by structural position, not business names.
    boundaries = structure.execution_boundaries
    index = boundaries.index(boundary)
    for item in boundaries[index + 1 :]:
        if item.kind == "human_input":
            return item
        if item.kind in {"condition", "human_approval", "verification", "state"}:
            break
    return None


def _boundary_step(boundary: ExecutionBoundary, *, step_id: str = "") -> PlanStep:
    kinds = {
        "condition": "condition",
        "human_input": "human_input",
        "human_approval": "human_approval",
        "verification": "verifier",
        "state": "state_write",
    }
    kind = kinds.get(boundary.kind)
    if kind is None:
        raise ValueError(f"unsupported execution boundary: {boundary.kind}")
    return PlanStep(
        id=step_id or _nid(boundary.stage),
        kind=kind,  # type: ignore[arg-type]
        why=boundary.reason,
        expression=boundary.expression,
        question=boundary.question,
        prompt=(boundary.question or boundary.reason)
        if kind == "human_approval"
        else "",
        checks=boundary.checks,
        entity=boundary.entity,
        capability=boundary.capability,
        expected_schema=boundary.expected_schema,
        source=boundary.source,
    )


def _semantic_steps(
    structure: TaskStructure, actors: tuple[PlanActor, ...]
) -> tuple[PlanStep, ...]:
    """Compile the model's semantic ordering; capability labels are not ordering."""
    known = {actor.id: actor for actor in actors}
    if len(known) != len(actors):
        raise ValueError("duplicate task actor id")
    stage_ids = [_nid(stage.id) for stage in structure.stages]
    if len(set(stage_ids)) != len(stage_ids) or {"start", "output"} & set(stage_ids):
        raise ValueError("duplicate or reserved task stage id")
    backbone = [PlanStep(id="start", kind="start", why="Run begins")]
    used: set[int] = set()
    for stage in structure.stages:
        if stage.actor:
            if stage.actor not in known:
                raise ValueError(f"unknown stage actor: {stage.actor}")
            backbone.append(
                PlanStep(
                    id=_nid(stage.id),
                    kind="agent_call",
                    agent=stage.actor,
                    why=stage.summary,
                    source=stage.source,
                    input_sources=stage.input_sources,
                )
            )
        matching = [
            (index, boundary)
            for index, boundary in enumerate(structure.execution_boundaries)
            if _nid(boundary.stage) == _nid(stage.id)
        ]
        routes: dict[str, str] = {}
        folded: set[int] = set()
        declared_stages = {item.id: _nid(item.id) for item in structure.stages}
        declared_stages["output"] = "output"
        for index, boundary in matching:
            outcome = approval_outcome(structure, boundary)
            if outcome is None:
                continue
            folded.add(index)
            if len(boundary.branches) == 2 and all(
                value in declared_stages for value in boundary.branches
            ):
                branch_targets = {declared_stages[value] for value in boundary.branches}
                if len(branch_targets) == 2 and "output" not in branch_targets:
                    raise ValueError(
                        "approval_branch_join_ambiguous: distinct non-terminal "
                        f"routes at stage {stage.id} need explicit branch joins; "
                        "a linear stage list cannot safely separate their actions"
                    )
                for approved, truth in (
                    (True, outcome.true_means_approved),
                    (False, not outcome.true_means_approved),
                ):
                    port = "approved" if approved else "rejected"
                    target = declared_stages[boundary.branches[0 if truth else 1]]
                    if port in routes and routes[port] != target:
                        raise ValueError(
                            "approval predicates disagree on their control route"
                        )
                    routes[port] = target
        used.update(folded)
        matching = [
            (index, boundary) for index, boundary in matching if index not in folded
        ]
        for index, boundary in matching:
            used.add(index)
            if boundary.kind in {"reasoning", "multimodal", "tool", "artifact"}:
                if boundary.kind == "tool" and boundary.required:
                    actor = known.get(stage.actor)
                    if actor is None or boundary.capability not in actor.capabilities:
                        raise ValueError(
                            "required capability boundary has no owning actor"
                        )
                elif (
                    boundary.required
                    and not stage.actor
                    and boundary.kind != "artifact"
                ):
                    raise ValueError("required reasoning boundary has no owning actor")
                continue
            if boundary.kind == "human_approval" and boundary.approval_class == "tool":
                continue
            if boundary.kind == "human_input" and native_loop_input(
                structure, boundary.stage
            ):
                continue
            if boundary.kind == "verification" and native_loop_verification(
                structure, boundary.stage
            ):
                continue
            if (
                boundary.kind == "state"
                and native_loop_state(structure, boundary.stage)
                and structure.state is not None
                and boundary.entity == structure.state.entity
            ):
                continue
            if boundary.kind == "state":
                backbone.append(
                    PlanStep(
                        id=f"{_nid(stage.id)}_state_type",
                        kind="transform",
                        why="Bind the declared entity type",
                        entity=boundary.entity,
                    )
                )
            suffix = (
                f"_{boundary.kind}_{index}" if stage.actor or len(matching) > 1 else ""
            )
            compiled = _boundary_step(boundary, step_id=_nid(stage.id) + suffix)
            if boundary.kind in {"verification", "human_approval"} and not stage.actor:
                compiled = replace(compiled, input_sources=stage.input_sources)
            if boundary.kind == "human_approval":
                compiled = replace(
                    compiled,
                    on_approved=routes.get("approved", ""),
                    on_rejected=routes.get("rejected", ""),
                )
            backbone.append(compiled)
        if not stage.actor and not matching:
            raise ValueError(f"stage has no executable actor or boundary: {stage.id}")
    for index, boundary in enumerate(structure.execution_boundaries):
        if index in used:
            continue
        if boundary.kind in {"reasoning", "multimodal", "tool", "artifact"}:
            if boundary.required and boundary.kind != "artifact":
                raise ValueError("required boundary has no executable semantic stage")
            continue
        if boundary.kind == "human_approval" and boundary.approval_class == "tool":
            continue
        if boundary.required:
            # A required user/state/check boundary may not silently disappear.
            if boundary.kind == "state":
                backbone.append(
                    PlanStep(
                        id=f"{_nid(boundary.stage)}_state_type",
                        kind="transform",
                        why="Bind the declared entity type",
                        entity=boundary.entity,
                    )
                )
            backbone.append(_boundary_step(boundary))
    backbone.append(PlanStep(id="output", kind="output", why="Return outputs"))
    wired = list(_wire(backbone, []))
    # Model plans may name branch stage ids. Labels alone do not grant looping.
    boundary_by_stage = {
        _nid(item.stage): item for item in structure.execution_boundaries
    }
    for index, step in enumerate(wired):
        if step.kind != "condition":
            continue
        condition_boundary = boundary_by_stage.get(step.id)
        if condition_boundary and len(condition_boundary.branches) == 2:
            targets = tuple(_nid(value) for value in condition_boundary.branches)
            if all(target in {item.id for item in wired} for target in targets):
                wired[index] = replace(step, on_true=targets[0], on_false=targets[1])
    return tuple(wired)


def _boundary(structure: TaskStructure, kind: str) -> ExecutionBoundary | None:
    for item in structure.execution_boundaries:
        if item.kind == kind:
            return item
    return None


def _source(structure: TaskStructure, kind: str) -> str:
    item = _boundary(structure, kind)
    return item.source if item is not None else ""


def _capabilities(structure: TaskStructure) -> tuple[str, ...]:
    names: list[str] = [
        capability for actor in structure.actors for capability in actor.capabilities
    ]
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
