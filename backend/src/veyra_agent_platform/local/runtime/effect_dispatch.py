"""Identify dispatch evidence consistently across retry and checkpoint recovery."""

from __future__ import annotations

import json
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource


def has_dispatched_effect(
    connection: Any,
    run_id: str,
    source: AgentSource,
    *,
    after_sequence: int = 0,
) -> bool:
    image_nodes = {node.id for node in source.nodes if node.model_ref == "model.image"}
    events = connection.execute(
        "SELECT kind, node_id, payload_json FROM runtime_run_events "
        "WHERE run_id = ? AND sequence > ? AND kind IN "
        "('tool.started', 'node.started', 'image.response_received')",
        (run_id, after_sequence),
    ).fetchall()
    # Historical Graph image dispatches have no phase; their fixed Source is evidence.
    return any(
        event["kind"] in {"tool.started", "image.response_received"}
        or event["node_id"] in image_nodes
        or json.loads(event["payload_json"]).get("phase") == "image"
        for event in events
    )
