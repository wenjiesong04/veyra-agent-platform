"""Compose companion Agents and a Workflow DAG from an ExecutionPlan."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from veyra_agent_platform.contracts.agent import DEFAULT_MAX_TURNS, AgentSource
from veyra_agent_platform.contracts.agent_spec import AgentSpecification
from veyra_agent_platform.contracts.canonical import source_hash
from veyra_agent_platform.contracts.common import SCHEMA_VERSION, new_uuid7, thaw_json
from veyra_agent_platform.contracts.execution_plan import (
    ExecutionPlan,
    PlanActor,
    PlanStep,
)
from veyra_agent_platform.contracts.resource_plan import ResourcePlan
from veyra_agent_platform.contracts.semantic_plan import SemanticField
from veyra_agent_platform.contracts.task_structure import (
    StateRequirement,
    TaskIOField,
    TaskStructure,
)
from veyra_agent_platform.local.builder.agent_composer import compose_loop_agent
from veyra_agent_platform.local.builder.finalization_composer import actor_finalization
from veyra_agent_platform.local.builder.product_shape import (
    native_loop_state,
    stage_key,
)
from veyra_agent_platform.local.builder.workflow_bindings import (
    compile_workflow_bindings,
    workflow_io_fields,
    workflow_io_name,
    workflow_node_id,
)
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
        human_interactions=_native_questions(plan, role),
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
    actor_resources: Mapping[str, ResourcePlan] | None = None,
    initial_model_turns: int = DEFAULT_MAX_TURNS,
) -> tuple[AgentSource | None, WorkflowOrchestration | None]:
    """PURE_AGENT returns a loop source. Composite returns orchestration."""

    shape = plan.product_shape
    write_roots = tuple(plan.task.get("filesystem_write_roots") or ())
    if shape == "UNSUPPORTED" or plan.shape.status != "decided":
        return None, None
    if shape == "PURE_AGENT":
        spec = specification_from_plan(plan, requirement=requirement)
        return compose_loop_agent(
            spec,
            resolved,
            requirement=requirement,
            state=plan.state,
            filesystem_write_roots=write_roots,
            protect_input_files=bool(plan.task.get("protect_input_files")),
            protected_input_fields=tuple(plan.task.get("protected_input_fields") or ()),
            finalization=actor_finalization(plan, spec),
            initial_model_turns=initial_model_turns,
        ), None
    _validate_plan(plan)
    companions: list[AgentSource] = []
    by_id: dict[str, AgentSource] = {}
    for actor in plan.actors:
        spec = specification_from_plan(plan, actor=actor, requirement=requirement)
        source = compose_loop_agent(
            spec,
            actor_resources[actor.id]
            if actor_resources is not None
            else _actor_resources(resolved, actor),
            requirement=requirement,
            state=_actor_state(plan, actor),
            filesystem_write_roots=write_roots,
            protect_input_files=bool(plan.task.get("protect_input_files")),
            finalization=actor_finalization(plan, spec, actor),
            initial_model_turns=initial_model_turns,
        )
        payload = source.to_dict()
        payload["name"] = actor.name
        source = AgentSource.from_dict(payload)
        companions.append(source)
        by_id[actor.id] = source
    workflow = _workflow_payload(
        plan,
        by_id,
        requirement,
        entity_tool=entity_tool
        if any(step.kind == "state_write" for step in plan.steps)
        else None,
    )
    flow = tuple(step.kind for step in plan.steps)
    return None, WorkflowOrchestration(
        workflow=workflow,
        companions=tuple(companions),
        flow=flow,
    )


def _native_questions(plan: ExecutionPlan, actor: PlanActor | None) -> tuple[str, ...]:
    owned_stages = {
        stage_key(str(stage.get("id") or ""))
        for stage in plan.task.get("stages", ())
        if isinstance(stage, Mapping) and actor and stage.get("actor") == actor.id
    }
    return tuple(
        dict.fromkeys(
            (
                "Optional follow-up, not a delivery prerequisite: "
                if boundary.get("required") is False
                else ""
            )
            + str(boundary.get("question") or boundary.get("reason") or "")
            for boundary in plan.task.get("execution_boundaries", ())
            if isinstance(boundary, Mapping)
            and boundary.get("kind") == "human_input"
            and (
                plan.product_shape == "PURE_AGENT"
                or stage_key(str(boundary.get("stage") or "")) in owned_stages
            )
        )
    )


def _actor_state(plan: ExecutionPlan, actor: PlanActor) -> StateRequirement | None:
    if plan.state is None:
        return None
    structure = TaskStructure.from_dict(thaw_json(plan.task))
    return (
        plan.state
        if any(
            boundary.kind == "state"
            and boundary.entity == plan.state.entity
            and native_loop_state(structure, boundary.stage)
            and any(
                stage_key(stage.id) == stage_key(boundary.stage)
                and stage.actor == actor.id
                for stage in structure.stages
            )
            for boundary in structure.execution_boundaries
        )
        else None
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
    ids = [workflow_node_id(step.id) for step in plan.steps]
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
            if step.kind not in {"output", "stop"}
            else ()
        )
        for target in targets:
            if not target:
                continue
            target_id = workflow_node_id(target)
            if target_id not in edges:
                raise ValueError(f"unknown execution target: {target}")
            edges[workflow_node_id(step.id)].append(target_id)
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
    bindings = compile_workflow_bindings(plan, agents)
    for column, step in enumerate(plan.steps):
        node = _node(step, agents, plan, entity_tool=entity_tool)
        if step.kind == "human_approval" and bindings.approval_reviews.get(step.id):
            material = "\n\n".join(
                f"{name}:\n{{{{{value}}}}}"
                for name, value in bindings.approval_reviews[step.id].items()
            )
            node["prompt"] = str(node["prompt"]) + "\n\n" + material
        if step.kind == "agent_call":
            node["input_mapping"] = bindings.call_inputs[step.id]
            node["output_mapping"] = bindings.call_outputs[step.id]
        if step.kind == "human_input":
            node["inputs"] = bindings.human_fields[step.id]
        if step.id in bindings.verifiers:
            node["input_mapping"], node["checks"] = bindings.verifiers[step.id]
        if step.id in bindings.conditions:
            node["expression"] = bindings.conditions[step.id]
        nodes.append(node)
        node_id = workflow_node_id(step.id)
        positions[node_id] = {"x": 80 + column * 220, "y": 80}
        labels[node_id] = step.id.replace("-", " ").replace("_", " ")
        if step.kind == "verifier":
            checks.extend(node["checks"])
        _emit_edges(step, transitions)
        if step.id in bindings.aliases:
            alias_id = workflow_node_id(step.id + "_outputs")
            if alias_id in {workflow_node_id(item.id) for item in plan.steps}:
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
                        for name, value in bindings.aliases[step.id].items()
                    },
                }
            )
            positions[alias_id] = {"x": 80 + column * 220 + 110, "y": 220}
    inputs = workflow_io_fields(plan.inputs) or {"request": "string"}
    outputs = workflow_io_fields(plan.outputs) or {"result": "object"}
    output_name = next(iter(outputs))
    for node in nodes:
        if node.get("component_type") == "Output":
            node["output_name"] = output_name
    permissions = dict(_EMPTY_PERMISSIONS)
    if plan.task.get("protect_input_files"):
        permissions["protect_input_files"] = True
    if plan.task.get("protected_input_fields"):
        permissions["protected_input_fields"] = [
            workflow_io_name(name) for name in plan.task["protected_input_fields"]
        ]
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
                    "checks": list(dict.fromkeys(checks)),
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


def _node(
    step: PlanStep,
    agents: dict[str, AgentSource],
    plan: ExecutionPlan,
    *,
    entity_tool: dict[str, Any] | None,
) -> dict[str, Any]:
    node_id = workflow_node_id(step.id)
    if step.kind == "start":
        return {"id": node_id, "component_type": "Start"}
    if step.kind == "stop":
        return {"id": node_id, "component_type": "Stop"}
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
        inputs = {name: workflow_io_name(name) for name in source.inputs} or {
            "request": "request"
        }
        outputs = {name: workflow_node_id(name) for name in source.outputs} or {
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
            workflow_io_name(name): (
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
    source = workflow_node_id(step.id)
    if step.kind in {"output", "stop"}:
        return
    if step.kind == "condition":
        if step.on_true:
            transitions.append(
                {"from": source, "port": "true", "to": workflow_node_id(step.on_true)}
            )
        if step.on_false:
            transitions.append(
                {"from": source, "port": "false", "to": workflow_node_id(step.on_false)}
            )
        return
    if step.kind in {"human_approval", "human_input"}:
        if step.on_approved:
            transitions.append(
                {
                    "from": source,
                    "port": "approved",
                    "to": workflow_node_id(step.on_approved),
                }
            )
        if step.on_rejected:
            transitions.append(
                {
                    "from": source,
                    "port": "rejected",
                    "to": workflow_node_id(step.on_rejected),
                }
            )
        return
    if step.kind == "verifier":
        passed = step.on_true or step.on_next or "output"
        failed = step.on_false or "output"
        transitions.append(
            {"from": source, "port": "passed", "to": workflow_node_id(passed)}
        )
        transitions.append(
            {"from": source, "port": "failed", "to": workflow_node_id(failed)}
        )
        return
    if step.on_next:
        transitions.append(
            {"from": source, "port": "next", "to": workflow_node_id(step.on_next)}
        )
