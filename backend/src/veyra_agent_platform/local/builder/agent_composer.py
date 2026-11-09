"""Compose a loop AgentSource from AgentSpecification + ResourcePlan.

Resolver chooses resources. This module writes AgentSource, permissions, and locks.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from veyra_agent_platform.contracts.agent import (
    DEFAULT_MAX_TURNS,
    EXECUTION_KIND_LOOP,
    AgentSource,
)
from veyra_agent_platform.contracts.agent_spec import AgentSpecification
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.filesystem_scope import (
    NATIVE_PROJECT_FILESYSTEM_ADAPTERS,
    filesystem_roots_satisfied,
    normalize_project_scope,
)
from veyra_agent_platform.contracts.finalization import FinalizationContract
from veyra_agent_platform.contracts.interaction import derive_interaction_mode
from veyra_agent_platform.contracts.resource_plan import PlannedResource, ResourcePlan
from veyra_agent_platform.contracts.semantic_plan import SemanticField
from veyra_agent_platform.contracts.task_structure import StateRequirement
from veyra_agent_platform.contracts.typed_io import ARTIFACT_KINDS, TypedField
from veyra_agent_platform.local.builder.agent_state import state_instructions
from veyra_agent_platform.local.builder.knowledge_binding import bind_knowledge
from veyra_agent_platform.local.projects.layout import attach_default_canvas_note

_RUNTIME_PROFILE = "veyra-runtime-profile/1"
_RUNTIME_LOCK = "veyra.runtime.profile@1.0.0"
_EMPTY_PERMISSIONS: dict[str, Any] = {
    "network_hosts": [],
    "tools": [],
    "filesystem_read_roots": [],
    "filesystem_write_roots": [],
    "shell_workspace_only": False,
}


def compose_loop_agent(
    specification: AgentSpecification,
    plan: ResourcePlan,
    *,
    requirement: str = "",
    agent_id: str | None = None,
    state: StateRequirement | None = None,
    filesystem_write_roots: tuple[str, ...] = (),
    protect_input_files: bool = False,
    protected_input_fields: tuple[str, ...] = (),
    finalization: FinalizationContract | None = None,
    initial_model_turns: int = DEFAULT_MAX_TURNS,
) -> AgentSource:
    """Build AgentSource from a server ResourcePlan. Never invents resource IDs."""

    from veyra_agent_platform.local.factory.compiler import agent_candidate_identity

    display, slug = agent_candidate_identity(specification.suggested_name or "Agent")
    instructions = _instructions(specification, requirement)
    if state is not None:
        instructions += "\n\n" + state_instructions(state)
    if finalization is not None:
        instructions += (
            "\n\nDelivery contract: final submits a candidate, not a published result. "
            "Runtime checks it and returns read-only review feedback in this same "
            "run. Correct the cited defects without changing the task or granting "
            "permissions. Ask the user only when an absent fact or choice is "
            "needed to fulfill the task. When the task asks to report gaps or "
            "conflicts, report them without guessing; optional future corrections "
            "are not a delivery prerequisite. Preserve explicit user decisions "
            "and before-effect approvals. Model review is "
            "not independent factual or physical verification."
            " If project state includes generated images, use render_images and "
            "record its actual artifact references before final. Business state "
            "writes are retained as progress, not automatic proof of acceptance."
        )
    outputs = {
        agent_io_name(item.name): _field_wire(item) for item in specification.outputs
    } or {"result": "string"}
    inputs = {
        agent_io_name(item.name): _field_wire(item) for item in specification.inputs
    } or {"request": "string"}
    if len(inputs) != len(specification.inputs) and specification.inputs:
        raise ValueError("Agent input field names collide after normalization")
    if len(outputs) != len(specification.outputs) and specification.outputs:
        raise ValueError("Agent output field names collide after normalization")
    primary_output = next(iter(outputs))
    ready: list[PlannedResource] = []
    seen: set[str] = set()
    for item in (*plan.selected, *plan.needs_configuration):
        if item.bind_status not in {
            "already_bound",
            "will_bind",
            "needs_configuration",
        }:
            continue
        if item.reference in seen:
            continue
        seen.add(item.reference)
        ready.append(item)
    tools = [item for item in ready if item.kind in {"tool", "mcp_tool"}]
    skills = [item for item in ready if item.kind == "skill"]
    policies = [item for item in ready if item.kind == "policy"]
    permissions = dict(_EMPTY_PERMISSIONS)
    if protect_input_files:
        permissions["protect_input_files"] = True
    if protected_input_fields:
        permissions["protected_input_fields"] = [
            agent_io_name(name) for name in protected_input_fields
        ]
    lock: dict[str, str] = {
        _RUNTIME_LOCK: sha256_digest({"runtime_profile": _RUNTIME_PROFILE})
    }
    bindings: dict[str, dict[str, Any]] = {}
    for index, resource in enumerate(tools, start=1):
        _apply_tool_permissions(permissions, resource)
        lock[resource.reference] = resource.content_hash
        bindings[f"bind_tool{index}"] = {
            "kind": resource.kind,
            "reference": resource.reference,
            "x": 480,
            "y": 40 + (index * 90),
        }
    if filesystem_write_roots:
        roots = tuple(
            dict.fromkeys(
                normalize_project_scope(root) for root in filesystem_write_roots
            )
        )
        if roots != ("project",) and any(
            "shell_exec" in resource.capabilities
            or (resource.required_permissions or {}).get("shell_workspace_only")
            or (
                "workspace_write" in resource.capabilities
                and resource.adapter not in NATIVE_PROJECT_FILESYSTEM_ADAPTERS
            )
            for resource in tools
        ):
            raise ValueError("Selected executor cannot enforce a directory write limit")
    if filesystem_write_roots and permissions["filesystem_write_roots"]:
        writers = [
            resource
            for resource in tools
            if (resource.required_permissions or {}).get("filesystem_write_roots")
        ]
        if set(roots) != set(permissions["filesystem_write_roots"]) and any(
            resource.adapter not in NATIVE_PROJECT_FILESYSTEM_ADAPTERS
            for resource in writers
        ):
            raise ValueError("Selected executor cannot enforce a directory write limit")
        if not filesystem_roots_satisfied(
            permissions["filesystem_write_roots"],
            roots,
            allow_subscopes=True,
        ):
            raise ValueError(
                "Requested write scope is incompatible with selected Tools"
            )
        permissions["filesystem_write_roots"] = list(roots)
    for index, resource in enumerate(skills, start=1):
        lock[resource.reference] = resource.content_hash
        bindings[f"bind_skill{index}"] = {
            "kind": "skill",
            "reference": resource.reference,
            "x": 700,
            "y": 40 + (index * 90),
        }
    for index, resource in enumerate(policies, start=1):
        lock[resource.reference] = resource.content_hash
        bindings[f"bind_policy{index}"] = {
            "kind": "policy",
            "reference": resource.reference,
            "x": 920,
            "y": 40 + (index * 90),
        }
    secret_refs = sorted({ref for resource in tools for ref in _secret_refs(resource)})
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "agentspec_version": "26.1",
        "component_type": "Flow",
        "agent_id": agent_id or new_uuid7(),
        "slug": slug,
        "name": display,
        "description": specification.description or specification.goal,
        "inputs": inputs,
        "outputs": outputs,
        "nodes": [
            {"id": "start", "component_type": "Start"},
            {
                "id": "model",
                "component_type": "Model",
                "model_ref": "model.primary",
                "system_prompt": instructions,
            },
            {"id": "output", "component_type": "Output", "output_name": primary_output},
        ],
        "transitions": [
            {"from": "start", "port": "next", "to": "model"},
            {"from": "model", "port": "next", "to": "output"},
        ],
        "extensions": {
            "veyra": {
                "runtime_profile": _RUNTIME_PROFILE,
                "secret_refs": secret_refs,
                "permissions": permissions,
                "verification": {"required": False, "checks": []},
                "skill_refs": [item.reference for item in skills],
                "policy_refs": [item.reference for item in policies],
                "execution_kind": EXECUTION_KIND_LOOP,
                "interaction_mode": derive_interaction_mode(inputs),
                "instructions": instructions,
                "max_turns": initial_model_turns,
                "handoff_agent_refs": [],
                **({"state_contract": state.to_dict()} if state is not None else {}),
            }
        },
        "ui": attach_default_canvas_note(
            {
                "positions": {
                    "start": {"x": 0, "y": 80},
                    "model": {"x": 240, "y": 80},
                    "output": {"x": 480, "y": 80},
                },
                **({"bindings": bindings} if bindings else {}),
            },
            specification.goal or display,
        ),
        "lock": lock,
    }
    if finalization is not None:
        payload["extensions"]["veyra"]["finalization"] = finalization.to_dict()
    if plan.knowledge.status == "available":
        for document in plan.knowledge.documents:
            payload = bind_knowledge(payload, dict(document))
    source = AgentSource.from_dict(payload)
    if any(
        node.component_type.value in {"Condition", "HumanApproval", "Transform"}
        for node in source.nodes
    ):
        raise ValueError("loop Agent composer must not emit orchestration nodes")
    unknown = [
        item.reference
        for item in tools + skills + policies
        if item.reference not in source.lock
    ]
    if unknown:
        raise ValueError("loop Agent composer dropped ResourcePlan locks")
    return source


def _apply_tool_permissions(
    permissions: dict[str, Any], resource: PlannedResource
) -> None:
    extras = catalog_permission_overlay(resource.required_permissions or {})
    if not extras["tools"]:
        extras["tools"] = [resource.resource_id]
    permissions["tools"] = _unique([*permissions["tools"], *extras["tools"]])
    permissions["network_hosts"] = _unique(
        [*permissions["network_hosts"], *extras["network_hosts"]]
    )
    permissions["filesystem_read_roots"] = _unique(
        [*permissions["filesystem_read_roots"], *extras["filesystem_read_roots"]]
    )
    permissions["filesystem_write_roots"] = _unique(
        [*permissions["filesystem_write_roots"], *extras["filesystem_write_roots"]]
    )
    if extras["shell_workspace_only"]:
        permissions["shell_workspace_only"] = True


def _secret_refs(resource: PlannedResource | None) -> list[str]:
    if resource is None or not resource.secret_ref:
        return []
    return [resource.secret_ref]


def _instructions(specification: AgentSpecification, requirement: str) -> str:
    sections = [specification.goal.strip()]
    if requirement.strip():
        sections.append("User's complete requirement:\n" + requirement.strip())
    if specification.responsibilities:
        sections.append(
            "Your responsibilities:\n" + "\n".join(specification.responsibilities)
        )
    if specification.human_interactions:
        sections.append(
            "Human interaction constraints:\n"
            + "\n".join(specification.human_interactions)
        )
    if specification.success_criteria:
        sections.append(
            "Success criteria:\n" + "\n".join(specification.success_criteria)
        )
    body = "\n\n".join(item for item in sections if item)
    outputs = (
        ", ".join(f"{item.name}:{item.type}" for item in specification.outputs)
        or "result:string"
    )
    return (
        f"{body}\n\n"
        "You are an autonomous Agent. Decide whether to call a permitted tool. "
        "Do not follow a fixed DAG. The complete requirement is context: perform "
        "only your responsibilities and respect the declared human boundaries. "
        "When finished, return the declared outputs: "
        f"{outputs}."
    )


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in values if item))


def agent_io_name(name: str) -> str:
    compact = re.sub(r"[^a-z0-9-]", "", name.casefold().replace("_", "-"))
    compact = re.sub(r"-{2,}", "-", compact).strip("-")
    if not compact or compact[0].isdigit() or not compact[0].isalpha():
        return "field"
    return compact[:63]


def _field_wire(item: SemanticField) -> str | dict[str, object]:
    name = item.type
    if item.type in ARTIFACT_KINDS:
        field = TypedField(
            type="artifact",
            artifact_kind=item.type,  # type: ignore[arg-type]
            required=item.required,
            multiple=item.multiple,
            description=item.description,
        )
        return field.to_wire()
    if item.multiple or not item.required or item.description:
        payload: dict[str, object] = {"type": name}
        if not item.required:
            payload["required"] = False
        if item.multiple:
            payload["multiple"] = True
        if item.description:
            payload["description"] = item.description
        return payload
    return name


def catalog_permission_overlay(
    required: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(required, Mapping):
        required = {}
    nested = required.get("required_permissions")
    if isinstance(nested, Mapping):
        required = nested
    return {
        "tools": list(required.get("tools") or []),
        "network_hosts": list(required.get("network_hosts") or []),
        "filesystem_read_roots": list(required.get("filesystem_read_roots") or []),
        "filesystem_write_roots": list(required.get("filesystem_write_roots") or []),
        "shell_workspace_only": bool(required.get("shell_workspace_only")),
    }
