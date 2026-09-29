"""Deterministic structural simulation. Never calls a real Provider."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from veyra_agent_platform.contracts.agent import AgentBlueprint, ComponentType
from veyra_agent_platform.contracts.condition import parse_condition_expression
from veyra_agent_platform.contracts.typed_io import TypedField, value_matches_field
from veyra_agent_platform.local.runtime.dataflow import DataflowStore

_IMAGE_REF = {
    "kind": "artifact",
    "artifact_id": "art_sim_image",
    "media_type": "image/png",
    "filename": "simulated.png",
}
_FILE_REF = {
    "kind": "artifact",
    "artifact_id": "art_sim_file",
    "media_type": "application/pdf",
    "filename": "simulated.pdf",
}


@dataclass(frozen=True)
class SimulationReport:
    passed: bool
    diagnostics: tuple[str, ...]
    branches: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "diagnostics": list(self.diagnostics),
            "branches": list(self.branches),
        }


def simulate_agent(blueprint: AgentBlueprint) -> SimulationReport:
    diagnostics: list[str] = []
    branches: list[str] = []
    if not blueprint.data_edges:
        return SimulationReport(
            False, ("code=MISSING_DATAFLOW expected=data_edges",), ()
        )
    start = next(
        node.id
        for node in blueprint.nodes
        if node.component_type is ComponentType.START
    )
    routes = _branch_routes(blueprint)
    for route in routes or (("default", {}),):
        label, decisions = route if isinstance(route, tuple) else ("default", {})
        branches.append(str(label))
        try:
            result, visited = _walk(blueprint, start, decisions)
        except SimulationFailure as exc:
            diagnostics.append(str(exc))
            continue
        for name, field in blueprint.outputs.items():
            on_path = False
            for edge in blueprint.data_edges:
                if edge.target.kind != "run_output" or edge.target.port != name:
                    continue
                if edge.source.kind == "run_input" or edge.source.node_id in visited:
                    on_path = True
                    break
            if not on_path:
                continue
            if name not in result:
                if field.required:
                    diagnostics.append(
                        f"code=UNREACHABLE_OUTPUT path=outputs.{name} branch={label}"
                    )
                continue
            if not value_matches_field(field, result[name]):
                diagnostics.append(
                    f"code=DATAFLOW_TYPE_MISMATCH path=outputs.{name} branch={label}"
                )
    unique = tuple(dict.fromkeys(diagnostics))
    return SimulationReport(not unique, unique, tuple(branches))


class SimulationFailure(ValueError):
    pass


def _walk(
    blueprint: AgentBlueprint,
    start: str,
    decisions: Mapping[str, str],
) -> tuple[dict[str, Any], set[str]]:
    nodes = {node.id: node for node in blueprint.nodes}
    edges = {
        (edge.from_node, edge.port.value): edge.to_node
        for edge in blueprint.transitions
    }
    values = {name: _synthetic(field, name) for name, field in blueprint.inputs.items()}
    store = DataflowStore.from_source(
        _BlueprintSource(blueprint, values),
        values,
    )
    current = start
    seen: set[str] = set()
    visited: set[str] = set()
    for _ in range(len(nodes) + 8):
        if (
            current in seen
            and nodes[current].component_type is not ComponentType.HUMAN_APPROVAL
        ):
            raise SimulationFailure(f"code=UNBOUNDED_LOOP path=nodes.{current}")
        seen.add(current)
        visited.add(current)
        node = nodes[current]
        if node.component_type is ComponentType.OUTPUT:
            return store.run_outputs(blueprint.outputs), visited
        if node.component_type in {
            ComponentType.MODEL,
            ComponentType.AGENT,
            ComponentType.TRANSFORM,
            ComponentType.TOOL,
            ComponentType.CUSTOM_COMPONENT,
        }:
            context = store.context_for(node)
            for name, field in (node.inputs or {}).items():
                if field.required and name not in context.resolved_inputs:
                    raise SimulationFailure(
                        "code=MISSING_REQUIRED_INPUT "
                        f"path=nodes.{node.id}.inputs.{name}"
                    )
            produced = {
                name: _synthetic(field, name)
                for name, field in (node.outputs or {}).items()
            }
            store.record(node.id, produced)
            port = "next"
        elif node.component_type is ComponentType.HUMAN_APPROVAL:
            port = decisions.get(node.id, "approved")
        elif node.component_type is ComponentType.CONDITION:
            parsed = parse_condition_expression(node.expression or "")
            actual = values.get(parsed.field)
            matched = str(actual) == parsed.literal
            if parsed.operator == "!=":
                matched = not matched
            port = "true" if matched else "false"
        elif node.component_type is ComponentType.VERIFIER:
            port = "passed"
        else:
            port = "next"
        nxt = edges.get((current, port))
        if nxt is None:
            raise SimulationFailure(
                f"code=UNREACHABLE_BRANCH path=nodes.{current}.{port}"
            )
        current = nxt
    raise SimulationFailure("code=UNBOUNDED_LOOP expected=finite_graph")


def _branch_routes(
    blueprint: AgentBlueprint,
) -> list[tuple[str, dict[str, str]]]:
    approvals = [
        node.id
        for node in blueprint.nodes
        if node.component_type is ComponentType.HUMAN_APPROVAL
    ]
    conditions = [
        node
        for node in blueprint.nodes
        if node.component_type is ComponentType.CONDITION
    ]
    routes: list[tuple[str, dict[str, str]]] = [("approved", {})]
    if approvals:
        routes = [
            ("approved", {node_id: "approved" for node_id in approvals}),
            ("rejected", {node_id: "rejected" for node_id in approvals}),
        ]
        if len(approvals) > 1:
            mixed = {node_id: "approved" for node_id in approvals}
            mixed[approvals[0]] = "rejected"
            routes.append(("rejected-then-approved", mixed))
    if conditions:
        extra: list[tuple[str, dict[str, str]]] = []
        for label, decisions in routes:
            extra.append((f"{label}-true", decisions))
            extra.append((f"{label}-false", decisions))
        routes = extra or [("true", {}), ("false", {})]
    return routes


def _synthetic(field: TypedField, name: str) -> Any:
    if field.multiple:
        return [_synthetic_one(field, name)]
    return _synthetic_one(field, name)


def _synthetic_one(field: TypedField, name: str) -> Any:
    if field.enum:
        return field.enum[0]
    kind = field.compact_type
    if kind == "boolean":
        return True
    if kind in {"integer", "number"}:
        return 1
    if kind == "object":
        return {"simulated": name}
    if kind in {"array", "table"}:
        return [{"simulated": name}]
    if kind == "image":
        return dict(_IMAGE_REF)
    if kind in {"pdf", "document", "file", "audio", "video"}:
        return dict(_FILE_REF)
    if kind == "collection":
        return {
            "kind": "collection",
            "collection_id": "col_sim",
            "items": [dict(_FILE_REF)],
        }
    return f"simulated-{name}"


class _BlueprintSource:
    """Minimal adapter so simulation can reuse DataflowStore."""

    def __init__(self, blueprint: AgentBlueprint, values: Mapping[str, Any]) -> None:
        self.inputs = blueprint.inputs
        self.outputs = blueprint.outputs
        self.nodes = blueprint.nodes
        self.data_edges = blueprint.data_edges
        self._values = values
