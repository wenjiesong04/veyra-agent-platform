"""Compile actor-owned delivery boundaries into an executable loop policy."""

from __future__ import annotations

from dataclasses import replace

from veyra_agent_platform.contracts.agent_spec import AgentSpecification
from veyra_agent_platform.contracts.common import thaw_json
from veyra_agent_platform.contracts.condition import (
    parse_condition_expression,
    parse_value_path,
)
from veyra_agent_platform.contracts.execution_plan import ExecutionPlan, PlanActor
from veyra_agent_platform.contracts.finalization import FinalizationContract
from veyra_agent_platform.contracts.task_structure import TaskStructure
from veyra_agent_platform.contracts.verification import parse_verifier_check

from .agent_composer import agent_io_name
from .product_shape import native_loop_verification, stage_key
from .task_bindings import resolve_declared_reference


def _delivery_bindings(
    structure: TaskStructure,
    specification: AgentSpecification,
    owned: set[str],
) -> dict[str, tuple[str, bool]]:
    """Bind only owned, declared, type-compatible producer ports to exports."""
    actors = {actor.id: actor for actor in structure.actors}
    ports = {
        f"{stage.id}.{port.name}": port
        for stage in structure.stages
        if stage_key(stage.id) in owned and stage.actor in actors
        for port in actors[stage.actor].outputs
    }
    aliases: dict[str, dict[str, bool]] = {}
    for output in specification.outputs:
        try:
            explicit = len(parse_value_path(output.source)) >= 2
        except ValueError:
            explicit = False
        if explicit:
            producer = resolve_declared_reference(
                output.source,
                task_inputs={},
                producer_outputs={name: name for name in ports},
            )
            candidates = [producer] if producer is not None else []
        else:
            candidates = [
                name
                for name, port in ports.items()
                if agent_io_name(port.name) == agent_io_name(output.name)
                and port.type == output.type
                and port.multiple == output.multiple
            ]
            # A bare matching name cannot choose between multiple stages.
            if len(candidates) != 1:
                continue
        for producer in candidates:
            port = ports[producer]
            if port.type == output.type and port.multiple == output.multiple:
                exports = aliases.setdefault(producer, {})
                name = agent_io_name(output.name)
                exports[name] = exports.get(name, False) or explicit
    return {
        producer: next(iter(exports.items()))
        for producer, exports in aliases.items()
        if len(exports) == 1
    }


def actor_finalization(
    plan: ExecutionPlan,
    specification: AgentSpecification,
    actor: PlanActor | None = None,
) -> FinalizationContract | None:
    structure = TaskStructure.from_dict(thaw_json(plan.task))
    owned = {
        stage_key(stage.id)
        for stage in structure.stages
        if stage.actor and (actor is None or stage.actor == actor.id)
    }
    boundaries = [
        boundary
        for boundary in structure.execution_boundaries
        if boundary.kind == "verification"
        and stage_key(boundary.stage) in owned
        and native_loop_verification(structure, boundary.stage)
    ]
    if not boundaries:
        return None
    required_questions = tuple(
        boundary.question or boundary.reason
        for boundary in structure.execution_boundaries
        if boundary.kind == "human_input"
        and boundary.required
        and stage_key(boundary.stage) in owned
    )
    fields = {agent_io_name(output.name): output for output in specification.outputs}
    bindings = _delivery_bindings(structure, specification, owned)
    actors = {item.id: item for item in structure.actors}
    declared_producers = {
        f"{stage.id}.{port.name}": stage.actor
        for stage in structure.stages
        if stage.actor in actors
        for port in actors[stage.actor].outputs
    }

    def delivery_path(path: tuple[str, ...]) -> tuple[str, ...]:
        root = agent_io_name(path[0])
        binding = None
        producer = None
        if len(path) >= 2:
            binding = resolve_declared_reference(
                ".".join(path[:2]), task_inputs={}, producer_outputs=bindings
            )
            producer = resolve_declared_reference(
                ".".join(path[:2]),
                task_inputs={},
                producer_outputs=declared_producers,
            )
        if binding is not None and binding[1]:
            return (binding[0], *path[2:])
        if producer is not None and binding is None:
            raise ValueError(
                "undeclared delivery condition: producer is not an owned export"
            )
        if root in fields:
            if binding is not None:
                raise ValueError(
                    "ambiguous delivery condition; declare its output source"
                )
            return (root, *path[1:])
        if binding is not None:
            return (binding[0], *path[2:])
        raise ValueError(f"undeclared delivery condition: {path[0]}")

    checks: list[str] = []
    for boundary in boundaries:
        if not boundary.required:
            continue
        for check in boundary.checks or ("output.not_empty",):
            kind, argument = parse_verifier_check(check)
            if kind in {"required_fields", "artifact_exists"}:
                path = delivery_path(parse_value_path(argument))
                if len(path) != 1:
                    raise ValueError(f"undeclared delivery check field: {argument}")
                check = f"{kind}:{path[0]}"
            elif kind == "constraint_match":
                expression = parse_condition_expression(argument)
                expression = replace(
                    expression, field=".".join(delivery_path(expression.path))
                )
                check = f"{kind}:{expression.to_text()}"
            elif kind == "schema_valid" and "result" not in fields:
                raise ValueError("schema_valid requires a result output")
            checks.append(check)
    criteria = tuple(
        dict.fromkeys(
            [
                *(
                    boundary.reason
                    for boundary in boundaries
                    if boundary.reason and boundary.required
                ),
                *(structure.constraints if actor is None else ()),
                *(structure.success_criteria if actor is None else ()),
                *(
                    "Resolve this interaction from supplied facts or actual user "
                    "replies before generating images or final delivery: " + question
                    for question in required_questions
                ),
            ]
        )
    )
    image_review = any(boundary.reason for boundary in boundaries) and any(
        field.type == "image" for field in specification.outputs
    )
    return FinalizationContract(
        checks=tuple(dict.fromkeys(checks)),
        criteria=criteria,
        advisory_criteria=tuple(
            dict.fromkeys(
                boundary.reason
                for boundary in boundaries
                if boundary.reason
                and not boundary.required
                and boundary.reason not in criteria
            )
        ),
        review_images=image_review,
        pre_render_review=image_review and bool(required_questions),
    )
