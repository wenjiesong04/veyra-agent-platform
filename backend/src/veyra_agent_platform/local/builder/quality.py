"""Static quality gate for compiled Agent blueprints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from veyra_agent_platform.contracts.agent import AgentBlueprint, ComponentType
from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.condition import parse_condition_expression
from veyra_agent_platform.contracts.dataflow import validate_data_edges

QualityVerdict = Literal["PASS", "REPAIR_REQUIRED"]
_SECRET_MARKERS = ("api_key", "authorization", "password", "-----begin")


@dataclass(frozen=True)
class QualityReport:
    verdict: QualityVerdict
    diagnostics: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"verdict": self.verdict, "diagnostics": list(self.diagnostics)}


def validate_agent_quality(blueprint: AgentBlueprint) -> QualityReport:
    diagnostics: list[str] = []
    if not blueprint.data_edges:
        diagnostics.append("code=MISSING_DATAFLOW expected=data_edges")
    else:
        try:
            validate_data_edges(
                inputs=blueprint.inputs,
                outputs=blueprint.outputs,
                nodes=blueprint.nodes,
                edges=blueprint.data_edges,
            )
        except ContractValidationError as exc:
            diagnostics.append(str(exc))
    consumed = {
        edge.source.port
        for edge in blueprint.data_edges
        if edge.source.kind == "run_input"
    }
    for name, field in blueprint.inputs.items():
        if field.required and name not in consumed:
            diagnostics.append(
                f"code=UNUSED_REQUIRED_INPUT path=inputs.{name} "
                "expected=consumed_or_optional"
            )
    produced = {
        edge.target.port
        for edge in blueprint.data_edges
        if edge.target.kind == "run_output"
    }
    for name, field in blueprint.outputs.items():
        if field.required and name not in produced:
            diagnostics.append(
                f"code=UNREACHABLE_OUTPUT path=outputs.{name} expected=bound_source"
            )
    kinds = {node.id: node.component_type for node in blueprint.nodes}
    incoming = {node.id: 0 for node in blueprint.nodes}
    outgoing: dict[str, list[str]] = {node.id: [] for node in blueprint.nodes}
    for edge in blueprint.transitions:
        outgoing[edge.from_node].append(edge.to_node)
        incoming[edge.to_node] += 1
    for node in blueprint.nodes:
        if node.component_type is ComponentType.START:
            continue
        if incoming[node.id] == 0:
            diagnostics.append(f"code=DANGLING_NODE path=nodes.{node.id}")
        if node.component_type is not ComponentType.OUTPUT and not outgoing[node.id]:
            diagnostics.append(f"code=UNREACHABLE_BRANCH path=nodes.{node.id}")
    for node in blueprint.nodes:
        if node.component_type is ComponentType.HUMAN_APPROVAL:
            ports = {
                edge.port.value
                for edge in blueprint.transitions
                if edge.from_node == node.id
            }
            if ports != {"approved", "rejected"}:
                diagnostics.append(f"code=INVALID_APPROVAL_ROUTES path=nodes.{node.id}")
        if node.component_type is ComponentType.CONDITION and node.expression:
            try:
                parsed = parse_condition_expression(node.expression)
            except ContractValidationError as exc:
                diagnostics.append(str(exc))
            else:
                if parsed.field not in blueprint.inputs:
                    known_outputs = {
                        name
                        for item in blueprint.nodes
                        for name in (item.outputs or {})
                    }
                    if parsed.field not in known_outputs:
                        diagnostics.append(
                            "code=CONDITION_UNKNOWN_FIELD "
                            f"path=nodes.{node.id}.expression actual={parsed.field}"
                        )
        prompt = (node.system_prompt or node.prompt or "").casefold()
        if any(marker in prompt for marker in _SECRET_MARKERS):
            diagnostics.append(f"code=SECRET_EMBEDDED path=nodes.{node.id}")
        if (
            node.component_type in {ComponentType.MODEL, ComponentType.AGENT}
            and not node.model_ref
        ):
            diagnostics.append(
                f"code=UNBOUND_MODEL_CAPABILITY path=nodes.{node.id}.model_ref"
            )
    _ = kinds
    unique = tuple(dict.fromkeys(diagnostics))
    return QualityReport("PASS" if not unique else "REPAIR_REQUIRED", unique)
