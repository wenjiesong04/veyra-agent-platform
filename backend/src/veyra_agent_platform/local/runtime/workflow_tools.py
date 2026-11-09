"""Pinned Workflow Tool arguments and single-effect approval snapshots."""

from __future__ import annotations

from typing import Any

from veyra_agent_platform.contracts.agent import FlowNode
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.workflow import WorkflowSource
from veyra_agent_platform.local.resources import ResourceCatalogError

from .approvals import tool_approval_summary
from .tools import ToolAuthorization, ToolRuntime


def workflow_tool_arguments(
    tools: ToolRuntime, node: FlowNode, values: dict[str, Any]
) -> dict[str, Any]:
    mapped = {
        name: values.get(source_name)
        for name, source_name in (node.input_mapping or {}).items()
    }
    try:
        resource = tools.catalog.detail(*(node.uses or "").rsplit("@", 1))
    except (ResourceCatalogError, ValueError):
        return mapped
    spec = resource.get("spec", {})
    # Keep legacy Entity defaults, without injecting Entity-only fields into
    # filesystem, calculation, MCP, or other Tool argument contracts.
    if str(spec.get("adapter", "")).startswith("veyra.runtime.entity."):
        declared = spec.get("input_schema") or {}
        defaults = {
            "entity_type": values.get("entity_type") or "ProjectEntity",
            "status": values.get("status") or "active",
            "payload": values.get("result") or dict(values),
            "entity_id": values.get("entity_id"),
        }
        for name, value in defaults.items():
            if (
                name in declared
                and value is not None
                and (name not in mapped or mapped[name] is None or mapped[name] == "")
            ):
                mapped[name] = value
    return mapped


def tool_snapshot(
    source: WorkflowSource,
    node: FlowNode,
    authorization: ToolAuthorization,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    snapshot = {
        "node_id": node.id,
        "source_hash": source.source_hash,
        "tool_reference": node.uses,
        "resource_hash": (authorization.resource or {}).get("content_hash"),
        "input_digest": authorization.input_digest,
        "arguments": arguments,
    }
    return {**snapshot, "snapshot_digest": sha256_digest(snapshot)}


def tool_waiting(
    source: WorkflowSource,
    node: FlowNode,
    authorization: ToolAuthorization,
    arguments: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    request_id = new_uuid7()
    snapshot = tool_snapshot(source, node, authorization, arguments)
    summary = tool_approval_summary(
        node.uses or "", arguments, permissions=source.permissions.to_dict()
    )
    content = arguments.get("content")
    if authorization.adapter == "veyra.runtime.filesystem.write" and isinstance(
        content, str
    ):
        summary.update(
            content_digest=sha256_digest({"content": content}),
            content_bytes=len(content.encode("utf-8")),
            content_preview=content[:20_000],
            preview_truncated=len(content) > 20_000,
        )
    waiting = {
        "kind": "approval",
        "node_id": node.id,
        "request_id": request_id,
        "tool_reference": node.uses,
        "prompt": f"Approve tool {node.uses}",
        "approval_summary": summary,
        "context": {
            "kind": "tool_permission",
            "snapshot_digest": snapshot["snapshot_digest"],
        },
    }
    return waiting, {**snapshot, "request_id": request_id}
