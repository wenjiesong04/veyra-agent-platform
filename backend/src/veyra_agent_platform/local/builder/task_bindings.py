"""Validate model-proposed task references before resource grounding/composition."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TypeVar

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.task_structure import TaskIOField, TaskStructure

from .product_shape import decide_product_shape

_REFERENCE = re.compile(r"([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)\Z")
_BARE_INPUT = re.compile(r"[A-Za-z0-9_-]+\Z")
_Value = TypeVar("_Value")


def _name(value: str) -> str:
    return value.casefold().replace("_", "-")


def resolve_declared_reference(
    reference: str,
    *,
    task_inputs: Mapping[str, _Value],
    producer_outputs: Mapping[str, _Value],
) -> _Value | None:
    """Resolve only supplied symbols, sharing planning and compilation semantics.

    A bare name denotes a declared task input. Qualified names denote
    ``input(s).port`` or a supplied ``stage.port`` producer. Case and underscore
    aliases are deterministic; aliases of distinct values are rejected.
    """
    inputs = _declared_symbols(task_inputs, qualified=False)
    outputs = _declared_symbols(producer_outputs, qualified=True)
    match = _REFERENCE.fullmatch(reference)
    if match is not None:
        owner, port = (_name(part) for part in match.groups())
        if owner in {"input", "inputs"}:
            return inputs.get(port)
        return outputs.get(f"{owner}.{port}")
    if _BARE_INPUT.fullmatch(reference):
        return inputs.get(_name(reference))
    return None


def _declared_symbols(
    symbols: Mapping[str, _Value], *, qualified: bool
) -> dict[str, _Value]:
    result: dict[str, _Value] = {}
    for name, value in symbols.items():
        match = _REFERENCE.fullmatch(name) if qualified else _BARE_INPUT.fullmatch(name)
        if match is None:
            # Metadata or non-reference aliases never become executable names.
            continue
        key = ".".join(_name(part) for part in name.split("."))
        if key in result and result[key] != value:
            raise ContractValidationError("Declared reference aliases collide")
        result[key] = value
    return result


def _ports(fields: tuple[TaskIOField, ...], label: str) -> set[str]:
    values = [_name(field.name) for field in fields]
    if len(set(values)) != len(values):
        raise ContractValidationError(f"{label} field names collide")
    return set(values)


def validate_task_bindings(structure: TaskStructure) -> None:
    """Only resolve declared names; do not invent missing ports or fallback data."""
    actors = {actor.id: actor for actor in structure.actors}
    if len(actors) != len(structure.actors):
        raise ContractValidationError("Task actor IDs must be unique")
    stages = {_name(stage.id): stage for stage in structure.stages}
    if len(stages) != len(structure.stages):
        raise ContractValidationError("Task stage IDs collide")
    inputs = _ports(structure.inputs, "Task input")
    _ports(structure.outputs, "Task output")
    for actor_row in structure.actors:
        _ports(actor_row.inputs, f"Actor {actor_row.id} input")
        _ports(actor_row.outputs, f"Actor {actor_row.id} output")
    external = decide_product_shape(structure).shape != "PURE_AGENT"
    human_outputs = {
        _name(boundary.stage): {_name(key) for key in boundary.expected_schema or {}}
        for boundary in structure.execution_boundaries
        if boundary.kind == "human_input"
    }
    producer_ports = {
        stage_id: (
            _ports(actors[stage.actor].outputs, f"Actor {stage.actor} output")
            if stage.actor in actors
            else human_outputs.get(stage_id, set())
        )
        for stage_id, stage in stages.items()
    }

    def available_producers(seen: set[str]) -> dict[str, str]:
        return {
            f"{owner}.{port}": f"{owner}.{port}"
            for owner in seen
            for port in producer_ports.get(owner, set())
        }

    def candidates(seen: set[str]) -> str:
        declared = ", ".join(f"input.{name}" for name in sorted(inputs)[:4]) or "none"
        produced = ", ".join(sorted(available_producers(seen))[:4]) or "none yet"
        return (
            ". Declared task inputs: "
            + declared
            + ". Available producer outputs: "
            + produced
        )

    def check(reference: str, seen: set[str], location: str) -> None:
        if (
            resolve_declared_reference(
                reference,
                task_inputs={name: name for name in inputs},
                producer_outputs=available_producers(seen),
            )
            is not None
        ):
            return
        match = _REFERENCE.fullmatch(reference)
        if match is None:
            raise ContractValidationError(
                f"{location} needs a declared input or stage.port reference"
                + candidates(seen)
            )
        owner, port = match.groups()
        normalized_port = _name(port)
        if _name(owner) in {"input", "inputs"}:
            if normalized_port not in inputs:
                raise ContractValidationError(
                    f"{location} references undeclared task input {port}"
                    + candidates(seen)
                )
            return
        normalized_owner = _name(owner)
        stage = stages.get(normalized_owner)
        if stage is None:
            raise ContractValidationError(
                f"{location} references unknown stage {owner}" + candidates(seen)
            )
        if normalized_owner not in seen:
            raise ContractValidationError(
                f"{location} references unavailable stage {owner}" + candidates(seen)
            )
        if not external:
            # Working notes inside one autonomous loop are not external ports.
            return
        available = producer_ports[normalized_owner]
        if normalized_port not in available:
            raise ContractValidationError(
                f"{location} references undeclared output {owner}.{port}; "
                "declare the producer's typed output and retain the task duty. "
                "Available outputs: "
                + (", ".join(sorted(available)) or "none declared")
                + candidates(seen)
            )

    seen: set[str] = set()
    for stage in structure.stages:
        if stage.actor and stage.actor not in actors:
            raise ContractValidationError(f"Stage {stage.id} references unknown actor")
        stage_actor = actors.get(stage.actor)
        sources = stage.input_sources or {}
        if stage_actor is not None:
            targets = [_name(key) for key in sources]
            if len(set(targets)) != len(targets):
                raise ContractValidationError(f"Stage {stage.id} input targets collide")
            unknown = set(targets) - _ports(
                stage_actor.inputs, f"Actor {stage_actor.id} input"
            )
            if unknown:
                raise ContractValidationError(
                    f"Stage {stage.id} references undeclared actor input"
                    "; declared actor inputs: "
                    + ", ".join(sorted(_ports(stage_actor.inputs, "Actor input")))
                )
        for target, reference in sources.items():
            check(reference, seen, f"Stage {stage.id} input {target}")
        seen.add(_name(stage.id))
    for output in structure.outputs:
        if output.source and _REFERENCE.fullmatch(output.source):
            check(output.source, seen, f"Task output {output.name}")
