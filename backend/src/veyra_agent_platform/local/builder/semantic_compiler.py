"""Compile AgentSemanticPlanV1 into a canonical AgentBlueprint candidate.

The model describes intent. This compiler owns IDs, pins, permissions, and
graph wiring. It reuses Slice 1/2 resolvers and never guesses among matches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from veyra_agent_platform.contracts.agent import AgentBlueprint, AgentSource
from veyra_agent_platform.contracts.semantic_plan import AgentSemanticPlanV1
from veyra_agent_platform.local.builder.knowledge_binding import (
    bind_knowledge,
    knowledge_reference,
    resolve_knowledge,
)
from veyra_agent_platform.local.builder.resource_binding import (
    FILESYSTEM_READ_RESOURCE_ID,
    grant_required_permissions,
    resolve_project_resource,
)

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_SLUG_NOISE = re.compile(r"[^a-z0-9]+")
_PROJECT_SCOPED_READ = re.compile(
    r"(project|workspace|项目|工作区).{0,24}(file|文件)|"
    r"(file|文件).{0,24}(project|workspace|项目|工作区)|"
    r"filesystem[._ -]?read|"
    r"veyra\.tool\.filesystem\.read",
    re.IGNORECASE,
)
_EXTERNAL_TOOL = re.compile(
    r"(github|mcp\b|shell\.exec|browser\.navigate|veyra\.tool\.(?!filesystem\.read))",
    re.IGNORECASE,
)
CompileStatus = Literal["compiled", "clarification", "missing_capability"]


@dataclass(frozen=True)
class BuilderProjectContext:
    project_id: str
    knowledge: tuple[dict[str, Any], ...]
    project_resources: tuple[dict[str, Any], ...]
    catalog_resources: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class SemanticCompileResult:
    status: CompileStatus
    blueprint: AgentBlueprint | None
    question: str | None
    missing: tuple[dict[str, Any], ...]
    tools: tuple[dict[str, Any], ...]
    documents: tuple[dict[str, Any], ...]


def compile_semantic_plan(
    plan: AgentSemanticPlanV1, context: BuilderProjectContext
) -> SemanticCompileResult:
    """Resolve intents against this Project, then emit a validated Blueprint."""

    tools: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    seen_tools: set[str] = set()
    seen_knowledge: set[str] = set()

    for intent in plan.capability_intents:
        match = resolve_project_resource(
            list(context.project_resources),
            list(context.catalog_resources),
            intent,
        )
        if match.status == "resolved" and match.selected is not None:
            reference = str(match.selected["reference"])
            if reference not in seen_tools:
                tools.append(match.selected)
                seen_tools.add(reference)
            continue
        if match.status == "ambiguous":
            return SemanticCompileResult(
                "clarification",
                None,
                _clarify(plan.goal, match.candidates, knowledge=False),
                (),
                (),
                (),
            )
        if match.status == "unbound":
            if _PROJECT_SCOPED_READ.search(intent):
                missing.append(
                    _missing_capability(
                        "tool",
                        FILESYSTEM_READ_RESOURCE_ID,
                        "Tool is not bound to this Project",
                    )
                )
            continue
        if _EXTERNAL_TOOL.search(intent):
            missing.append(
                _missing_capability(
                    "tool",
                    intent,
                    "Requested capability is not bound to this Project",
                )
            )

    for intent in plan.knowledge_intents:
        knowledge_match = resolve_knowledge(list(context.knowledge), intent)
        if (
            knowledge_match.status == "resolved"
            and knowledge_match.selected is not None
        ):
            reference = knowledge_reference(knowledge_match.selected)
            if reference not in seen_knowledge:
                documents.append(knowledge_match.selected)
                seen_knowledge.add(reference)
            continue
        if knowledge_match.status == "ambiguous":
            return SemanticCompileResult(
                "clarification",
                None,
                _clarify(plan.goal, knowledge_match.candidates, knowledge=True),
                (),
                (),
                (),
            )

    if missing:
        return SemanticCompileResult(
            "missing_capability", None, None, tuple(missing), (), ()
        )

    blueprint = AgentBlueprint.from_dict(_blueprint_payload(plan, tools, documents))
    return SemanticCompileResult(
        "compiled",
        blueprint,
        None,
        (),
        tuple(tools),
        tuple(documents),
    )


def finalize_compiled_source(
    source: AgentSource, context: BuilderProjectContext
) -> AgentSource:
    """Replace Catalog hashes with Project pins and bind resolved Knowledge."""

    payload = source.to_dict()
    bound = {
        str(item["reference"]): item
        for item in context.project_resources
        if item.get("scope") == "project"
    }
    for node in payload["nodes"]:
        uses = node.get("uses")
        resource = bound.get(str(uses or ""))
        if resource is None:
            continue
        digest = resource.get("bound_content_hash")
        if isinstance(digest, str) and _HASH.fullmatch(digest):
            payload["lock"][str(uses)] = digest
        payload["extensions"]["veyra"]["permissions"] = grant_required_permissions(
            payload["extensions"]["veyra"]["permissions"],
            resource["required_permissions"],
        )
    knowledge = {
        knowledge_reference(document): document for document in context.knowledge
    }
    for binding in (payload.get("ui") or {}).get("bindings") or {}.values():
        if not isinstance(binding, dict) or binding.get("kind") != "knowledge":
            continue
        document = knowledge.get(str(binding.get("reference") or ""))
        if document is not None:
            payload = bind_knowledge(payload, document)
    return AgentSource.from_dict(payload)


def builder_project_context(
    *,
    project_id: str,
    knowledge: list[dict[str, Any]],
    project_resources: list[dict[str, Any]],
    catalog_resources: list[dict[str, Any]],
) -> BuilderProjectContext:
    return BuilderProjectContext(
        project_id=project_id,
        knowledge=tuple(knowledge),
        project_resources=tuple(project_resources),
        catalog_resources=tuple(catalog_resources),
    )


def _blueprint_payload(
    plan: AgentSemanticPlanV1,
    tools: list[dict[str, Any]],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    used_fields: set[str] = set()
    inputs = {
        _field_slug(item.name, used_fields, "input"): item.type for item in plan.inputs
    }
    outputs = {
        _field_slug(item.name, used_fields, "output"): item.type
        for item in plan.outputs
    }
    extra_outputs = [f"{item.name} ({item.type})" for item in plan.outputs[1:]]
    if extra_outputs:
        primary_name, primary_type = next(iter(outputs.items()))
        outputs = {primary_name: primary_type}
    path_input = next(
        (name for name, kind in inputs.items() if kind == "string" and "path" in name),
        None,
    )
    if tools and path_input is None:
        path_input = _field_slug("path", used_fields, "input")
        inputs[path_input] = "string"

    nodes: list[dict[str, Any]] = [{"id": "start", "component_type": "Start"}]
    transitions: list[dict[str, str]] = []
    positions = {"start": {"x": 0, "y": 0}}
    previous = "start"
    cursor_x = 0
    permissions = {
        "network_hosts": [],
        "tools": [],
        "filesystem_read_roots": [],
        "filesystem_write_roots": [],
        "shell_workspace_only": False,
    }

    for index, resource in enumerate(tools):
        node_id = "filesystem_read" if index == 0 else f"filesystem_read_{index + 1}"
        nodes.append(
            {
                "id": node_id,
                "component_type": "Tool",
                "uses": resource["reference"],
                "input_mapping": {"path": path_input},
            }
        )
        transitions.append({"from": previous, "port": "next", "to": node_id})
        cursor_x += 160
        positions[node_id] = {"x": cursor_x, "y": 0}
        previous = node_id
        permissions = grant_required_permissions(
            permissions, resource["required_permissions"]
        )

    cursor_x += 160
    nodes.append(
        {
            "id": "analyze",
            "component_type": "Agent",
            "model_ref": "model.primary",
            "system_prompt": _system_prompt(plan, extra_outputs),
        }
    )
    transitions.append({"from": previous, "port": "next", "to": "analyze"})
    positions["analyze"] = {"x": cursor_x, "y": 0}

    output_name = next(iter(outputs))
    cursor_x += 160
    nodes.append(
        {"id": "output", "component_type": "Output", "output_name": output_name}
    )
    transitions.append({"from": "analyze", "port": "next", "to": "output"})
    positions["output"] = {"x": cursor_x, "y": 0}

    bindings: dict[str, dict[str, Any]] = {}
    for index, document in enumerate(documents):
        identity = f"knowledge_{index + 1}"
        bindings[identity] = {
            "kind": "knowledge",
            "reference": knowledge_reference(document),
            "x": 24 + (index % 3) * 220,
            "y": 24 + (index // 3) * 140,
        }

    component_types = list(dict.fromkeys(str(node["component_type"]) for node in nodes))
    ui: dict[str, Any] = {"positions": positions}
    if bindings:
        ui["bindings"] = bindings
    return {
        "schema_version": "1.0",
        "goal": plan.goal,
        "inputs": inputs,
        "outputs": outputs,
        "nodes": nodes,
        "transitions": transitions,
        "required_capabilities": {
            "component_types": component_types,
            "tool_refs": [resource["reference"] for resource in tools],
            "skill_refs": [],
            "policy_refs": [],
        },
        "requested_permissions": permissions,
        "verification": {"required": False, "checks": []},
        "ui_suggestions": ui,
    }


def _system_prompt(
    plan: AgentSemanticPlanV1, extra_outputs: list[str] | None = None
) -> str:
    lines = [
        f"You are {plan.suggested_name}.",
        plan.description,
        f"Goal: {plan.goal}",
        "Steps:",
        *[f"{index}. {step}" for index, step in enumerate(plan.steps, start=1)],
    ]
    if extra_outputs:
        lines.append("Also include these fields in the result:")
        lines.extend(f"- {item}" for item in extra_outputs)
    if plan.success_criteria:
        lines.append("Success:")
        lines.extend(f"- {item}" for item in plan.success_criteria)
    if plan.approval_points:
        lines.append("Ask for approval when:")
        lines.extend(f"- {item}" for item in plan.approval_points)
    if plan.user_constraints:
        lines.append("Constraints:")
        lines.extend(f"- {item}" for item in plan.user_constraints)
    return "\n".join(lines)


def _field_slug(name: str, used: set[str], prefix: str) -> str:
    folded = _SLUG_NOISE.sub("-", name.casefold()).strip("-")
    if not folded or not folded[0].isalpha():
        folded = f"{prefix}-{len(used) + 1}"
    folded = folded[:63].strip("-") or f"{prefix}-{len(used) + 1}"
    candidate = folded
    index = 2
    while candidate in used:
        suffix = f"-{index}"
        candidate = f"{folded[: 63 - len(suffix)]}{suffix}"
        index += 1
    used.add(candidate)
    return candidate


def _clarify(
    goal: str, candidates: tuple[dict[str, Any], ...], *, knowledge: bool
) -> str:
    names = ", ".join(
        str(item.get("name") or item.get("reference") or "")
        for item in candidates
        if item.get("name") or item.get("reference")
    )
    if _CJK.search(goal):
        kind = "资料" if knowledge else "能力"
        return f"当前 Project 中有多份匹配的{kind}：{names}。请指出要用哪一份。"
    kind = "Knowledge documents" if knowledge else "capabilities"
    return (
        f"This Project has multiple matching {kind}: {names}. Which one should be used?"
    )


def _missing_capability(kind: str, reference: str, reason: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "reference": reference,
        "reason": reason,
        "proposal": {"action": "quarantined_resource_draft", "executable": False},
    }
