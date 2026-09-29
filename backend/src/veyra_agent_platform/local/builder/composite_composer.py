"""Compose companion Agents and a Workflow DAG from an ExecutionPlan."""

from __future__ import annotations

import re
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.agent_spec import AgentSpecification
from veyra_agent_platform.contracts.common import SCHEMA_VERSION, new_uuid7
from veyra_agent_platform.contracts.execution_plan import (
    ExecutionPlan,
    PlanActor,
    PlanStep,
)
from veyra_agent_platform.contracts.resource_plan import ResourcePlan
from veyra_agent_platform.contracts.semantic_plan import SemanticField
from veyra_agent_platform.contracts.task_structure import TaskIOField
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
    if requirement and (role is None or role.id in {"main", "editor"}):
        from veyra_agent_platform.local.builder.specification import (
            infer_agent_specification,
        )

        legacy = infer_agent_specification(requirement).suggested_name
        if legacy:
            name = legacy
    caps = tuple(role.capabilities) if role is not None else plan.capabilities
    inputs = plan.inputs or (TaskIOField(name="request", type="string"),)
    outputs = _actor_outputs(plan, role)
    return AgentSpecification(
        schema_version=SCHEMA_VERSION,
        goal=(role.brief if role is not None else plan.shape.reason)
        or requirement[:400],
        suggested_name=name,
        description=requirement[:400] or plan.shape.reason,
        inputs=tuple(_semantic(item) for item in inputs),
        outputs=tuple(_semantic(item) for item in outputs),
        responsibilities=(role.brief,) if role is not None and role.brief else (),
        human_interactions=(),
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
        success_criteria=(),
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
        return compose_loop_agent(spec, resolved, requirement=requirement), None
    companions: list[AgentSource] = []
    by_id: dict[str, AgentSource] = {}
    for actor in plan.actors:
        spec = specification_from_plan(plan, actor=actor, requirement=requirement)
        source = compose_loop_agent(spec, resolved, requirement=actor.brief)
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
    for column, step in enumerate(plan.steps):
        nodes.append(_node(step, agents, plan, entity_tool=entity_tool))
        node_id = _flow_id(step.id)
        positions[node_id] = {"x": 80 + column * 220, "y": 80}
        labels[node_id] = step.id.replace("-", " ").replace("_", " ")
        if step.kind == "verifier":
            checks = list(step.checks)
        _emit_edges(step, transitions)
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
    lock: dict[str, str] = {}
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
            and item.type not in {"image", "pdf", "document", "file", "collection"}
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
        source = agents.get(step.agent) or next(iter(agents.values()), None)
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
