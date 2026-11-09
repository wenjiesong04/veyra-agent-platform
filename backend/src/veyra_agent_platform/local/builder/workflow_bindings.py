"""Compile all Workflow value bindings before emitting graph nodes."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, TypeVar

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.condition import parse_condition_expression
from veyra_agent_platform.contracts.dataflow import types_compatible
from veyra_agent_platform.contracts.execution_plan import ExecutionPlan, PlanStep
from veyra_agent_platform.contracts.task_structure import TaskIOField
from veyra_agent_platform.contracts.typed_io import (
    ARTIFACT_KINDS,
    TypedField,
    parse_typed_fields,
)
from veyra_agent_platform.contracts.verification import (
    parse_verifier_check as parse_verifier_check,
)

from .task_bindings import resolve_declared_reference

_Value = TypeVar("_Value")


@dataclass(frozen=True)
class WorkflowValueBindings:
    call_inputs: dict[str, dict[str, str]]
    call_outputs: dict[str, dict[str, str]]
    aliases: dict[str, dict[str, str]]
    human_fields: dict[str, dict[str, Any]]
    verifiers: dict[str, tuple[dict[str, str], list[str]]]
    conditions: dict[str, str]
    approval_reviews: dict[str, dict[str, str]] = field(default_factory=dict)


def workflow_node_id(value: str) -> str:
    """Workflow node ids must match NODE_ID_RE (underscores, no hyphens)."""

    text = re.sub(r"[^a-z0-9_]", "", value.casefold().replace("-", "_"))
    if not text or not text[0].isalpha():
        text = f"n_{text}"
    return text[:63]


def workflow_io_name(value: str) -> str:
    """Names that are valid TypedField slugs and NODE_ID mapping targets."""

    text = re.sub(r"[^a-z0-9]", "", value.casefold())
    if not text or not text[0].isalpha():
        text = f"field{text}"
    return text[:63]


def workflow_io_fields(fields: tuple[TaskIOField, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in fields:
        name = workflow_io_name(item.name)
        payload: dict[str, Any] = {
            "type": item.type
            if item.type
            not in {"image", "pdf", "document", "file", "audio", "video", "collection"}
            else "artifact",
            "required": item.required,
        }
        if item.type in {
            "image",
            "pdf",
            "document",
            "file",
            "audio",
            "video",
            "collection",
        }:
            payload["artifact_kind"] = item.type
        if item.multiple:
            payload["multiple"] = True
        if item.description:
            payload["description"] = item.description
        if (
            item.required
            and not item.multiple
            and not item.description
            and item.type not in ARTIFACT_KINDS
        ):
            result[name] = item.type
        else:
            result[name] = payload
    return result


def actor_port_name(value: str) -> str:
    text = re.sub(r"[^a-z0-9-]", "", value.casefold().replace("_", "-"))
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:63] if text and text[0].isalpha() else "field"


def _output_value(stage_id: str, port: str) -> str:
    return workflow_node_id(stage_id + "_" + port)


def compile_workflow_bindings(
    plan: ExecutionPlan, agents: dict[str, AgentSource]
) -> WorkflowValueBindings:
    """Resolve semantic sources to real values without serializing typed payloads."""
    top_fields = parse_typed_fields(
        workflow_io_fields(plan.inputs) or {"request": "string"}, "inputs"
    )
    input_refs = {item.name: workflow_io_name(item.name) for item in plan.inputs}
    if not input_refs:
        input_refs = {"request": "request"}
    if len(set(input_refs.values())) != len(input_refs):
        raise ValueError("Workflow input field names collide after normalization")
    canonical_inputs = {
        actor_port_name(raw): value for raw, value in input_refs.items()
    }
    available_inputs = {
        name: (value, top_fields[value])
        for name, value in {**input_refs, **canonical_inputs}.items()
    }
    semantic: dict[str, tuple[str, TypedField]] = {}
    occupied: set[str] = set(top_fields)
    call_inputs: dict[str, dict[str, str]] = {}
    call_outputs: dict[str, dict[str, str]] = {}
    aliases: dict[str, dict[str, str]] = {}
    humans: dict[str, dict[str, Any]] = {}
    verifiers: dict[str, tuple[dict[str, str], list[str]]] = {}
    conditions: dict[str, str] = {}
    approval_reviews: dict[str, dict[str, str]] = {}
    previous_outputs: dict[str, str] = {}
    actor_by_id = {actor.id: actor for actor in plan.actors}
    legacy = not any(
        actor.inputs or actor.outputs for actor in plan.actors
    ) and not any(step.input_sources for step in plan.steps)
    final_fields = parse_typed_fields(
        workflow_io_fields(plan.outputs) or {"result": "object"}, "outputs"
    )
    final_sources: dict[str, str] = {}
    for item in plan.outputs:
        target = workflow_io_name(item.name)
        if "." in item.source and re.fullmatch(
            r"[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+", item.source
        ):
            stage, port = item.source.split(".", 1)
            final_sources[target] = f"{workflow_node_id(stage)}.{actor_port_name(port)}"
        else:
            matching = [
                (step.id, name)
                for step in plan.steps
                if step.kind == "agent_call"
                for name, field in agents[step.agent].outputs.items()
                if actor_port_name(item.name) == name
                and types_compatible(field, final_fields[target])
            ]
            if matching:
                stage, name = matching[-1]
                final_sources[target] = f"{stage}.{name}"
    previous: tuple[str, AgentSource] | None = None
    for step in plan.steps:
        if step.kind == "human_approval":
            review: dict[str, str] = {}
            for name, reference in (step.input_sources or {}).items():
                resolved_review = _resolve(reference, semantic, available_inputs)
                if resolved_review is None:
                    raise ValueError(
                        f"unknown or unavailable approval input source: {reference}"
                    )
                review[name] = resolved_review[0]
            approval_reviews[step.id] = review
            continue
        if step.kind == "condition" and not legacy:
            conditions[step.id] = bind_condition(
                step.expression,
                {name: value[0] for name, value in semantic.items()},
                previous_outputs,
                {**input_refs, **canonical_inputs},
            )
            continue
        if step.kind == "verifier" and not legacy:
            verifiers[step.id] = bind_verifier(
                step,
                {name: value[0] for name, value in semantic.items()},
                previous_outputs,
                {**input_refs, **canonical_inputs},
            )
            continue
        if step.kind == "human_input":
            fields: dict[str, Any] = {}
            for name, kind in (step.expected_schema or {"reply": "string"}).items():
                value = workflow_io_name(step.id + name)
                if value in occupied:
                    raise ValueError("HumanInput value id collides with existing value")
                occupied.add(value)
                descriptor = workflow_io_fields(
                    (TaskIOField(name=value, type=kind, description=name),)
                )[value]
                fields[value] = descriptor
                field = parse_typed_fields({value: descriptor}, "human inputs")[value]
                semantic[f"{step.id}.{name}"] = (value, field)
                semantic[f"{step.id}.{actor_port_name(name)}"] = (value, field)
            humans[step.id] = fields
            continue
        if step.kind != "agent_call":
            continue
        source = agents[step.agent]
        explicit = {
            actor_port_name(key): value
            for key, value in (step.input_sources or {}).items()
        }
        if len(explicit) != len(step.input_sources or {}):
            raise ValueError("input source target names collide")
        if set(explicit) - set(source.inputs):
            raise ValueError("input source references an unknown actor input port")
        inputs: dict[str, str] = {}
        for name, field in source.inputs.items():
            requested_source = explicit.get(name)
            found: tuple[str, TypedField] | None = None
            if requested_source:
                found = _resolve(requested_source, semantic, available_inputs)
                if found is None:
                    raise ValueError(
                        "unknown or unavailable semantic input source: "
                        f"{requested_source}"
                    )
            else:
                top_name = next(
                    (
                        value
                        for raw, value in input_refs.items()
                        if actor_port_name(raw) == name
                    ),
                    None,
                )
                if top_name:
                    found = (top_name, top_fields[top_name])
                elif legacy and name == "context" and previous:
                    prior_step, prior_source = previous
                    port = (
                        "result"
                        if "result" in prior_source.outputs
                        else next(iter(prior_source.outputs))
                    )
                    found = semantic[f"{prior_step}.{port}"]
                elif field.required:
                    raise ValueError(
                        f"required actor input has no source: {step.id}.{name}"
                    )
            if found:
                value, provided = found
                if not types_compatible(provided, field):
                    raise ValueError(
                        f"incompatible semantic input source: {step.id}.{name}"
                    )
                inputs[name] = value
        outputs: dict[str, str] = {}
        raw_outputs = {
            actor_port_name(item.name): item.name
            for item in actor_by_id[step.agent].outputs
        }
        for name, field in source.outputs.items():
            value = _output_value(step.id, name)
            if value in occupied:
                raise ValueError("Agent output value id collides after normalization")
            occupied.add(value)
            outputs[name] = value
            semantic[f"{step.id}.{name}"] = (value, field)
            semantic[f"{step.id}.{raw_outputs.get(name, name)}"] = (value, field)
            if legacy:
                aliases.setdefault(step.id, {})[workflow_node_id(name)] = value
            for target, reference in final_sources.items():
                if (
                    reference == f"{step.id}.{name}"
                    or reference == f"{step.id}.{raw_outputs.get(name, name)}"
                ):
                    if not types_compatible(field, final_fields[target]):
                        raise ValueError("incompatible final Workflow output source")
                    aliases.setdefault(step.id, {})[target] = value
        call_inputs[step.id] = inputs
        call_outputs[step.id] = outputs
        previous_outputs = dict(outputs)
        previous = (step.id, source)
    for reference in final_sources.values():
        if reference not in semantic and not reference.startswith("input."):
            raise ValueError(f"unknown final Workflow output source: {reference}")
    return WorkflowValueBindings(
        call_inputs,
        call_outputs,
        aliases,
        humans,
        verifiers,
        conditions,
        approval_reviews,
    )


def bind_condition(
    expression: str,
    semantic: Mapping[str, str],
    previous_outputs: Mapping[str, str],
    task_inputs: Mapping[str, str],
) -> str:
    """Resolve the same declared namespaces used by calls and checks."""
    parsed = parse_condition_expression(expression)
    parts = parsed.path
    value = None
    suffix = parts[1:]
    if len(parts) > 1:
        value = _resolve(".".join(parts[:2]), semantic, task_inputs)
        if value is not None:
            suffix = parts[2:]
        elif parts[0] in {"input", "inputs"}:
            raise ValueError(
                f"unknown or unavailable condition subject: {parsed.field}"
            )
    if value is None:
        value = task_inputs.get(parts[0]) or task_inputs.get(actor_port_name(parts[0]))
    if value is None:
        value = previous_outputs.get(actor_port_name(parts[0]))
    if value is None:
        raise ValueError(f"unknown or unavailable condition subject: {parsed.field}")
    field = ".".join((value, *suffix))
    return replace(parsed, field=field).to_text()


def bind_verifier(
    step: PlanStep,
    semantic: dict[str, str],
    previous_outputs: dict[str, str],
    task_inputs: dict[str, str],
) -> tuple[dict[str, str], list[str]]:
    """Only producer ports already available at this stage can satisfy a check."""
    mapping = dict(previous_outputs)
    for name, reference in (step.input_sources or {}).items():
        target = name.casefold().replace("_", "-")
        value = _resolve(reference, semantic, task_inputs)
        if value is None:
            raise ValueError(f"unavailable verifier input source: {reference}")
        mapping[target] = value
    checks: list[str] = []
    for check in step.checks or ("output.not_empty",):
        parse_verifier_check(check)
        if check in {"output.not_empty", "schema_valid"}:
            if check == "schema_valid" and "result" not in mapping:
                raise ValueError("schema_valid needs a declared verifier result input")
            checks.append(check)
            continue
        if check.startswith(("required_fields:", "artifact_exists:")):
            kind, field = check.split(":", 1)
            if "." in field:
                value = _resolve(field, semantic, task_inputs)
                target = field.split(".", 1)[1].casefold().replace("_", "-")
                if value is None:
                    raise ValueError(f"unavailable verifier check source: {field}")
                if target in mapping and mapping[target] != value:
                    raise ValueError(
                        "ambiguous verifier check; use explicit input_sources"
                    )
                mapping[target] = value
            else:
                target = field.casefold().replace("_", "-")
                if target not in mapping:
                    raise ValueError(f"undeclared verifier check field: {field}")
            checks.append(f"{kind}:{target}")
            continue
        if check.startswith("constraint_match:"):
            condition = parse_condition_expression(check.split(":", 1)[1])
            if condition.root not in mapping:
                raise ValueError(
                    f"undeclared verifier condition field: {condition.field}"
                )
            checks.append(check)
            continue
        raise ValueError(f"unsupported verifier check: {check}")
    if not mapping:
        raise ValueError("intermediate verification requires declared producer outputs")
    return mapping, checks


def _resolve(
    reference: str, semantic: Mapping[str, _Value], task_inputs: Mapping[str, _Value]
) -> _Value | None:
    return resolve_declared_reference(
        reference, task_inputs=task_inputs, producer_outputs=semantic
    )
