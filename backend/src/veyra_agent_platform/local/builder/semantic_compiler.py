"""Compile AgentSemanticPlan into a canonical AgentBlueprint candidate.

The model describes intent and optional step graph intent. This compiler owns
IDs, pins, permissions, and graph wiring. It never emits AgentCall inside an
Agent and never guesses among Project resources.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Literal

from veyra_agent_platform.contracts.agent import AgentBlueprint, AgentSource
from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.condition import parse_condition_expression
from veyra_agent_platform.contracts.semantic_plan import (
    AgentSemanticPlanV1,
    SemanticField,
    SemanticStepIntent,
)
from veyra_agent_platform.local.builder.component_planning import (
    resolve_reusable_capabilities,
)
from veyra_agent_platform.local.builder.dataflow_compiler import (
    DataflowCompileError,
    attach_compiled_dataflow,
    attach_step_ports,
    field_wire,
)
from veyra_agent_platform.local.builder.knowledge_binding import (
    bind_knowledge,
    knowledge_reference,
    resolve_knowledge,
)
from veyra_agent_platform.local.builder.resource_binding import (
    FILESYSTEM_READ_RESOURCE_ID,
    grant_required_permissions,
    resolve_capability_intent,
    resource_readiness,
)
from veyra_agent_platform.local.projects.layout import (
    attach_default_canvas_note,
    default_canvas_note,
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
_POLICY_MARKERS = (
    "mcp",
    "web-search",
    "shell.exec",
    "browser.navigate",
    "github",
    "http",
)
_EXTERNAL_TOOL = re.compile(
    r"(github|mcp\b|shell\.exec|browser\.navigate|veyra\.tool\.(?!filesystem\.read))",
    re.IGNORECASE,
)


def _is_regurgitated_policy(text: str) -> bool:
    folded = text.casefold()
    hits = sum(1 for marker in _POLICY_MARKERS if marker in folded)
    return hits >= 2 or text.count(",") >= 3


_OUTPUT_NOT_EMPTY = re.compile(
    r"not empty|non-?empty|非空|有输出|must produce|output exists|"
    r"结果不为空|contains? (a )?(result|output)",
    re.IGNORECASE,
)
_RESERVED_NODE_IDS = {"start", "output", "note_intro"}
CompileStatus = Literal[
    "compiled", "clarification", "missing_capability", "compile_error"
]


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
    warnings: tuple[str, ...] = ()
    error: str | None = None


class SemanticGraphError(ValueError):
    """A semantic graph cannot be represented without losing its meaning."""


@dataclass(frozen=True)
class _GraphFork:
    step: SemanticStepIntent
    ports: tuple[str, str]
    keys: tuple[str, str]
    labels: tuple[str, str]


_CONFIRM_LITERALS = frozenset({"confirm", "confirmed", "approved", "yes", "ok", "true"})
_SYNTHETIC_ROUTE_FIELDS = frozenset(
    {
        "decision",
        "confirm",
        "choice",
        "approved",
        "user-decision",
        "user_decision",
        "route",
        "route-decision",
        "confirmation",
    }
)


def _output_contract_line(name: str, item: SemanticField) -> str:
    label = f"{name} ({item.type})"
    if name != item.name:
        label += f" [{item.name}]"
    if item.description:
        label += f": {item.description}"
    return label


def _describe_fork(ordered: list[SemanticStepIntent]) -> _GraphFork:
    conditions = [
        step for step in ordered if step.operation_kind == "condition" and step.branches
    ]
    approval_forks = [
        step
        for step in ordered
        if step.operation_kind == "approval"
        and any(
            child.branch_condition.casefold() == step.semantic_key.casefold()
            for child in ordered
        )
    ]
    if conditions and approval_forks:
        raise SemanticGraphError(
            "V1 supports one fork per Agent graph; use a Condition on a Run "
            "input or HumanApproval approved/rejected ports, not both"
        )
    if len(conditions) > 1:
        raise SemanticGraphError(
            "V1 supports one branched Condition per Agent graph; nested or sibling "
            "branched Conditions need an explicit graph compiler"
        )
    if len(approval_forks) > 1:
        raise SemanticGraphError("V1 supports one HumanApproval fork per Agent graph")
    if conditions:
        condition = conditions[0]
        return _GraphFork(
            condition,
            ("true", "false"),
            (condition.branches[0].key, condition.branches[1].key),
            (condition.branches[0].label, condition.branches[1].label),
        )
    if approval_forks:
        approval = approval_forks[0]
        return _GraphFork(
            approval,
            ("approved", "rejected"),
            ("approved", "rejected"),
            ("approved", "rejected"),
        )
    raise SemanticGraphError(
        "branch_condition requires a forked Condition or HumanApproval"
    )


@dataclass(frozen=True)
class _RedundantCondition:
    approval: str
    mapping: dict[str, str]


def _collapse_redundant_approval_condition(
    plan: AgentSemanticPlanV1,
) -> tuple[AgentSemanticPlanV1, tuple[str, ...]]:
    """Rewrite approval then Condition(confirm) into approval ports."""

    steps = list(plan.step_intents)
    approvals = {
        step.semantic_key.casefold(): step.semantic_key
        for step in steps
        if step.operation_kind == "approval"
    }
    redundant: dict[str, _RedundantCondition] = {}
    for step in steps:
        if step.operation_kind != "condition" or len(step.branches) != 2:
            continue
        approval_deps = [
            approvals[item.casefold()]
            for item in step.depends_on
            if item.casefold() in approvals
        ]
        if len(approval_deps) != 1 or not step.condition_expression.strip():
            continue
        try:
            parsed = parse_condition_expression(step.condition_expression)
        except ContractValidationError:
            continue
        if parsed.operator != "==":
            continue
        field_key = parsed.field.casefold().replace("_", "-")
        literal = str(parsed.literal).casefold()
        synthetic = field_key in {
            item.replace("_", "-") for item in _SYNTHETIC_ROUTE_FIELDS
        }
        if (
            literal not in _CONFIRM_LITERALS
            and parsed.literal is not True
            and not synthetic
        ):
            continue
        redundant[step.semantic_key.casefold()] = _RedundantCondition(
            approval_deps[0],
            {
                step.branches[0].key.casefold(): "approved",
                step.branches[1].key.casefold(): "rejected",
            },
        )
    if not redundant:
        return plan, ()
    rewritten: list[SemanticStepIntent] = []
    for step in steps:
        if step.semantic_key.casefold() in redundant:
            continue
        depends: list[str] = []
        seen: set[str] = set()
        for item in step.depends_on:
            folded = item.casefold()
            mapped = redundant.get(folded)
            target = mapped.approval if mapped is not None else item
            key = target.casefold()
            if key in seen:
                continue
            seen.add(key)
            depends.append(target)
        info = (
            redundant.get(step.branch_condition.casefold())
            if step.branch_condition
            else None
        )
        if info is not None:
            rewritten.append(
                replace(
                    step,
                    depends_on=tuple(depends),
                    branch_condition=info.approval,
                    branch_key=info.mapping.get(step.branch_key.casefold(), "approved"),
                )
            )
            continue
        if tuple(depends) != step.depends_on:
            rewritten.append(replace(step, depends_on=tuple(depends)))
        else:
            rewritten.append(step)
    return (
        replace(plan, step_intents=tuple(rewritten)),
        ("collapsed_redundant_approval_condition",),
    )


def compile_semantic_plan(
    plan: AgentSemanticPlanV1, context: BuilderProjectContext
) -> SemanticCompileResult:
    """Resolve intents against this Project, then emit a validated Blueprint."""

    documents, knowledge_question = _resolve_knowledge(plan, context)
    if knowledge_question is not None:
        return SemanticCompileResult(
            "clarification", None, knowledge_question, (), (), ()
        )

    reusable = resolve_reusable_capabilities(plan, list(context.project_resources))
    if reusable.clarification is not None:
        return SemanticCompileResult(
            "clarification", None, reusable.clarification, (), (), ()
        )
    effective = _with_synthesized_intents(reusable.plan)
    if effective.step_intents:
        compiled = _compile_graph_intent(effective, context, documents)
    else:
        compiled = _compile_v1(effective, context, documents)
    if reusable.missing:
        return SemanticCompileResult(
            "missing_capability",
            None,
            None,
            tuple(_merge_missing(list(reusable.missing), list(compiled.missing))),
            compiled.tools,
            compiled.documents,
            compiled.warnings,
        )
    return compiled


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


def _with_synthesized_intents(plan: AgentSemanticPlanV1) -> AgentSemanticPlanV1:
    if plan.step_intents or len(plan.steps) <= 1:
        return plan
    return replace(plan, step_intents=_sequential_model_intents(plan.steps))


def _sequential_model_intents(steps: tuple[str, ...]) -> tuple[SemanticStepIntent, ...]:
    used = set(_RESERVED_NODE_IDS)
    intents: list[SemanticStepIntent] = []
    previous: str | None = None
    for phrase in steps:
        key = _unique_id(_node_id_from_key(phrase), used)
        intents.append(
            SemanticStepIntent(
                semantic_key=key,
                name=phrase[:80],
                purpose=phrase[:240],
                operation_kind="model",
                depends_on=(previous,) if previous else (),
            )
        )
        previous = key
    return tuple(intents)


def _capability_query(step: SemanticStepIntent) -> str:
    if step.capability_requirement:
        return step.capability_requirement
    return " ".join(part for part in (step.name, step.purpose) if part).strip()


def _matching_tool(
    step: SemanticStepIntent, tools: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not tools:
        return None
    match = resolve_capability_intent(tools, [], _capability_query(step))
    if match.status == "resolved" and match.selected is not None:
        reference = str(match.selected.get("reference") or "")
        for resource in tools:
            if str(resource.get("reference") or "") == reference:
                return resource
    return None


def _readiness_warnings(tools: list[dict[str, Any]]) -> tuple[str, ...]:
    warnings: list[str] = []
    seen: set[str] = set()
    for resource in tools:
        state = str(resource_readiness(resource)["readiness"])
        if state == "ready":
            continue
        name = str(resource.get("name") or resource.get("resource_id") or "tool")
        token = f"capability_{state}:{name}"
        if token not in seen:
            seen.add(token)
            warnings.append(token)
    return tuple(warnings)


def _merge_missing(
    current: list[dict[str, Any]], extra: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged = list(current)
    seen = {str(item.get("reference") or "") for item in merged}
    for item in extra:
        reference = str(item.get("reference") or "")
        if reference and reference not in seen:
            merged.append(item)
            seen.add(reference)
        elif not reference:
            merged.append(item)
    return merged


def _compile_v1(
    plan: AgentSemanticPlanV1,
    context: BuilderProjectContext,
    documents: list[dict[str, Any]],
) -> SemanticCompileResult:
    tools, missing, question = _resolve_capability_intents(
        plan.capability_intents, context, require_unresolved=False
    )
    if question is not None:
        return SemanticCompileResult("clarification", None, question, (), (), ())
    modality_missing, modality_tools, modality_warnings = _modality_requirements(
        plan, context
    )
    missing.extend(modality_missing)
    if missing:
        return SemanticCompileResult(
            "missing_capability", None, None, tuple(missing), (), ()
        )
    tools = _merge_tools(tools, modality_tools)
    warnings = modality_warnings + _readiness_warnings(tools)
    try:
        payload = _linear_blueprint(
            plan,
            tools,
            documents,
            model_steps=[
                SemanticStepIntent(
                    semantic_key="analyze",
                    name=plan.suggested_name,
                    purpose=plan.description,
                    operation_kind="model",
                    depends_on=(),
                )
            ],
            extra_approvals=plan.approval_points,
            warnings=warnings,
            collapse_models=True,
        )
        blueprint = AgentBlueprint.from_dict(payload)
    except SemanticGraphError as exc:
        return SemanticCompileResult(
            "compile_error",
            None,
            None,
            (),
            tuple(tools),
            tuple(documents),
            warnings,
            error=str(exc),
        )
    except (TypeError, ValueError, ContractValidationError) as exc:
        return SemanticCompileResult(
            "compile_error",
            None,
            None,
            (),
            tuple(tools),
            tuple(documents),
            warnings,
            error=str(exc),
        )
    return SemanticCompileResult(
        "compiled",
        blueprint,
        None,
        (),
        tuple(tools),
        tuple(documents),
        warnings,
    )


def _compile_graph_intent(
    plan: AgentSemanticPlanV1,
    context: BuilderProjectContext,
    documents: list[dict[str, Any]],
) -> SemanticCompileResult:
    tools: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    seen: set[str] = set()
    capability_steps = [
        step for step in plan.step_intents if step.operation_kind == "capability"
    ]
    for step in capability_steps:
        match = resolve_capability_intent(
            list(context.project_resources),
            list(context.catalog_resources),
            _capability_query(step),
        )
        if match.status == "resolved" and match.selected is not None:
            reference = str(match.selected["reference"])
            if reference not in seen:
                tools.append(match.selected)
                seen.add(reference)
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
        missing.append(
            _missing_capability(
                "tool",
                _capability_query(step),
                "Requested capability is not bound to this Project",
            )
        )
    leftover_intents = () if capability_steps else plan.capability_intents
    extra_tools, extra_missing, question = _resolve_capability_intents(
        leftover_intents, context, require_unresolved=False
    )
    if question is not None:
        return SemanticCompileResult("clarification", None, question, (), (), ())
    for resource in extra_tools:
        reference = str(resource["reference"])
        if reference not in seen:
            tools.append(resource)
            seen.add(reference)
    missing = _merge_missing(missing, extra_missing)
    modality_missing, modality_tools, modality_warnings = _modality_requirements(
        plan, context
    )
    missing = _merge_missing(missing, modality_missing)
    tools = _merge_tools(tools, modality_tools)
    if missing:
        return SemanticCompileResult(
            "missing_capability", None, None, tuple(missing), (), ()
        )
    if any(step.operation_kind == "approval" for step in plan.step_intents):
        extra_approvals: tuple[str, ...] = ()
    else:
        extra_approvals = plan.approval_points
    plan, collapse_warnings = _collapse_redundant_approval_condition(plan)
    warnings = (
        _verification_warnings(plan)
        + modality_warnings
        + _readiness_warnings(tools)
        + collapse_warnings
    )
    try:
        payload = _linear_blueprint(
            plan,
            tools,
            documents,
            model_steps=list(plan.step_intents),
            extra_approvals=extra_approvals,
            warnings=warnings,
            collapse_models=False,
        )
    except SemanticGraphError as exc:
        return SemanticCompileResult(
            "compile_error",
            None,
            None,
            (),
            tuple(tools),
            tuple(documents),
            warnings,
            error=str(exc),
        )
    except (TypeError, ValueError) as exc:
        return SemanticCompileResult(
            "compile_error",
            None,
            None,
            (),
            tuple(tools),
            tuple(documents),
            warnings,
            error=str(exc),
        )
    return SemanticCompileResult(
        "compiled",
        AgentBlueprint.from_dict(payload),
        None,
        (),
        tuple(tools),
        tuple(documents),
        warnings,
    )


def _linear_blueprint(
    plan: AgentSemanticPlanV1,
    tools: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    *,
    model_steps: list[SemanticStepIntent],
    extra_approvals: tuple[str, ...],
    warnings: tuple[str, ...],
    collapse_models: bool,
) -> dict[str, Any]:
    used_fields: set[str] = set()
    inputs = {
        _field_slug(item.name, used_fields, "input"): _field_wire(item)
        for item in plan.inputs
    }
    outputs = {
        _field_slug(item.name, used_fields, "output"): _field_wire(item)
        for item in plan.outputs
    }
    extra_outputs = [
        _output_contract_line(name, item)
        for name, item in zip(outputs, plan.outputs, strict=True)
        if item.type != "image"
    ]
    path_input = next(
        (name for name, kind in inputs.items() if kind == "string" and "path" in name),
        None,
    )
    filesystem_tools = [
        resource
        for resource in tools
        if resource.get("kind") in {"tool", "mcp_tool"}
        and _is_filesystem_tool(resource)
    ]
    if filesystem_tools and path_input is None:
        path_input = _field_slug("path", used_fields, "input")
        inputs[path_input] = "string"

    nodes: list[dict[str, Any]] = [{"id": "start", "component_type": "Start"}]
    transitions: list[dict[str, str]] = []
    # Builder proposals are laid out by the shared Studio/Factory DAG layout.
    positions: dict[str, dict[str, int]] = {}
    labels: dict[str, str] = {}
    previous = "start"
    previous_port = "next"
    permissions = {
        "network_hosts": [],
        "tools": [],
        "filesystem_read_roots": [],
        "filesystem_write_roots": [],
        "shell_workspace_only": False,
    }
    used_ids = {"start", "output", "note_intro"}
    tool_by_ref = {str(resource["reference"]): resource for resource in tools}
    pending_tools = list(tools)
    ordered = _ordered_steps(model_steps, collapse_models=collapse_models)
    terminal_prompts = _terminal_prompt_keys(ordered)
    if not any(step.operation_kind == "capability" for step in ordered):
        for index, resource in enumerate(pending_tools):
            node_id = _unique_id(
                "filesystem_read" if index == 0 else f"tool_{index + 1}", used_ids
            )
            tool_node = _resource_node(resource, node_id)
            mapping = (
                {"path": path_input}
                if tool_node.get("component_type") == "Tool" and path_input
                else _component_input_mapping(resource, inputs, path_input)
            )
            if mapping:
                tool_node["input_mapping"] = mapping
            nodes.append(tool_node)
            labels[node_id] = str(resource.get("name") or "Tool")[:80]
            transitions.append({"from": previous, "port": previous_port, "to": node_id})
            previous = node_id
            previous_port = "next"
            permissions = grant_required_permissions(
                permissions, resource["required_permissions"]
            )
        pending_tools = []

    if any(step.branches or step.branch_condition for step in ordered):
        return _branched_blueprint_payload(
            plan,
            tools=tools,
            documents=documents,
            extra_outputs=extra_outputs,
            inputs=inputs,
            outputs=outputs,
            path_input=path_input,
            ordered=ordered,
            extra_approvals=extra_approvals,
            warnings=warnings,
            nodes=nodes,
            transitions=transitions,
            labels=labels,
            permissions=permissions,
            used_ids=used_ids,
            previous=previous,
            previous_port=previous_port,
        )

    for step in ordered:
        node, extras, consumed = _compile_step(
            step,
            plan,
            extra_outputs=extra_outputs,
            inputs=inputs,
            outputs=outputs,
            path_input=path_input,
            tools=tools if step.operation_kind == "capability" else [],
            used_ids=used_ids,
            include_all_steps=collapse_models,
            emit_agent_outputs=(
                step.semantic_key.casefold() in terminal_prompts and bool(extra_outputs)
            ),
        )
        if consumed is not None and not any(
            item.operation_kind == "capability" for item in ordered
        ):
            pending_tools = [
                resource
                for resource in pending_tools
                if str(resource["reference"]) != consumed
            ]
        if node is None:
            continue
        node_id = str(node["id"])
        nodes.append(node)
        labels[node_id] = step.name[:80]
        transitions.append({"from": previous, "port": previous_port, "to": node_id})
        component = str(node["component_type"])
        extra_ports = {
            "Condition": ("false",),
            "HumanApproval": ("rejected",),
            "Verifier": ("failed",),
        }.get(component, ())
        success_port = {
            "Condition": "true",
            "HumanApproval": "approved",
            "Verifier": "passed",
        }.get(component, "next")
        for port in extra_ports:
            transitions.append({"from": node_id, "port": port, "to": "output"})
        previous = node_id
        previous_port = success_port
        if node.get("uses"):
            matched = tool_by_ref.get(str(node["uses"]))
            if matched is not None:
                permissions = grant_required_permissions(
                    permissions, matched["required_permissions"]
                )
        nodes.extend(extras)

    for index, prompt in enumerate(extra_approvals):
        node_id = _unique_id(f"approval_{index + 1}", used_ids)
        nodes.append(
            {
                "id": node_id,
                "component_type": "HumanApproval",
                "prompt": prompt,
            }
        )
        labels[node_id] = prompt[:80]
        transitions.append({"from": previous, "port": previous_port, "to": node_id})
        transitions.append({"from": node_id, "port": "rejected", "to": "output"})
        previous = node_id
        previous_port = "approved"

    output_name = next(iter(outputs))
    nodes.append(
        {"id": "output", "component_type": "Output", "output_name": output_name}
    )
    transitions.append({"from": previous, "port": previous_port, "to": "output"})
    labels["output"] = output_name[:80]

    return _finalize_blueprint_payload(
        plan,
        inputs=inputs,
        outputs=outputs,
        nodes=nodes,
        transitions=transitions,
        permissions=permissions,
        documents=documents,
        warnings=warnings,
        positions=positions,
        labels=labels,
    )


def _branched_blueprint_payload(
    plan: AgentSemanticPlanV1,
    *,
    tools: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    extra_outputs: list[str],
    inputs: Mapping[str, Any],
    outputs: Mapping[str, Any],
    path_input: str | None,
    ordered: list[SemanticStepIntent],
    extra_approvals: tuple[str, ...],
    warnings: tuple[str, ...],
    nodes: list[dict[str, Any]],
    transitions: list[dict[str, str]],
    labels: dict[str, str],
    permissions: dict[str, Any],
    used_ids: set[str],
    previous: str,
    previous_port: str,
) -> dict[str, Any]:
    """Compile semantic branches as a DAG, never as an ordered step list."""

    fork = _describe_fork(ordered)
    fork_key = fork.step.semantic_key.casefold()
    terminal_prompts = _terminal_prompt_keys(ordered)
    node_by_key: dict[str, dict[str, Any]] = {}
    for step in ordered:
        try:
            node, extras, consumed = _compile_step(
                step,
                plan,
                extra_outputs=extra_outputs,
                inputs=inputs,
                outputs=outputs,
                path_input=path_input,
                tools=tools if step.operation_kind == "capability" else [],
                used_ids=used_ids,
                include_all_steps=False,
                emit_agent_outputs=(
                    step.semantic_key.casefold() in terminal_prompts
                    and bool(extra_outputs)
                ),
            )
        except (TypeError, ValueError) as exc:
            raise SemanticGraphError(str(exc)) from exc
        if node is None:
            raise SemanticGraphError(
                f"semantic step {step.semantic_key} could not be compiled"
            )
        node_by_key[step.semantic_key.casefold()] = node
        nodes.append(node)
        labels[str(node["id"])] = step.name[:80]
        nodes.extend(extras)
        if consumed is not None:
            matched = next(
                (
                    resource
                    for resource in tools
                    if str(resource["reference"]) == consumed
                ),
                None,
            )
            if matched is not None:
                permissions = grant_required_permissions(
                    permissions, matched["required_permissions"]
                )

    dependents: dict[str, list[SemanticStepIntent]] = {
        step.semantic_key.casefold(): [] for step in ordered
    }
    for step in ordered:
        for dependency in step.depends_on:
            dependent = dependents.get(dependency.casefold())
            if dependent is None:
                raise SemanticGraphError(
                    f"semantic dependency {dependency} is not present in the graph"
                )
            dependent.append(step)

    output_name = next(iter(outputs))
    global_approval_ids: list[str] = []
    for index, prompt in enumerate(extra_approvals):
        node_id = _unique_id(f"approval_{index + 1}", used_ids)
        global_approval_ids.append(node_id)
        nodes.append(
            {
                "id": node_id,
                "component_type": "HumanApproval",
                "prompt": prompt,
            }
        )
        labels[node_id] = prompt[:80]
    final_success = global_approval_ids[0] if global_approval_ids else "output"

    def branch_roots(branch_key: str) -> list[SemanticStepIntent]:
        return [
            step
            for step in ordered
            if step.branch_condition.casefold() == fork_key
            and step.branch_key.casefold() == branch_key.casefold()
            and not any(
                dependency.casefold() != fork_key for dependency in step.depends_on
            )
        ]

    branch_targets: dict[str, str] = {}
    fork_node_id = str(node_by_key[fork_key]["id"])
    branch_labels: dict[str, dict[str, str]] = {}
    if fork.step.operation_kind == "condition":
        branch_labels[fork_node_id] = {}
    for port, branch_key, label in zip(fork.ports, fork.keys, fork.labels, strict=True):
        roots = branch_roots(branch_key)
        if len(roots) > 1:
            raise SemanticGraphError(
                f"branch {branch_key} has multiple roots; add a merge step"
            )
        if roots:
            target = str(node_by_key[roots[0].semantic_key.casefold()]["id"])
        else:
            shared = [
                step for step in dependents[fork_key] if not step.branch_condition
            ]
            if len(shared) > 1:
                raise SemanticGraphError(
                    f"{fork.step.semantic_key} has ambiguous shared successors"
                )
            target = (
                str(node_by_key[shared[0].semantic_key.casefold()]["id"])
                if shared
                else final_success
            )
        branch_targets[port] = target
        if fork.step.operation_kind == "condition":
            branch_labels[fork_node_id][port] = label

    def success_target(step: SemanticStepIntent) -> str:
        children = dependents[step.semantic_key.casefold()]
        if step.semantic_key.casefold() == fork_key:
            return final_success
        if len(children) > 1:
            raise SemanticGraphError(
                f"semantic step {step.semantic_key} has multiple successors on "
                "one runtime port"
            )
        if children:
            return str(node_by_key[children[0].semantic_key.casefold()]["id"])
        return final_success

    roots = [
        step for step in ordered if not step.depends_on and not step.branch_condition
    ]
    if len(roots) != 1:
        raise SemanticGraphError(
            "branched graph needs exactly one shared entry path before the fork"
        )
    transitions.append(
        {
            "from": previous,
            "port": previous_port,
            "to": str(node_by_key[roots[0].semantic_key.casefold()]["id"]),
        }
    )

    for step in ordered:
        node = node_by_key[step.semantic_key.casefold()]
        node_id = str(node["id"])
        component = str(node["component_type"])
        if node_id == fork_node_id:
            transitions.extend(
                {"from": node_id, "port": port, "to": branch_targets[port]}
                for port in fork.ports
            )
        elif component == "HumanApproval":
            transitions.append(
                {"from": node_id, "port": "approved", "to": success_target(step)}
            )
            transitions.append({"from": node_id, "port": "rejected", "to": "output"})
        elif component == "Verifier":
            transitions.append(
                {"from": node_id, "port": "passed", "to": success_target(step)}
            )
            transitions.append({"from": node_id, "port": "failed", "to": "output"})
        else:
            transitions.append(
                {"from": node_id, "port": "next", "to": success_target(step)}
            )

    for index, node_id in enumerate(global_approval_ids):
        next_node = (
            global_approval_ids[index + 1]
            if index + 1 < len(global_approval_ids)
            else "output"
        )
        transitions.append({"from": node_id, "port": "approved", "to": next_node})
        transitions.append({"from": node_id, "port": "rejected", "to": "output"})

    nodes.append(
        {"id": "output", "component_type": "Output", "output_name": output_name}
    )
    labels["output"] = output_name[:80]
    return _finalize_blueprint_payload(
        plan,
        inputs=inputs,
        outputs=outputs,
        nodes=nodes,
        transitions=transitions,
        permissions=permissions,
        documents=documents,
        warnings=warnings,
        positions={},
        labels=labels,
        branch_labels=branch_labels,
    )


_SUCCESS_IMAGE_PORTS = frozenset({"next", "approved", "true", "passed"})


def _wire_is_image(wire: Any) -> bool:
    if wire == "image":
        return True
    return isinstance(wire, Mapping) and wire.get("artifact_kind") == "image"


def _image_generation_prompt(name: str, description: str, goal: str) -> str:
    lines = [
        f"Generate the image for {name}.",
        description or goal,
        "Use the Agent inputs and earlier working notes in this run as the brief.",
    ]
    return "\n".join(line for line in lines if line)


def _attach_image_outputs(
    plan: AgentSemanticPlanV1,
    *,
    nodes: list[dict[str, Any]],
    transitions: list[dict[str, str]],
    labels: dict[str, str],
    outputs: Mapping[str, Any],
    used_ids: set[str],
) -> None:
    """Compile declared image outputs onto model.image nodes."""

    already = {
        name
        for node in nodes
        for name, wire in dict(node.get("outputs") or {}).items()
        if _wire_is_image(wire)
    }
    images = [
        (name, wire)
        for name, wire in outputs.items()
        if _wire_is_image(wire) and name not in already
    ]
    if not images:
        return
    descriptions = {
        name: item.description for name, item in zip(outputs, plan.outputs, strict=True)
    }
    models = [node for node in nodes if node.get("component_type") == "Model"]
    non_image = [name for name, wire in outputs.items() if not _wire_is_image(wire)]
    if (
        not non_image
        and len(images) == 1
        and len(models) == 1
        and models[0].get("model_ref") != "model.image"
    ):
        name, wire = images[0]
        models[0]["model_ref"] = "model.image"
        models[0]["outputs"] = {name: wire}
        models[0]["system_prompt"] = _image_generation_prompt(
            name, descriptions.get(name, ""), plan.goal
        )
        return
    incoming = [
        edge
        for edge in transitions
        if edge.get("to") == "output" and edge.get("port") in _SUCCESS_IMAGE_PORTS
    ]
    if not incoming:
        return
    previous: str | None = None
    for name, wire in images:
        node_id = _unique_id(f"render_{_node_id_from_key(name)}", used_ids)
        nodes.append(
            {
                "id": node_id,
                "component_type": "Model",
                "model_ref": "model.image",
                "system_prompt": _image_generation_prompt(
                    name, descriptions.get(name, ""), plan.goal
                ),
                "outputs": {name: wire},
            }
        )
        labels[node_id] = name[:80]
        if previous is None:
            for edge in incoming:
                edge["to"] = node_id
        else:
            transitions.append({"from": previous, "port": "next", "to": node_id})
        previous = node_id
    if previous is not None:
        transitions.append({"from": previous, "port": "next", "to": "output"})


def _finalize_blueprint_payload(
    plan: AgentSemanticPlanV1,
    *,
    inputs: Mapping[str, Any],
    outputs: Mapping[str, Any],
    nodes: list[dict[str, Any]],
    transitions: list[dict[str, str]],
    permissions: dict[str, Any],
    documents: list[dict[str, Any]],
    warnings: tuple[str, ...],
    positions: Mapping[str, Mapping[str, int]],
    labels: Mapping[str, str],
    branch_labels: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    used_ids = {str(node["id"]) for node in nodes}
    resolved_labels = dict(labels)
    _attach_image_outputs(
        plan,
        nodes=nodes,
        transitions=transitions,
        labels=resolved_labels,
        outputs=outputs,
        used_ids=used_ids,
    )
    labels = resolved_labels
    verifier_checks: list[str] = []
    for node in nodes:
        if node.get("component_type") == "Verifier":
            verifier_checks.extend(str(item) for item in node.get("checks") or [])
    bindings: dict[str, dict[str, Any]] = {}
    for index, document in enumerate(documents):
        identity = f"knowledge_{index + 1}"
        bindings[identity] = {
            "kind": "knowledge",
            "reference": knowledge_reference(document),
            "x": -260,
            "y": 80 + index * 140,
        }
    component_types = list(dict.fromkeys(str(node["component_type"]) for node in nodes))
    if any(node["component_type"] == "AgentCall" for node in nodes):
        raise SemanticGraphError("AgentCall is not allowed inside an Agent graph")
    condition_expressions = {
        str(node["id"]): str(node["expression"])
        for node in nodes
        if node.get("component_type") == "Condition" and node.get("expression")
    }
    note = _note_text(
        plan,
        branch_labels=branch_labels or {},
        condition_expressions=condition_expressions,
    )
    ui: dict[str, Any] = {
        "positions": dict(positions),
        "labels": dict(labels),
        "notes": {"note_intro": default_canvas_note(note)},
    }
    if bindings:
        ui["bindings"] = bindings
    if branch_labels:
        ui["branch_labels"] = {
            condition_id: dict(port_labels)
            for condition_id, port_labels in branch_labels.items()
        }
    ui = attach_default_canvas_note(ui, note)
    _ = warnings
    try:
        data_edges = attach_compiled_dataflow(
            nodes=nodes,
            transitions=transitions,
            inputs=inputs,
            outputs=outputs,
            steps=_steps_by_node(plan, nodes),
        )
    except DataflowCompileError as exc:
        raise SemanticGraphError(str(exc)) from exc
    payload = {
        "schema_version": "1.0",
        "goal": plan.goal,
        "inputs": dict(inputs),
        "outputs": dict(outputs),
        "nodes": nodes,
        "transitions": transitions,
        "required_capabilities": {
            "component_types": component_types,
            "tool_refs": [
                str(node["uses"])
                for node in nodes
                if node.get("component_type") == "Tool" and node.get("uses")
            ],
            "skill_refs": [],
            "policy_refs": [],
        },
        "requested_permissions": permissions,
        "verification": {
            "required": bool(verifier_checks),
            "checks": list(dict.fromkeys(verifier_checks)),
        },
        "ui_suggestions": ui,
    }
    if data_edges:
        payload["data_edges"] = data_edges
    return payload


def _steps_by_node(
    plan: AgentSemanticPlanV1, nodes: list[dict[str, Any]]
) -> dict[str, SemanticStepIntent]:
    remaining = list(plan.step_intents)
    mapping: dict[str, SemanticStepIntent] = {}
    for node in nodes:
        node_id = str(node["id"])
        match: SemanticStepIntent | None = None
        for step in remaining:
            expected = _node_id_from_key(step.semantic_key)
            if node_id == expected or node_id.startswith(f"{expected}_"):
                match = step
                break
        if match is not None:
            mapping[node_id] = match
            remaining.remove(match)
    return mapping


def _step_is_image_generation(step: SemanticStepIntent) -> bool:
    return bool(step.outputs) and all(item.type == "image" for item in step.outputs)


def _compile_step(
    step: SemanticStepIntent,
    plan: AgentSemanticPlanV1,
    *,
    extra_outputs: list[str],
    inputs: Mapping[str, Any],
    outputs: Mapping[str, Any],
    path_input: str | None,
    tools: list[dict[str, Any]],
    used_ids: set[str],
    include_all_steps: bool = False,
    emit_agent_outputs: bool = True,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    node_id = _unique_id(_node_id_from_key(step.semantic_key), used_ids)
    kind = step.operation_kind
    if kind == "model":
        node: dict[str, Any] = {
            "id": node_id,
            "component_type": "Model",
            "model_ref": (
                "model.image" if _step_is_image_generation(step) else "model.primary"
            ),
            "system_prompt": _model_prompt(
                plan,
                step,
                extra_outputs,
                include_all_steps=include_all_steps,
                emit_agent_outputs=emit_agent_outputs,
            ),
        }
        attach_step_ports(
            node,
            step,
            inputs=inputs,
            outputs=outputs,
            emit_agent_outputs=emit_agent_outputs,
        )
        return node, [], None
    if kind == "capability":
        resource = _matching_tool(step, tools)
        if resource is None:
            return None, [], None
        node = _resource_node(resource, node_id)
        mapping: dict[str, str]
        if node["component_type"] == "Tool":
            mapping = {"path": path_input} if path_input else {}
        else:
            mapping = _component_input_mapping(resource, inputs, path_input)
        if mapping:
            node["input_mapping"] = mapping
        attach_step_ports(
            node,
            step,
            inputs=inputs,
            outputs=outputs,
            emit_agent_outputs=False,
        )
        return node, [], str(resource["reference"])
    if kind == "transform":
        mapping = _transform_mapping(step, inputs, outputs)
        node = {
            "id": node_id,
            "component_type": "Transform",
            "mapping": mapping,
        }
        attach_step_ports(
            node,
            step,
            inputs=inputs,
            outputs=outputs,
            emit_agent_outputs=True,
        )
        return node, [], None
    if kind == "condition":
        return (
            {
                "id": node_id,
                "component_type": "Condition",
                "expression": _condition_expression(step, inputs),
            },
            [],
            None,
        )
    if kind == "approval":
        return (
            {
                "id": node_id,
                "component_type": "HumanApproval",
                "prompt": step.purpose,
            },
            [],
            None,
        )
    if kind == "verification":
        checks = _step_verifier_checks(step)
        if checks:
            return (
                {
                    "id": node_id,
                    "component_type": "Verifier",
                    "checks": list(checks),
                },
                [],
                None,
            )
        return (
            {
                "id": node_id,
                "component_type": "Model",
                "model_ref": "model.primary",
                "system_prompt": _model_prompt(
                    plan,
                    step,
                    extra_outputs,
                    include_all_steps=include_all_steps,
                    emit_agent_outputs=emit_agent_outputs,
                ),
            },
            [],
            None,
        )
    return None, [], None


def _resource_node(resource: Mapping[str, Any], node_id: str) -> dict[str, Any]:
    is_custom_component = (
        resource.get("kind") == "component"
        and resource.get("component_class") == "composite"
    )
    return {
        "id": node_id,
        "component_type": "CustomComponent" if is_custom_component else "Tool",
        "uses": resource["reference"],
    }


def _component_input_mapping(
    resource: Mapping[str, Any], inputs: Mapping[str, Any], path_input: str | None
) -> dict[str, str]:
    spec = resource.get("spec")
    component_inputs = spec.get("inputs") if isinstance(spec, Mapping) else None
    if not isinstance(component_inputs, Mapping):
        return {}
    mapping = {name: name for name in component_inputs if name in inputs}
    if path_input is None or len(mapping) == len(component_inputs):
        return mapping
    candidates = [
        name
        for name, field in component_inputs.items()
        if name not in mapping
        and (
            name == "path"
            or (
                isinstance(field, Mapping)
                and field.get("type") == "string"
                and "path" in name.casefold()
            )
        )
    ]
    if len(candidates) == 1:
        mapping[candidates[0]] = path_input
    return mapping


def _ordered_steps(
    steps: list[SemanticStepIntent], *, collapse_models: bool
) -> list[SemanticStepIntent]:
    if collapse_models:
        models = [step for step in steps if step.operation_kind == "model"]
        return models[:1]
    by_key = {step.semantic_key.casefold(): step for step in steps}
    remaining = {step.semantic_key.casefold() for step in steps}
    ordered: list[SemanticStepIntent] = []
    while remaining:
        ready = [
            step
            for step in steps
            if step.semantic_key.casefold() in remaining
            and all(item.casefold() not in remaining for item in step.depends_on)
        ]
        if not ready:
            break
        next_step = ready[0]
        ordered.append(next_step)
        remaining.remove(next_step.semantic_key.casefold())
    leftover = [by_key[key] for key in remaining if key in by_key]
    return ordered + leftover


def _resolve_knowledge(
    plan: AgentSemanticPlanV1, context: BuilderProjectContext
) -> tuple[list[dict[str, Any]], str | None]:
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for intent in plan.knowledge_intents:
        knowledge_match = resolve_knowledge(list(context.knowledge), intent)
        if (
            knowledge_match.status == "resolved"
            and knowledge_match.selected is not None
        ):
            reference = knowledge_reference(knowledge_match.selected)
            if reference not in seen:
                documents.append(knowledge_match.selected)
                seen.add(reference)
            continue
        if knowledge_match.status == "ambiguous":
            return [], _clarify(plan.goal, knowledge_match.candidates, knowledge=True)
    return documents, None


def _resolve_capability_intents(
    intents: tuple[str, ...],
    context: BuilderProjectContext,
    *,
    require_unresolved: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    tools: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    seen: set[str] = set()
    for intent in intents:
        match = resolve_capability_intent(
            list(context.project_resources),
            list(context.catalog_resources),
            intent,
        )
        if match.status == "resolved" and match.selected is not None:
            reference = str(match.selected["reference"])
            if reference not in seen:
                tools.append(match.selected)
                seen.add(reference)
            continue
        if match.status == "ambiguous":
            return (
                [],
                [],
                _clarify(intent, match.candidates, knowledge=False),
            )
        if match.status == "unbound":
            if _PROJECT_SCOPED_READ.search(intent) or require_unresolved:
                missing.append(
                    _missing_capability(
                        "tool",
                        FILESYSTEM_READ_RESOURCE_ID,
                        "Tool is not bound to this Project",
                    )
                )
            elif _EXTERNAL_TOOL.search(intent):
                missing.append(
                    _missing_capability(
                        "tool",
                        intent,
                        "Requested capability is not bound to this Project",
                    )
                )
            continue
        if _is_regurgitated_policy(intent):
            continue
        if _EXTERNAL_TOOL.search(intent) or require_unresolved:
            missing.append(
                _missing_capability(
                    "tool",
                    intent,
                    "Requested capability is not bound to this Project",
                )
            )
    return tools, missing, None


def _note_text(
    plan: AgentSemanticPlanV1,
    *,
    branch_labels: Mapping[str, Mapping[str, str]] | None = None,
    condition_expressions: Mapping[str, str] | None = None,
) -> str:
    chinese = bool(_CJK.search(plan.goal) or _CJK.search(plan.suggested_name))
    purpose = "目的" if chinese else "Purpose"
    inputs = "输入" if chinese else "Inputs"
    outputs = "输出" if chinese else "Outputs"
    steps_label = "主要步骤" if chinese else "Main steps"
    lines = [
        plan.suggested_name,
        "",
        f"{purpose}: {plan.description or plan.goal}",
        "",
        f"{inputs}: " + "、".join(item.name for item in plan.inputs),
        f"{outputs}: " + "、".join(item.name for item in plan.outputs),
        "",
        f"{steps_label}:",
    ]
    named = [step.name for step in plan.step_intents] or list(plan.steps)
    lines.extend(f"{index}. {name}" for index, name in enumerate(named, start=1))
    if branch_labels:
        lines.extend(("", "Branches:"))
        for condition_id, ports in branch_labels.items():
            labels = ", ".join(
                f"{port}={label}" for port, label in sorted(ports.items())
            )
            lines.append(f"{condition_id}: {labels}")
    if condition_expressions:
        lines.extend(("", "Executable conditions:"))
        lines.extend(
            f"{condition_id}: {expression}"
            for condition_id, expression in sorted(condition_expressions.items())
        )
    return "\n".join(lines)[:4000]


def _terminal_prompt_keys(steps: list[SemanticStepIntent]) -> set[str]:
    """Model steps that must emit the Agent output contract.

    Earlier model steps only hand a working note to the next node. Forcing
    every step to emit the final JSON makes intermediate nodes fail or
    overwrite the real result.
    """

    prompt_steps = [
        step
        for step in steps
        if step.operation_kind == "model"
        or (step.operation_kind == "verification" and not _step_verifier_checks(step))
    ]
    keys = {step.semantic_key.casefold() for step in prompt_steps}
    if not keys:
        return set()
    by_key = {step.semantic_key.casefold(): step for step in steps}

    def model_ancestors(step: SemanticStepIntent, seen: set[str]) -> set[str]:
        found: set[str] = set()
        for dependency in step.depends_on:
            parent_key = dependency.casefold()
            if parent_key in seen:
                continue
            parent = by_key.get(parent_key)
            if parent is None:
                continue
            seen.add(parent_key)
            if parent_key in keys:
                found.add(parent_key)
            else:
                found |= model_ancestors(parent, seen)
        return found

    covered: set[str] = set()
    for step in prompt_steps:
        covered |= model_ancestors(step, set())
    uncovered = keys - covered
    if uncovered:
        return uncovered
    return {prompt_steps[-1].semantic_key.casefold()}


def _predecessor_note_lines(
    plan: AgentSemanticPlanV1, step: SemanticStepIntent
) -> list[str]:
    by_key = {item.semantic_key.casefold(): item for item in plan.step_intents}
    notes: list[str] = []
    seen: set[str] = set()
    pending = list(step.depends_on)
    while pending:
        key = pending.pop().casefold()
        if key in seen:
            continue
        seen.add(key)
        parent = by_key.get(key)
        if parent is None:
            continue
        pending.extend(parent.depends_on)
        if parent.operation_kind in {"model", "transform", "capability"} or (
            parent.operation_kind == "verification"
            and not _step_verifier_checks(parent)
        ):
            notes.append(f"- {parent.semantic_key}: {parent.name}")
    if not notes:
        return []
    return [
        "You will receive Agent inputs and these earlier working notes by name:",
        *notes,
        "Use the connected typed ports. Do not ask the user follow-up questions.",
    ]


def _model_prompt(
    plan: AgentSemanticPlanV1,
    step: SemanticStepIntent,
    extra_outputs: list[str],
    *,
    include_all_steps: bool = False,
    emit_agent_outputs: bool = True,
) -> str:
    lines = [
        f"You are {step.name}.",
        f"Purpose: {step.purpose or plan.description}",
        f"Goal: {plan.goal}",
    ]
    if include_all_steps:
        lines.append("Steps:")
        lines.extend(
            f"{index}. {item}" for index, item in enumerate(plan.steps, start=1)
        )
    if step.inputs:
        lines.append("Available inputs for this node:")
        used_in: set[str] = set()
        for item in step.inputs:
            slug = _field_slug(item.name, used_in, "input")
            extra = f": {item.description}" if item.description else ""
            lines.append(
                f"- {slug} ({item.type}{'[]' if item.multiple else ''}){extra}"
            )
    else:
        lines.append("Available Agent inputs:")
        used_in = set()
        for item in plan.inputs:
            slug = _field_slug(item.name, used_in, "input")
            extra = f": {item.description}" if item.description else ""
            lines.append(
                f"- {slug} ({item.type}{'[]' if item.multiple else ''}){extra}"
            )
    lines.extend(_predecessor_note_lines(plan, step))
    node_outputs = step.outputs or (tuple(plan.outputs) if emit_agent_outputs else ())
    if node_outputs:
        used_out: set[str] = set()
        lines.append("Expected outputs for this node:")
        for item in node_outputs:
            slug = _field_slug(item.name, used_out, "output")
            extra = f": {item.description}" if item.description else ""
            lines.append(
                f"- {slug} ({item.type}{'[]' if item.multiple else ''}){extra}"
            )
        if (
            len(node_outputs) == 1
            and node_outputs[0].type == "string"
            and not node_outputs[0].multiple
        ):
            lines.append("Return the single string output as plain text.")
        elif not _step_is_image_generation(step):
            if emit_agent_outputs and not step.outputs:
                lines.append(
                    "Return one JSON object with exactly these declared fields; do not "
                    "rename, omit, or add fields."
                )
            else:
                lines.append(
                    "Return one JSON object with exactly these node output fields; "
                    "do not rename, omit, or add fields. Do not return unrelated "
                    "Agent-wide fields this node does not produce."
                )
    elif not emit_agent_outputs:
        lines.append(
            "Return only this step's typed working result for the next node. "
            "Do not return the final Agent output JSON."
        )
    else:
        lines.append(
            "Return the complete declared Agent output contract and preserve its "
            "field names and types:"
        )
        lines.extend(f"- {item}" for item in extra_outputs)
        if (
            len(plan.outputs) == 1
            and plan.outputs[0].type == "string"
            and not plan.outputs[0].multiple
        ):
            lines.append("Return the single string output as plain text.")
        else:
            lines.append(
                "Return one JSON object with exactly these declared fields; do not "
                "rename, omit, or add fields."
            )
    if plan.success_criteria:
        lines.append("Success:")
        lines.extend(f"- {item}" for item in plan.success_criteria)
    if plan.user_constraints:
        lines.append("Constraints:")
        lines.extend(f"- {item}" for item in plan.user_constraints)
    return "\n".join(lines)


def _transform_mapping(
    step: SemanticStepIntent, inputs: Mapping[str, Any], outputs: Mapping[str, Any]
) -> dict[str, str]:
    step_outputs = (
        {_port_from_field(item.name): item for item in step.outputs}
        if step.outputs
        else None
    )
    step_inputs = (
        {_port_from_field(item.name): item for item in step.inputs}
        if step.inputs
        else {}
    )
    declared_outputs = (
        {name: name for name in step_outputs}
        if step_outputs
        else {str(name): str(name) for name in outputs}
    )
    declared_inputs = {
        **{str(name).casefold(): str(name) for name in inputs},
        **{name.casefold(): name for name in step_inputs},
    }
    if step.output_mapping:
        requested = dict(step.output_mapping)
    else:
        purpose = step.purpose.strip()
        if "{{" in purpose and "}}" in purpose and ":" in purpose:
            name, template = purpose.split(":", 1)
            slug = _SLUG_NOISE.sub("-", name.casefold()).strip("-")
            requested = {slug: template.strip()} if slug else {}
        else:
            if len(declared_outputs) > 1:
                raise ValueError(
                    "code=transform_output_mapping_required "
                    f"path=step_intents[{step.semantic_key}].output_mapping "
                    "expected=each_declared_output_mapped actual=missing"
                )
            target = next(iter(declared_outputs))
            source = next(iter(declared_inputs.values()), "")
            if not source:
                raise ValueError(
                    "code=transform_input_not_declared "
                    f"path=step_intents[{step.semantic_key}].output_mapping "
                    "expected=literal_or_declared_input actual=missing"
                )
            requested = {target: f"{{{{{source}}}}}"}

    output_names = {str(name).casefold(): str(name) for name in declared_outputs}
    mapping: dict[str, str] = {}
    for target, template in requested.items():
        wire_target = output_names.get(target.casefold())
        if wire_target is None:
            raise ValueError(
                "code=transform_output_not_declared "
                f"path=step_intents[{step.semantic_key}].output_mapping[{target}] "
                f"expected=declared_output actual={target} "
                f"allowed_outputs={','.join(output_names.values())}"
            )
        for token in re.findall(r"\{\{([^{}]+)\}\}", template):
            wire_source = _lookup_declared_input(token, declared_inputs)
            if wire_source is None:
                path = (
                    f"step_intents[{step.semantic_key}].output_mapping[{wire_target}]"
                )
                raise ValueError(
                    "code=transform_input_not_declared "
                    f"path={path} "
                    f"expected=literal_or_declared_input actual={token} "
                    f"allowed_inputs={','.join(declared_inputs.values()) or 'none'}"
                )
        mapping[wire_target] = template
    return mapping


def _lookup_declared_input(token: str, declared: Mapping[str, str]) -> str | None:
    folded = token.casefold()
    if folded in declared:
        return declared[folded]
    dashed = folded.replace("_", "-")
    if dashed in declared:
        return declared[dashed]
    underscored = folded.replace("-", "_")
    if underscored in declared:
        return declared[underscored]
    return None


def _port_from_field(name: str) -> str:
    folded = _SLUG_NOISE.sub("-", name.casefold()).strip("-")
    return folded or "port"


def _condition_expression(step: SemanticStepIntent, inputs: Mapping[str, Any]) -> str:
    expression = step.condition_expression.strip()
    allowed_inputs = {str(name).casefold(): str(name) for name in inputs}
    path = f"step_intents[{step.semantic_key}].condition_expression"
    if not expression:
        raise ValueError(
            "code=condition_expression_required "
            f"path={path} expected=declared_input_comparison "
            "actual=missing "
            f"allowed_inputs={','.join(allowed_inputs.values()) or 'none'}"
        )
    try:
        parsed = parse_condition_expression(expression, field_name=path)
    except ContractValidationError as exc:
        raise ValueError(
            "code=condition_expression_invalid "
            f"path={path} expected=declared_input_comparison actual={expression} "
            f"allowed_inputs={','.join(allowed_inputs.values()) or 'none'}"
        ) from exc
    field = allowed_inputs.get(parsed.field.casefold())
    if field is None:
        raise ValueError(
            "code=condition_input_not_declared "
            f"path={path} expected=declared_agent_input actual={parsed.field} "
            f"allowed_inputs={','.join(allowed_inputs.values()) or 'none'}"
        )
    return f"{field} {parsed.operator} {parsed.literal_token}"


def _step_verifier_checks(step: SemanticStepIntent) -> tuple[str, ...]:
    if _OUTPUT_NOT_EMPTY.search(step.purpose):
        return ("output.not_empty",)
    return ()


def _verification_warnings(plan: AgentSemanticPlanV1) -> tuple[str, ...]:
    warnings: list[str] = []
    for step in plan.step_intents:
        if step.operation_kind != "verification":
            continue
        if not _OUTPUT_NOT_EMPTY.search(step.purpose):
            warnings.append(f"unsupported_verification:{step.semantic_key}")
    for criterion in plan.success_criteria:
        if not _OUTPUT_NOT_EMPTY.search(criterion):
            warnings.append(f"success_criterion_not_verifier:{criterion}")
    return tuple(warnings)


def _node_id_from_key(key: str) -> str:
    folded = _SLUG_NOISE.sub("_", key.casefold()).strip("_")
    if not folded or not folded[0].isalpha():
        folded = "step"
    return folded[:63]


def _unique_id(base: str, used: set[str]) -> str:
    candidate = base if base not in _RESERVED_NODE_IDS else f"{base}_node"
    if candidate not in used:
        used.add(candidate)
        return candidate
    index = 2
    while True:
        suffix = f"_{index}"
        next_id = f"{candidate[: 63 - len(suffix)]}{suffix}"
        if next_id not in used:
            used.add(next_id)
            return next_id
        index += 1


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


_CAPABILITY_NEEDLES = {
    "pdf_parser": ("pdf_parser", "pdf-parser", "parse-pdf"),
    "pdf_renderer": ("pdf_renderer", "pdf-renderer", "render-pdf"),
    "image_generation": (
        "image_generation",
        "image-generation",
        "text-to-image",
    ),
}


def _field_wire(field: SemanticField) -> str | dict[str, Any]:
    return field_wire(field)


def _merge_tools(
    current: list[dict[str, Any]], extra: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged = list(current)
    seen = {str(item.get("reference") or "") for item in merged}
    for item in extra:
        reference = str(item.get("reference") or "")
        if reference and reference not in seen:
            merged.append(item)
            seen.add(reference)
    return merged


def _is_filesystem_tool(resource: Mapping[str, Any]) -> bool:
    reference = str(resource.get("reference") or resource.get("resource_id") or "")
    return "filesystem" in reference.casefold()


def _provides_capability(resource: Mapping[str, Any], capability: str) -> bool:
    haystack = " ".join(
        str(resource.get(key) or "")
        for key in ("resource_id", "reference", "name", "slug")
    ).casefold()
    return any(needle in haystack for needle in _CAPABILITY_NEEDLES[capability])


def _find_project_capability(
    context: BuilderProjectContext, capability: str
) -> dict[str, Any] | None:
    for resource in context.project_resources:
        if resource.get("scope") != "project":
            continue
        if _provides_capability(resource, capability):
            return dict(resource)
    return None


def _modality_requirements(
    plan: AgentSemanticPlanV1, context: BuilderProjectContext
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[str, ...]]:
    missing: list[dict[str, Any]] = []
    tools: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()

    def require_capability(capability: str, reason: str) -> None:
        if capability in seen:
            return
        seen.add(capability)
        resource = _find_project_capability(context, capability)
        if resource is not None:
            tools.append(resource)
            return
        missing.append(_missing_capability(capability, capability, reason))

    for item in plan.inputs:
        if item.type == "image":
            warnings.append("requires_runtime_image_input")
        elif item.type in {"pdf", "document", "file"}:
            warnings.append("requires_runtime_document_extract")
        elif item.type in {"audio", "video"}:
            missing.append(
                _missing_capability(
                    "unsupported_modality",
                    item.type,
                    "Audio/video runtime adapters are not enabled",
                )
            )
    for item in plan.outputs:
        if item.type == "pdf":
            require_capability(
                "pdf_renderer", "PDF rendering is not bound to this Project"
            )
        elif item.type == "image":
            warnings.append("requires_runtime_image_output")
        elif item.type in {"audio", "video"}:
            missing.append(
                _missing_capability(
                    "unsupported_modality",
                    item.type,
                    "Audio/video runtime adapters are not enabled",
                )
            )
    return missing, tools, tuple(dict.fromkeys(warnings))
