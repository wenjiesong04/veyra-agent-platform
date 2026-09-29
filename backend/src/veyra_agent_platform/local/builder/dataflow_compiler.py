"""Compile SemanticPlan step I/O into typed node ports and data edges.

Control flow stays on transitions. This module never invents canonical hashes.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.dataflow import (
    DataEdge,
    PortRef,
    parse_data_edges,
    types_compatible,
    validate_data_edges,
)
from veyra_agent_platform.contracts.semantic_plan import (
    SemanticField,
    SemanticStepIntent,
)
from veyra_agent_platform.contracts.typed_io import (
    ARTIFACT_KINDS,
    TypedField,
    parse_typed_fields,
)


def _typed_fields(value: Any, field: str) -> Mapping[str, TypedField]:
    if not value:
        return {}
    return parse_typed_fields(value, field)


_SLUG_NOISE = re.compile(r"[^a-z0-9]+")
_DATA_NODES = frozenset({"Model", "Agent", "Transform", "Tool", "CustomComponent"})


class DataflowCompileError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


def attach_compiled_dataflow(
    *,
    nodes: list[dict[str, Any]],
    transitions: list[dict[str, str]],
    inputs: Mapping[str, Any],
    outputs: Mapping[str, Any],
    steps: Mapping[str, SemanticStepIntent] | None = None,
) -> list[dict[str, Any]]:
    """Mutate node ports when missing, then return canonical data edges."""

    step_by_node = steps or {}
    _ensure_ports(nodes, transitions, inputs, outputs, step_by_node)
    edges = _synthesize_edges(nodes, transitions, inputs, outputs, step_by_node)
    adapter = [_NodeView(node) for node in nodes]
    parsed_inputs = parse_typed_fields(dict(inputs), "inputs")
    parsed_outputs = parse_typed_fields(dict(outputs), "outputs")
    try:
        validate_data_edges(
            inputs=parsed_inputs,
            outputs=parsed_outputs,
            nodes=adapter,
            edges=edges,
        )
    except ContractValidationError as exc:
        raise DataflowCompileError(str(exc)) from exc
    return [edge.to_dict() for edge in edges]


def _is_image_wire(wire: Any) -> bool:
    return wire == "image" or (
        isinstance(wire, dict) and wire.get("artifact_kind") == "image"
    )


def attach_step_ports(
    node: dict[str, Any],
    step: SemanticStepIntent,
    *,
    inputs: Mapping[str, Any],
    outputs: Mapping[str, Any],
    emit_agent_outputs: bool,
) -> None:
    kind = str(node.get("component_type") or "")
    if kind not in _DATA_NODES:
        return
    if step.inputs and "inputs" not in node:
        node["inputs"] = _fields_wire(step.inputs)
    if step.outputs and "outputs" not in node:
        node["outputs"] = _fields_wire(step.outputs)
        return
    if emit_agent_outputs and "outputs" not in node:
        non_image = {
            name: wire
            for name, wire in dict(outputs).items()
            if not _is_image_wire(wire)
        }
        node["outputs"] = non_image or dict(outputs)
        return
    if kind in {"Model", "Agent"} and "outputs" not in node:
        node["outputs"] = {
            "working-result": {
                "type": "object",
                "description": (step.purpose or step.name)[:240],
            }
        }
    if kind == "Transform" and "outputs" not in node:
        node["outputs"] = dict(outputs)


def field_wire(field: SemanticField) -> str | dict[str, Any]:
    payload: dict[str, Any] = {}
    if field.type in ARTIFACT_KINDS:
        payload["type"] = "artifact"
        payload["artifact_kind"] = field.type
    else:
        payload["type"] = field.type
    if field.multiple:
        payload["multiple"] = True
    if not field.required:
        payload["required"] = False
    if field.description:
        payload["description"] = field.description
    if len(payload) == 1 and payload.get("type") == field.type:
        return field.type
    if (
        len(payload) == 2
        and payload.get("type") == "artifact"
        and "artifact_kind" in payload
        and not field.multiple
        and field.required
        and not field.description
    ):
        return field.type
    return payload


def _fields_wire(fields: Sequence[SemanticField]) -> dict[str, Any]:
    used: set[str] = set()
    wired: dict[str, Any] = {}
    for item in fields:
        name = _port_slug(item.name, used)
        wired[name] = field_wire(item)
    return wired


def _ensure_ports(
    nodes: list[dict[str, Any]],
    transitions: list[dict[str, str]],
    inputs: Mapping[str, Any],
    outputs: Mapping[str, Any],
    steps: Mapping[str, SemanticStepIntent],
) -> None:
    by_id = {str(node["id"]): node for node in nodes}
    predecessors = _data_predecessors(nodes, transitions)
    terminals = _terminal_data_nodes(nodes, transitions)
    for node in nodes:
        kind = str(node.get("component_type") or "")
        if kind not in _DATA_NODES:
            continue
        node_id = str(node["id"])
        step = steps.get(node_id)
        if "outputs" not in node:
            if node_id in terminals:
                if str(node.get("model_ref") or "") == "model.image":
                    images = {
                        name: wire
                        for name, wire in dict(outputs).items()
                        if _is_image_wire(wire)
                    }
                    node["outputs"] = images or dict(outputs)
                else:
                    non_image = {
                        name: wire
                        for name, wire in dict(outputs).items()
                        if not _is_image_wire(wire)
                    }
                    node["outputs"] = non_image or {
                        "working-result": {
                            "type": "object",
                            "description": node_id,
                        }
                    }
            elif step is not None:
                attach_step_ports(
                    node,
                    step,
                    inputs=inputs,
                    outputs=outputs,
                    emit_agent_outputs=False,
                )
            else:
                node["outputs"] = {
                    "working-result": {"type": "object", "description": node_id}
                }
        if "inputs" in node:
            continue
        if kind in {"Tool", "CustomComponent"}:
            mapping = node.get("input_mapping") or {}
            inferred = {}
            for port, source in dict(mapping).items():
                if source in inputs:
                    inferred[str(port)] = inputs[source]
            if inferred:
                node["inputs"] = inferred
            continue
        inferred = {}
        used: set[str] = set()
        if not predecessors.get(node_id) or kind in {"Model", "Agent"}:
            inferred = dict(inputs)
            used = set(inferred)
        for parent_id in predecessors.get(node_id) or ():
            parent = by_id.get(parent_id)
            if parent is None:
                continue
            for name, wire in dict(parent.get("outputs") or {}).items():
                port = _port_slug(name, used)
                inferred[port] = wire
        if not inferred:
            inferred = dict(inputs)
        node["inputs"] = inferred


def _synthesize_edges(
    nodes: list[dict[str, Any]],
    transitions: list[dict[str, str]],
    inputs: Mapping[str, Any],
    outputs: Mapping[str, Any],
    steps: Mapping[str, SemanticStepIntent],
) -> tuple[DataEdge, ...]:
    by_id = {str(node["id"]): node for node in nodes}
    predecessors = _data_predecessors(nodes, transitions)
    parsed_inputs = _typed_fields(dict(inputs), "inputs")
    parsed_outputs = _typed_fields(dict(outputs), "outputs")
    producers: list[tuple[PortRef, TypedField]] = [
        (PortRef("run_input", name), field) for name, field in parsed_inputs.items()
    ]
    for node in nodes:
        node_outputs = _typed_fields(node.get("outputs") or {}, f"{node['id']}.outputs")
        for name, field in node_outputs.items():
            producers.append((PortRef("node", name, str(node["id"])), field))
    raw: list[dict[str, Any]] = []
    bound: set[str] = set()

    def add(source: PortRef, target: PortRef, *, allow_duplicate: bool = False) -> None:
        key = target.as_key()
        if key in bound and not allow_duplicate:
            return
        if not allow_duplicate:
            bound.add(key)
        raw.append({"source": source.to_dict(), "target": target.to_dict()})

    for node in nodes:
        kind = str(node.get("component_type") or "")
        if kind not in _DATA_NODES:
            continue
        node_id = str(node["id"])
        step = steps.get(node_id)
        node_inputs = _typed_fields(node.get("inputs") or {}, f"{node_id}.inputs")
        available = list(predecessors.get(node_id) or ())
        for name, field in node_inputs.items():
            source_text = ""
            if step is not None:
                source_text = next(
                    (
                        item.source
                        for item in step.inputs
                        if _port_slug(item.name) == name
                    ),
                    "",
                )
            if source_text:
                parsed = _parse_source(source_text, parsed_inputs, by_id, steps)
                if parsed is not None:
                    add(parsed, PortRef("node", name, node_id))
                    continue
            match = _match_producer(
                field,
                name,
                producers,
                prefer_nodes=available,
                allow_run_input=True,
                exclude_node=node_id,
            )
            if match is None:
                incompatible = [
                    ref
                    for ref, produced in producers
                    if ref.port == name and not types_compatible(produced, field)
                ]
                if incompatible:
                    raise DataflowCompileError(
                        "code=DATAFLOW_TYPE_MISMATCH "
                        f"path=node.{node_id}.inputs.{name} "
                        "expected=compatible_source actual=incompatible"
                    )
            if match is None and field.required:
                raise DataflowCompileError(
                    "code=MISSING_REQUIRED_INPUT "
                    f"path=node.{node_id}.inputs.{name} "
                    "expected=bound_source actual=unbound"
                )
            if match is not None:
                add(match, PortRef("node", name, node_id))

    terminals = set(_terminal_data_nodes(nodes, transitions))
    for name, field in parsed_outputs.items():
        named = [
            ref
            for ref, produced in producers
            if ref.kind == "node"
            and ref.port == name
            and types_compatible(produced, field)
        ]
        chosen = named or [
            ref
            for ref, produced in producers
            if ref.kind == "node"
            and ref.node_id in terminals
            and types_compatible(produced, field)
        ]
        unique = list(dict.fromkeys(chosen))
        if not unique and field.required:
            raise DataflowCompileError(
                "code=UNREACHABLE_OUTPUT "
                f"path=outputs.{name} expected=bound_source actual=unbound"
            )
        for ref in unique:
            add(ref, PortRef("run_output", name), allow_duplicate=True)
    return parse_data_edges(raw, "data_edges")


def _parse_source(
    text: str,
    inputs: Mapping[str, TypedField],
    nodes: Mapping[str, Mapping[str, Any]],
    steps: Mapping[str, SemanticStepIntent],
) -> PortRef | None:
    raw = text.strip()
    if not raw:
        return None
    if raw.startswith("input.") or raw.startswith("run_input."):
        port = raw.split(".", 1)[1]
        if port in inputs:
            return PortRef("run_input", port)
        return None
    if "." in raw:
        owner, port = raw.split(".", 1)
        node_id = _node_id_for_key(owner, nodes, steps)
        if node_id and port in (nodes[node_id].get("outputs") or {}):
            return PortRef("node", port, node_id)
        return None
    if raw in inputs:
        return PortRef("run_input", raw)
    node_id = _node_id_for_key(raw, nodes, steps)
    if node_id:
        outputs = list(nodes[node_id].get("outputs") or {})
        if len(outputs) == 1:
            return PortRef("node", outputs[0], node_id)
    return None


def _node_id_for_key(
    key: str,
    nodes: Mapping[str, Mapping[str, Any]],
    steps: Mapping[str, SemanticStepIntent],
) -> str | None:
    folded = key.casefold()
    if folded in nodes:
        return folded
    for node_id, step in steps.items():
        if step.semantic_key.casefold() == folded:
            return node_id
    return None


def _match_producer(
    target: TypedField,
    name: str,
    producers: Sequence[tuple[PortRef, TypedField]],
    *,
    prefer_nodes: Sequence[str],
    allow_run_input: bool,
    exclude_node: str | None = None,
) -> PortRef | None:
    preferred = set(prefer_nodes)

    def allowed(ref: PortRef) -> bool:
        if ref.kind == "run_input":
            return allow_run_input
        if ref.kind != "node":
            return False
        if exclude_node and ref.node_id == exclude_node:
            return False
        if preferred:
            return ref.node_id in preferred
        return False

    name_hits = [
        ref
        for ref, field in producers
        if ref.port == name and types_compatible(field, target) and allowed(ref)
    ]
    if len(name_hits) == 1:
        return name_hits[0]
    if name_hits:
        node_hits = [ref for ref in name_hits if ref.kind == "node"]
        if node_hits:
            return node_hits[-1]
        return name_hits[0]
    type_hits = [
        ref
        for ref, field in producers
        if types_compatible(field, target) and allowed(ref)
    ]
    if len(type_hits) == 1:
        return type_hits[0]
    if preferred:
        local = [
            ref for ref in type_hits if ref.kind == "node" and ref.node_id in preferred
        ]
        if len(local) == 1:
            return local[0]
        if local:
            return local[-1]
    return None


def _data_predecessors(
    nodes: Sequence[Mapping[str, Any]], transitions: Sequence[Mapping[str, str]]
) -> dict[str, tuple[str, ...]]:
    kinds = {str(node["id"]): str(node.get("component_type") or "") for node in nodes}
    incoming: dict[str, list[str]] = {str(node["id"]): [] for node in nodes}
    outgoing: dict[str, list[str]] = {str(node["id"]): [] for node in nodes}
    for edge in transitions:
        outgoing.setdefault(str(edge["from"]), []).append(str(edge["to"]))
        incoming.setdefault(str(edge["to"]), []).append(str(edge["from"]))

    def producers(node_id: str, seen: set[str]) -> list[str]:
        found: list[str] = []
        for parent in incoming.get(node_id, []):
            if parent in seen:
                continue
            seen.add(parent)
            if kinds.get(parent) in _DATA_NODES:
                found.append(parent)
            else:
                found.extend(producers(parent, seen))
        return found

    return {node_id: tuple(producers(node_id, set())) for node_id in kinds}


def _terminal_data_nodes(
    nodes: Sequence[Mapping[str, Any]], transitions: Sequence[Mapping[str, str]]
) -> tuple[str, ...]:
    kinds = {str(node["id"]): str(node.get("component_type") or "") for node in nodes}
    incoming: dict[str, list[str]] = {str(node["id"]): [] for node in nodes}
    for edge in transitions:
        incoming.setdefault(str(edge["to"]), []).append(str(edge["from"]))
    terminals: list[str] = []
    for node in nodes:
        if kinds.get(str(node["id"])) != "Output":
            continue
        seen: set[str] = set()
        pending = list(incoming.get(str(node["id"]), []))
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            if kinds.get(current) in _DATA_NODES:
                terminals.append(current)
                continue
            pending.extend(incoming.get(current, []))
    return tuple(dict.fromkeys(terminals))


def _port_slug(name: str, used: set[str] | None = None) -> str:
    folded = _SLUG_NOISE.sub("-", name.casefold()).strip("-")
    if not folded or not folded[0].isalpha():
        folded = "port"
    folded = folded[:63].strip("-") or "port"
    candidate = folded
    taken = used if used is not None else set()
    index = 2
    while candidate in taken:
        suffix = f"-{index}"
        candidate = f"{folded[: 63 - len(suffix)]}{suffix}"
        index += 1
    taken.add(candidate)
    return candidate


class _NodeView:
    def __init__(self, node: Mapping[str, Any]) -> None:
        self.id = str(node["id"])
        raw_inputs = node.get("inputs") or {}
        raw_outputs = node.get("outputs") or {}
        self.inputs = _typed_fields(raw_inputs, f"{self.id}.inputs")
        self.outputs = _typed_fields(raw_outputs, f"{self.id}.outputs")
