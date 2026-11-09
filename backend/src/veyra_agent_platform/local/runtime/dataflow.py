"""Node-local typed dataflow store for Runtime.

Legacy Agents without ``data_edges`` keep the shared values bag. Typed graphs
resolve each node's inputs from explicit edges.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from veyra_agent_platform.contracts.agent import FlowNode
from veyra_agent_platform.contracts.dataflow import DataEdge, PortRef
from veyra_agent_platform.contracts.typed_io import TypedField

DATAFLOW_KEY = "$dataflow"


class DataflowOrigin(Protocol):
    @property
    def inputs(self) -> Mapping[str, TypedField]: ...

    @property
    def data_edges(self) -> tuple[DataEdge, ...]: ...


@dataclass
class NodeExecutionContext:
    node_id: str
    resolved_inputs: dict[str, Any]
    artifact_refs: tuple[dict[str, Any], ...] = ()
    provider_binding: Mapping[str, str] | None = None


@dataclass
class NodeExecutionResult:
    outputs: dict[str, Any]
    events: tuple[tuple[str | None, str, dict[str, Any]], ...] = ()
    artifacts: tuple[dict[str, Any], ...] = ()


@dataclass
class DataflowStore:
    edges: tuple[DataEdge, ...]
    run_inputs: dict[str, Any]
    node_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_source(
        cls, source: DataflowOrigin, values: Mapping[str, Any]
    ) -> DataflowStore:
        snapshot = values.get(DATAFLOW_KEY)
        stored: dict[str, dict[str, Any]] = {}
        if isinstance(snapshot, Mapping):
            raw = snapshot.get("nodes")
            if isinstance(raw, Mapping):
                stored = {
                    str(node_id): dict(ports)
                    for node_id, ports in raw.items()
                    if isinstance(ports, Mapping)
                }
        run_inputs = {name: values[name] for name in source.inputs if name in values}
        return cls(
            edges=source.data_edges,
            run_inputs=run_inputs,
            node_outputs=stored,
        )

    def context_for(self, node: FlowNode) -> NodeExecutionContext:
        resolved: dict[str, Any] = {}
        artifacts: list[dict[str, Any]] = []
        for edge in self.edges:
            if edge.target.kind != "node" or edge.target.node_id != node.id:
                continue
            value = self.read(edge.source)
            if value is None:
                continue
            resolved[edge.target.port] = value
            if isinstance(value, Mapping) and value.get("kind") in {
                "artifact",
                "collection",
            }:
                artifacts.append(dict(value))
        return NodeExecutionContext(
            node_id=node.id,
            resolved_inputs=resolved,
            artifact_refs=tuple(artifacts),
        )

    def record(self, node_id: str, outputs: Mapping[str, Any]) -> None:
        current = dict(self.node_outputs.get(node_id) or {})
        current.update(outputs)
        self.node_outputs[node_id] = current

    def run_outputs(self, fields: Mapping[str, TypedField]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for edge in self.edges:
            if edge.target.kind != "run_output":
                continue
            value = self.read(edge.source)
            if value is None or edge.target.port in result:
                continue
            result[edge.target.port] = value
        for name in fields:
            if name not in result and name in self.run_inputs:
                result[name] = self.run_inputs[name]
        return result

    def read(self, ref: PortRef) -> Any:
        if ref.kind == "run_input":
            return self.run_inputs.get(ref.port)
        if ref.kind == "node" and ref.node_id:
            return (self.node_outputs.get(ref.node_id) or {}).get(ref.port)
        return None

    def snapshot(self) -> dict[str, Any]:
        return {"nodes": {key: dict(value) for key, value in self.node_outputs.items()}}

    def merge_into(self, values: dict[str, Any]) -> dict[str, Any]:
        merged = dict(values)
        merged.update(self.run_inputs)
        for node_id, ports in self.node_outputs.items():
            merged[node_id] = dict(ports)
        merged[DATAFLOW_KEY] = self.snapshot()
        return merged
