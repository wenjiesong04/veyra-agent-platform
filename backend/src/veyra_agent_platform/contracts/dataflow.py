"""Canonical typed ports and data edges.

Control flow stays on ``transitions``. Data movement is explicit:

    run_input.port → node.input.port
    node.output.port → node.input.port
    node.output.port → run_output.port

Legacy Agent sources without ``data_edges`` still parse. Runtime then uses the
shared values bag and marks the graph as ``legacy``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .common import (
    NODE_ID_RE,
    ContractValidationError,
    require_keys,
    require_mapping,
    require_string,
)
from .typed_io import TypedField, wire_field_compact_type

PortKind = Literal["run_input", "node", "run_output"]
_PORT_KINDS = frozenset({"run_input", "node", "run_output"})
_PORT_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_EDGE_FIELDS = {"source", "target"}
_REF_FIELDS = {"kind", "node_id", "port"}

COMPATIBLE_TYPES: frozenset[tuple[str, str]] = frozenset(
    {
        ("string", "string"),
        ("integer", "integer"),
        ("integer", "number"),
        ("number", "number"),
        ("boolean", "boolean"),
        ("object", "object"),
        ("array", "array"),
        ("array", "table"),
        ("table", "table"),
        ("table", "array"),
        ("image", "image"),
        ("pdf", "pdf"),
        ("pdf", "document"),
        ("pdf", "file"),
        ("document", "document"),
        ("document", "file"),
        ("file", "file"),
        ("audio", "audio"),
        ("video", "video"),
        ("collection", "collection"),
    }
)


@dataclass(frozen=True)
class PortRef:
    kind: PortKind
    port: str
    node_id: str | None = None

    def to_dict(self) -> dict[str, str]:
        payload = {"kind": self.kind, "port": self.port}
        if self.node_id:
            payload["node_id"] = self.node_id
        return payload

    def as_key(self) -> str:
        if self.kind == "node":
            return f"node:{self.node_id}.{self.port}"
        return f"{self.kind}:{self.port}"


@dataclass(frozen=True)
class DataEdge:
    source: PortRef
    target: PortRef

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source.to_dict(), "target": self.target.to_dict()}


def parse_data_edges(value: Any, field: str = "data_edges") -> tuple[DataEdge, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ContractValidationError(f"{field} must be a list")
    if len(value) > 256:
        raise ContractValidationError(f"{field} exceeds 256 edges")
    parsed: list[DataEdge] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        edge = _parse_edge(item, f"{field}[{index}]")
        key = edge.target.as_key()
        if edge.target.kind != "run_output" and key in seen:
            raise ContractValidationError(
                f"code=DUPLICATE_TARGET_PORT path={field}[{index}] "
                f"expected=unique_target actual={key}"
            )
        seen.add(key)
        parsed.append(edge)
    return tuple(parsed)


def data_edges_to_wire(edges: Sequence[DataEdge]) -> list[dict[str, Any]]:
    return [edge.to_dict() for edge in edges]


def types_compatible(source: TypedField | str, target: TypedField | str) -> bool:
    source_type = _compact(source)
    target_type = _compact(target)
    if source_type is None or target_type is None:
        return False
    source_multi = isinstance(source, TypedField) and source.multiple
    target_multi = isinstance(target, TypedField) and target.multiple
    if source_multi != target_multi:
        return False
    return (source_type, target_type) in COMPATIBLE_TYPES


def validate_data_edges(
    *,
    inputs: Mapping[str, TypedField],
    outputs: Mapping[str, TypedField],
    nodes: Sequence[Any],
    edges: Sequence[DataEdge],
) -> None:
    """Fail closed on unknown ports, type mismatches, and missing required inputs."""

    by_id = {node.id: node for node in nodes}
    producers: dict[str, TypedField] = {}
    consumers: dict[str, TypedField] = {}
    for name, field in inputs.items():
        producers[f"run_input:{name}"] = field
    for name, field in outputs.items():
        consumers[f"run_output:{name}"] = field
    for node in nodes:
        node_inputs = getattr(node, "inputs", None) or {}
        node_outputs = getattr(node, "outputs", None) or {}
        for name, field in node_inputs.items():
            consumers[f"node:{node.id}.{name}"] = field
        for name, field in node_outputs.items():
            producers[f"node:{node.id}.{name}"] = field

    required_targets = {
        key
        for key, field in consumers.items()
        if field.required and key.startswith("node:")
    }
    required_outputs = {
        key
        for key, field in consumers.items()
        if field.required and key.startswith("run_output:")
    }
    bound_targets: set[str] = set()
    for index, edge in enumerate(edges):
        source_key = edge.source.as_key()
        target_key = edge.target.as_key()
        source_field = producers.get(source_key)
        target_field = consumers.get(target_key)
        if source_field is None:
            raise ContractValidationError(
                "code=UNKNOWN_SOURCE_PORT "
                f"path=data_edges[{index}].source expected=declared_output "
                f"actual={source_key}"
            )
        if target_field is None:
            raise ContractValidationError(
                "code=UNKNOWN_TARGET_PORT "
                f"path=data_edges[{index}].target expected=declared_input "
                f"actual={target_key}"
            )
        if edge.source.kind == "node" and edge.source.node_id not in by_id:
            raise ContractValidationError(
                "code=UNKNOWN_SOURCE_PORT "
                f"path=data_edges[{index}].source.node_id expected=existing_node "
                f"actual={edge.source.node_id}"
            )
        if edge.target.kind == "node" and edge.target.node_id not in by_id:
            raise ContractValidationError(
                "code=UNKNOWN_TARGET_PORT "
                f"path=data_edges[{index}].target.node_id expected=existing_node "
                f"actual={edge.target.node_id}"
            )
        if not types_compatible(source_field, target_field):
            raise ContractValidationError(
                "code=DATAFLOW_TYPE_MISMATCH "
                f"path=data_edges[{index}] "
                f"expected={source_field.compact_type}->{target_field.compact_type} "
                "actual=incompatible"
            )
        bound_targets.add(target_key)

    missing_inputs = sorted(required_targets - bound_targets)
    if missing_inputs:
        raise ContractValidationError(
            "code=MISSING_REQUIRED_INPUT "
            f"path=data_edges expected=bound_required_node_inputs "
            f"actual={','.join(missing_inputs)}"
        )
    missing_outputs = sorted(required_outputs - bound_targets)
    if missing_outputs:
        raise ContractValidationError(
            "code=UNREACHABLE_OUTPUT "
            f"path=data_edges expected=bound_required_run_outputs "
            f"actual={','.join(missing_outputs)}"
        )


def _parse_edge(value: Any, field: str) -> DataEdge:
    item = require_mapping(value, field)
    require_keys(item, allowed=_EDGE_FIELDS, required=_EDGE_FIELDS, field=field)
    return DataEdge(
        source=_parse_ref(item["source"], f"{field}.source", producer=True),
        target=_parse_ref(item["target"], f"{field}.target", producer=False),
    )


def _parse_ref(value: Any, field: str, *, producer: bool) -> PortRef:
    item = require_mapping(value, field)
    require_keys(item, allowed=_REF_FIELDS, required={"kind", "port"}, field=field)
    kind = require_string(item["kind"], f"{field}.kind")
    if kind not in _PORT_KINDS:
        raise ContractValidationError(f"{field}.kind is not a dataflow port kind")
    allowed = {"run_input", "node"} if producer else {"node", "run_output"}
    if kind not in allowed:
        raise ContractValidationError(
            f"{field}.kind is not valid on this end of an edge"
        )
    node_id = None
    if kind == "node":
        node_id = require_string(
            item.get("node_id"), f"{field}.node_id", pattern=NODE_ID_RE
        )
    elif "node_id" in item:
        raise ContractValidationError(f"{field}.node_id is only valid for kind=node")
    return PortRef(
        kind=kind,  # type: ignore[arg-type]
        port=require_string(item["port"], f"{field}.port", pattern=_PORT_RE),
        node_id=node_id,
    )


def _compact(field: TypedField | str) -> str | None:
    if isinstance(field, str):
        return field
    return wire_field_compact_type(field)
