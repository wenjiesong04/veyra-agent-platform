"""Compose companion Agents and a Workflow DAG from an ExecutionPlan."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.agent_spec import AgentSpecification
from veyra_agent_platform.contracts.canonical import source_hash
from veyra_agent_platform.contracts.common import SCHEMA_VERSION, new_uuid7
from veyra_agent_platform.contracts.dataflow import types_compatible
from veyra_agent_platform.contracts.execution_plan import (
    ExecutionPlan,
    PlanActor,
    PlanStep,
)
from veyra_agent_platform.contracts.resource_plan import ResourcePlan
from veyra_agent_platform.contracts.semantic_plan import SemanticField
from veyra_agent_platform.contracts.task_structure import TaskIOField
from veyra_agent_platform.contracts.typed_io import (
    ARTIFACT_KINDS,
    TypedField,
    parse_typed_fields,
)
from veyra_agent_platform.local.builder.agent_composer import compose_loop_agent
from veyra_agent_platform.local.builder.workflow_orchestration import (
    WorkflowOrchestration,
)
from veyra_agent_platform.local.projects.layout import attach_default_canvas_note

_EMPTY_PERMISSIONS: dict[str, Any] = {
    "network_hosts": [],
    "tools": [],
    "filesystem_read_roots": [],
    "filesystem_write_roots": [],
    "shell_workspace_only": False,
}


def _flow_id(value: str) -> str:
    """Workflow node ids must match NODE_ID_RE (underscores, no hyphens)."""

    text = re.sub(r"[^a-z0-9_]", "", value.casefold().replace("-", "_"))
    if not text or not text[0].isalpha():
        text = f"n_{text}"
    return text[:63]


def _port_name(value: str) -> str:
    """Names that are valid TypedField slugs and NODE_ID mapping targets."""

    text = re.sub(r"[^a-z0-9]", "", value.casefold())
    if not text or not text[0].isalpha():
        text = f"field{text}"
    return text[:63]


def specification_from_plan(
    plan: ExecutionPlan,
    *,
    actor: PlanActor | None = None,
    requirement: str = "",
) -> AgentSpecification:
    role = actor or (plan.actors[0] if plan.actors else None)
    name = role.name if role is not None else "Agent"
    if requirement and (
        role is None
        or (
            role.id in {"main", "editor"}
            and role.name.casefold()
            in {"assistant", "agent", "main", "advisor", "editor"}
        )
    ):
        from veyra_agent_platform.local.builder.specification import (
            infer_agent_specification,
        )

        legacy = infer_agent_specification(requirement).suggested_name
        if legacy:
            name = legacy
    caps = tuple(role.capabilities) if role is not None else plan.capabilities
    inputs = _actor_inputs(plan, role)
    outputs = _actor_outputs(plan, role)
    return AgentSpecification(
        schema_version=SCHEMA_VERSION,
        goal=(role.brief if role is not None else plan.shape.reason)
        or requirement[:400],
        suggested_name=name,
        description=requirement[:400] or plan.shape.reason,
        inputs=tuple(_semantic(item) for item in inputs),
        outputs=tuple(_semantic(item) for item in outputs),
        responsibilities=_responsibilities(plan, role),
        human_interactions=tuple(
            step.question or step.prompt or step.why
            for step in plan.steps
            if step.kind in {"human_input", "human_approval"}
        ),
        required_capabilities=tuple(
            cap
            for cap in caps
            if cap
            not in {
                "text_generation",
                "vision",
                "structured_output",
                "human_approval",
                "tool_calling",
            }
        ),
        success_criteria=tuple(
            dict.fromkeys(
                [
                    *plan.task.get("constraints", ()),
                    *plan.task.get("success_criteria", ()),
                    *(
                        item
                        for step in plan.steps
                        if step.kind == "verifier"
                        for item in (step.why, *step.checks)
                        if item
                    ),
                ]
            )
        ),
    )


def compose_execution_product(
    plan: ExecutionPlan,
    resolved: ResourcePlan,
    *,
    requirement: str = "",
    entity_tool: dict[str, Any] | None = None,
) -> tuple[AgentSource | None, WorkflowOrchestration | None]:
    """PURE_AGENT returns a loop source. Composite returns orchestration."""

    shape = plan.product_shape
    if shape == "UNSUPPORTED" or plan.shape.status != "decided":
        return None, None
    if shape == "PURE_AGENT":
        spec = specification_from_plan(plan, requirement=requirement)
        return compose_loop_agent(
            spec, resolved, requirement=requirement, state=plan.state
        ), None
    _validate_plan(plan)
    companions: list[AgentSource] = []
    by_id: dict[str, AgentSource] = {}
    for actor in plan.actors:
        spec = specification_from_plan(plan, actor=actor, requirement=requirement)
        source = compose_loop_agent(
            spec, _actor_resources(resolved, actor), requirement=requirement
        )
        payload = source.to_dict()
        payload["name"] = actor.name
        source = AgentSource.from_dict(payload)
        companions.append(source)
        by_id[actor.id] = source
    workflow = _workflow_payload(plan, by_id, requirement, entity_tool=entity_tool)
    flow = tuple(step.kind for step in plan.steps)
    return None, WorkflowOrchestration(
        workflow=workflow,
        companions=tuple(companions),
        flow=flow,
    )


def _responsibilities(plan: ExecutionPlan, actor: PlanActor | None) -> tuple[str, ...]:
    parts = [actor.brief] if actor and actor.brief else []
    parts.extend(
        f"Stage {step.id}: {step.why}"
        for step in plan.steps
        if step.kind == "agent_call" and (actor is None or step.agent == actor.id)
    )
    summary = plan.task.get("summary")
    if isinstance(summary, str) and summary:
        parts.append("Task context: " + summary)
    # A single loop remains autonomous, but must retain the planned method;
    # start/reason/output are the execution shell, not the task procedure.
    task_actors = plan.task.get("actors", ())
    actor_ids = {
        item.get("id")
        for item in task_actors
        if isinstance(item, Mapping)
        and actor is not None
        and (item.get("id") == actor.id or item.get("role") == actor.name)
    }
    for stage in plan.task.get("stages", ()):
        if not isinstance(stage, Mapping):
            continue
        if plan.product_shape != "PURE_AGENT" and stage.get("actor") not in actor_ids:
            continue
        method = str(stage.get("summary") or "").strip()
        if method:
            parts.append(f"Task procedure {stage.get('id')}: {method}")
            if stage.get("source"):
                parts.append("Information source: " + str(stage["source"]))
    return tuple(dict.fromkeys(parts))


def _actor_inputs(
    plan: ExecutionPlan, actor: PlanActor | None
) -> tuple[TaskIOField, ...]:
    if actor is not None and actor.inputs:
        return actor.inputs
    fields = plan.inputs or (TaskIOField(name="request", type="string"),)
    if actor is None or plan.product_shape == "PURE_AGENT":
        return fields
    previous: PlanActor | None = None
    by_id = {item.id: item for item in plan.actors}
    for step in plan.steps:
        if step.kind != "agent_call":
            continue
        if step.agent == actor.id:
            break
        previous = by_id.get(step.agent)
    if previous is None or any(item.name == "context" for item in fields):
        return fields
    outputs = _actor_outputs(plan, previous)
    context = next((item for item in outputs if item.name == "result"), outputs[0])
    return (
        *fields,
        replace(
            context,
            name="context",
            required=False,
            description="Structured output from the preceding Agent stage",
        ),
    )


def _actor_resources(plan: ResourcePlan, actor: PlanActor) -> ResourcePlan:
    """A Workflow's capability union must not grant every child every tool."""
    wanted = set(actor.capabilities)

    def allowed(resource: Any) -> bool:
        if resource.kind in {"tool", "mcp_tool", "skill"}:
            return bool(wanted.intersection(resource.capabilities))
        return True

    return replace(
        plan,
        selected=tuple(item for item in plan.selected if allowed(item)),
        already_bound=tuple(item for item in plan.already_bound if allowed(item)),
        will_bind=tuple(item for item in plan.will_bind if allowed(item)),
        needs_configuration=tuple(
            item for item in plan.needs_configuration if allowed(item)
        ),
    )


def _validate_plan(plan: ExecutionPlan) -> None:
    actors = {item.id for item in plan.actors}
    if len(actors) != len(plan.actors):
        raise ValueError("duplicate execution actor id")
    ids = [_flow_id(step.id) for step in plan.steps]
    if len(set(ids)) != len(ids):
        raise ValueError("execution step ids collide after normalization")
    edges: dict[str, list[str]] = {node_id: [] for node_id in ids}
    for step in plan.steps:
        if step.kind == "agent_call" and step.agent not in actors:
            raise ValueError(f"unknown execution actor: {step.agent}")
        targets = (
            (step.on_true, step.on_false)
            if step.kind in {"condition", "verifier"}
            else (step.on_approved, step.on_rejected)
            if step.kind in {"human_input", "human_approval"}
            else (step.on_next,)
            if step.kind != "output"
            else ()
        )
        for target in targets:
            if not target:
                continue
            target_id = _flow_id(target)
            if target_id not in edges:
                raise ValueError(f"unknown execution target: {target}")
            edges[_flow_id(step.id)].append(target_id)
    active: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in active:
            raise ValueError("Workflow execution plan must be a DAG")
        if node_id in visited:
            return
        active.add(node_id)
        for target in edges[node_id]:
            visit(target)
        active.remove(node_id)
        visited.add(node_id)

    for node_id in edges:
        visit(node_id)


def _semantic(item: TaskIOField) -> SemanticField:
    return SemanticField(
        name=item.name,
        type=item.type,  # type: ignore[arg-type]
        description=item.description,
        multiple=item.multiple,
        required=item.required,
        source=item.source,
    )


def _actor_outputs(
    plan: ExecutionPlan, role: PlanActor | None
) -> tuple[TaskIOField, ...]:
    if role is not None and role.outputs:
        return role.outputs
    if plan.product_shape == "PURE_AGENT":
        return plan.outputs or (TaskIOField(name="result", type="string"),)
    fields = list(plan.outputs)
    if role is not None and "vision" in role.capabilities:
        extras = [
            TaskIOField(name="model-known", type="boolean"),
            TaskIOField(name="result", type="object"),
        ]
        if any("amount" in (step.expression or "") for step in plan.steps):
            extras.append(TaskIOField(name="amount", type="number", required=False))
        return tuple(extras)
    if not fields:
        fields = [TaskIOField(name="result", type="object")]
    if any("amount" in (step.expression or "") for step in plan.steps) and not any(
        item.name == "amount" for item in fields
    ):
        fields.append(TaskIOField(name="amount", type="number", required=False))
    return tuple(fields)


def _field_name(value: str) -> str:
    text = re.sub(r"[^a-z0-9-]", "", value.casefold().replace("_", "-"))
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:63] if text and text[0].isalpha() else "field"


def _output_value(stage_id: str, port: str) -> str:
    return _flow_id(stage_id + "_" + port)


def _value_mappings(
    plan: ExecutionPlan, agents: dict[str, AgentSource]
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, dict[str, str]],
    dict[str, dict[str, str]],
    dict[str, dict[str, Any]],
]:
    """Resolve semantic sources to real values without serializing typed payloads."""
    top_fields = parse_typed_fields(
        _io_wire(plan.inputs) or {"request": "string"}, "inputs"
    )
    input_refs = {item.name: _port_name(item.name) for item in plan.inputs}
    if not input_refs:
        input_refs = {"request": "request"}
    if len(set(input_refs.values())) != len(input_refs):
        raise ValueError("Workflow input field names collide after normalization")
    semantic: dict[str, tuple[str, TypedField]] = {}
    occupied: set[str] = set(top_fields)
    call_inputs: dict[str, dict[str, str]] = {}
    call_outputs: dict[str, dict[str, str]] = {}
    aliases: dict[str, dict[str, str]] = {}
    humans: dict[str, dict[str, Any]] = {}
    actor_by_id = {actor.id: actor for actor in plan.actors}
    legacy = not any(
        actor.inputs or actor.outputs for actor in plan.actors
    ) and not any(step.input_sources for step in plan.steps)
    final_fields = parse_typed_fields(
        _io_wire(plan.outputs) or {"result": "object"}, "outputs"
    )
    final_sources: dict[str, str] = {}
    for item in plan.outputs:
        target = _port_name(item.name)
        if "." in item.source and re.fullmatch(
            r"[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+", item.source
        ):
            stage, port = item.source.split(".", 1)
            final_sources[target] = f"{_flow_id(stage)}.{_field_name(port)}"
        else:
            matching = [
                (step.id, name)
                for step in plan.steps
                if step.kind == "agent_call"
                for name, field in agents[step.agent].outputs.items()
                if _field_name(item.name) == name
                and types_compatible(field, final_fields[target])
            ]
            if matching:
                stage, name = matching[-1]
                final_sources[target] = f"{stage}.{name}"
    previous: tuple[str, AgentSource] | None = None
    for step in plan.steps:
        if step.kind == "human_input":
            fields: dict[str, Any] = {}
            for name, kind in (step.expected_schema or {"reply": "string"}).items():
                value = _port_name(step.id + name)
                if value in occupied:
                    raise ValueError("HumanInput value id collides with existing value")
                occupied.add(value)
                descriptor = _io_wire(
                    (TaskIOField(name=value, type=kind, description=name),)
                )[value]
                fields[value] = descriptor
                field = parse_typed_fields({value: descriptor}, "human inputs")[value]
                semantic[f"{step.id}.{name}"] = (value, field)
                semantic[f"{step.id}.{_field_name(name)}"] = (value, field)
            humans[step.id] = fields
            continue
        if step.kind != "agent_call":
            continue
        source = agents[step.agent]
        explicit = {
            _field_name(key): value for key, value in (step.input_sources or {}).items()
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
                if requested_source.startswith("input."):
                    raw = requested_source.removeprefix("input.")
                    input_value = input_refs.get(raw)
                    if input_value:
                        found = (input_value, top_fields[input_value])
                else:
                    found = semantic.get(requested_source)
                    if found is None and "." in requested_source:
                        stage, port = requested_source.split(".", 1)
                        found = semantic.get(f"{_flow_id(stage)}.{_field_name(port)}")
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
                        if _field_name(raw) == name
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
            _field_name(item.name): item.name
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
                aliases.setdefault(step.id, {})[_flow_id(name)] = value
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
        previous = (step.id, source)
    for reference in final_sources.values():
        if reference not in semantic and not reference.startswith("input."):
            raise ValueError(f"unknown final Workflow output source: {reference}")
    return call_inputs, call_outputs, aliases, humans


def _workflow_payload(
    plan: ExecutionPlan,
    agents: dict[str, AgentSource],
    requirement: str,
    *,
    entity_tool: dict[str, Any] | None,
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    transitions: list[dict[str, str]] = []
    positions: dict[str, dict[str, int]] = {}
    labels: dict[str, str] = {}
    checks: list[str] = []
    call_inputs, call_outputs, aliases, human_fields = _value_mappings(plan, agents)
    for column, step in enumerate(plan.steps):
        node = _node(step, agents, plan, entity_tool=entity_tool)
        if step.kind == "agent_call":
            node["input_mapping"] = call_inputs[step.id]
            node["output_mapping"] = call_outputs[step.id]
        if step.kind == "human_input":
            node["inputs"] = human_fields[step.id]
        nodes.append(node)
        node_id = _flow_id(step.id)
        positions[node_id] = {"x": 80 + column * 220, "y": 80}
        labels[node_id] = step.id.replace("-", " ").replace("_", " ")
        if step.kind == "verifier":
            checks = list(step.checks)
        _emit_edges(step, transitions)
        if step.id in aliases:
            alias_id = _flow_id(step.id + "_outputs")
            if alias_id in {_flow_id(item.id) for item in plan.steps}:
                raise ValueError("output alias node id collides with task stage")
            for edge in transitions:
                if edge["from"] == node_id:
                    edge["from"] = alias_id
            transitions.append({"from": node_id, "port": "next", "to": alias_id})
            nodes.append(
                {
                    "id": alias_id,
                    "component_type": "Transform",
                    "mapping": {
                        name: "{{" + value + "}}"
                        for name, value in aliases[step.id].items()
                    },
                }
            )
            positions[alias_id] = {"x": 80 + column * 220 + 110, "y": 220}
    inputs = _io_wire(plan.inputs) or {"request": "string"}
    outputs = _io_wire(plan.outputs) or {"result": "object"}
    output_name = next(iter(outputs))
    for node in nodes:
        if node.get("component_type") == "Output":
            node["output_name"] = output_name
    permissions = dict(_EMPTY_PERMISSIONS)
    for source in agents.values():
        permissions["tools"] = list(
            dict.fromkeys([*permissions["tools"], *source.permissions.tools])
        )
        permissions["network_hosts"] = list(
            dict.fromkeys(
                [*permissions["network_hosts"], *source.permissions.network_hosts]
            )
        )
        permissions["filesystem_read_roots"] = list(
            dict.fromkeys(
                [
                    *permissions["filesystem_read_roots"],
                    *source.permissions.filesystem_read_roots,
                ]
            )
        )
        permissions["filesystem_write_roots"] = list(
            dict.fromkeys(
                [
                    *permissions["filesystem_write_roots"],
                    *source.permissions.filesystem_write_roots,
                ]
            )
        )
        if source.permissions.shell_workspace_only:
            permissions["shell_workspace_only"] = True
    if entity_tool:
        permissions["tools"] = list(
            dict.fromkeys([*permissions["tools"], entity_tool["resource_id"]])
        )
    slug = "generated-workflow"
    # Review pins protect the candidate contents. Apply remaps these placeholders
    # to newly committed version IDs and revalidates the actual immutable pins.
    lock: dict[str, str] = {
        f"{source.agent_id}@{source.agent_id}": source_hash(source.to_dict())
        for source in agents.values()
    }
    if entity_tool and entity_tool.get("content_hash"):
        lock[entity_tool["reference"]] = str(entity_tool["content_hash"])
    return {
        "schema_version": "1.0",
        "component_type": "Workflow",
        "workflow_id": new_uuid7(),
        "slug": slug,
        "name": (plan.task.get("goal") or "Generated Workflow")[:80],
        "description": requirement[:400] or plan.shape.reason,
        "version": "1.0.0",
        "inputs": inputs,
        "outputs": outputs,
        "nodes": nodes,
        "transitions": transitions,
        "data_edges": [],
        "extensions": {
            "veyra": {
                "permissions": permissions,
                "verification": {
                    "required": bool(checks),
                    "checks": checks,
                },
            }
        },
        "ui": attach_default_canvas_note(
            {"positions": positions, "labels": labels},
            requirement[:180] or plan.shape.reason,
        ),
        "lock": lock,
        "companion_agent_ids": [item.agent_id for item in agents.values()],
    }


def _io_wire(fields: tuple[TaskIOField, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in fields:
        name = _port_name(item.name)
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


def _node(
    step: PlanStep,
    agents: dict[str, AgentSource],
    plan: ExecutionPlan,
    *,
    entity_tool: dict[str, Any] | None,
) -> dict[str, Any]:
    node_id = _flow_id(step.id)
    if step.kind == "start":
        return {"id": node_id, "component_type": "Start"}
    if step.kind == "output":
        return {
            "id": node_id,
            "component_type": "Output",
            "output_name": "result",
        }
    if step.kind == "agent_call":
        source = agents.get(step.agent)
        if source is None:
            raise ValueError("agent_call requires a companion Agent")
        inputs = {name: _port_name(name) for name in source.inputs} or {
            "request": "request"
        }
        outputs = {name: _flow_id(name) for name in source.outputs} or {
            "result": "result"
        }
        return {
            "id": node_id,
            "component_type": "AgentCall",
            "agent_ref": f"{source.agent_id}@{source.agent_id}",
            "input_mapping": inputs,
            "output_mapping": outputs,
        }
    if step.kind == "condition":
        return {
            "id": node_id,
            "component_type": "Condition",
            "expression": step.expression,
        }
    if step.kind == "human_input":
        expected = dict(step.expected_schema or {})
        schema_inputs: dict[str, dict[str, object]] = {
            _port_name(name): (
                {"type": kind, "required": True}
                if kind != "image"
                else {
                    "type": "artifact",
                    "artifact_kind": "image",
                    "required": True,
                }
            )
            for name, kind in expected.items()
        } or {"reply": {"type": "string", "required": True}}
        return {
            "id": node_id,
            "component_type": "HumanApproval",
            "prompt": step.question or step.why,
            "review": "input",
            "inputs": schema_inputs,
        }
    if step.kind == "human_approval":
        return {
            "id": node_id,
            "component_type": "HumanApproval",
            "prompt": step.prompt or step.why,
            "review": "approval",
        }
    if step.kind == "state_write":
        if entity_tool is None:
            raise ValueError("state_write requires a bound entity tool")
        return {
            "id": node_id,
            "component_type": "Tool",
            "uses": entity_tool["reference"],
        }
    if step.kind == "verifier":
        return {
            "id": node_id,
            "component_type": "Verifier",
            "checks": list(step.checks) or ["output.not_empty"],
        }
    if step.kind == "transform":
        mapping = {"status": "active"}
        if step.entity:
            mapping["entity_type"] = step.entity
        return {
            "id": node_id,
            "component_type": "Transform",
            "mapping": mapping,
        }
    raise ValueError(f"unsupported execution step: {step.kind}")


def _emit_edges(step: PlanStep, transitions: list[dict[str, str]]) -> None:
    source = _flow_id(step.id)
    if step.kind == "output":
        return
    if step.kind == "condition":
        if step.on_true:
            transitions.append(
                {"from": source, "port": "true", "to": _flow_id(step.on_true)}
            )
        if step.on_false:
            transitions.append(
                {"from": source, "port": "false", "to": _flow_id(step.on_false)}
            )
        return
    if step.kind in {"human_approval", "human_input"}:
        if step.on_approved:
            transitions.append(
                {
                    "from": source,
                    "port": "approved",
                    "to": _flow_id(step.on_approved),
                }
            )
        if step.on_rejected:
            transitions.append(
                {
                    "from": source,
                    "port": "rejected",
                    "to": _flow_id(step.on_rejected),
                }
            )
        return
    if step.kind == "verifier":
        passed = step.on_true or step.on_next or "output"
        failed = step.on_false or "output"
        transitions.append({"from": source, "port": "passed", "to": _flow_id(passed)})
        transitions.append({"from": source, "port": "failed", "to": _flow_id(failed)})
        return
    if step.on_next:
        transitions.append(
            {"from": source, "port": "next", "to": _flow_id(step.on_next)}
        )
