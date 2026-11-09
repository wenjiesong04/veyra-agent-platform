from __future__ import annotations

import pytest

from veyra_agent_platform.contracts.common import ContractValidationError, new_uuid7
from veyra_agent_platform.contracts.workflow import WorkflowSource

AGENT_ID = "01a03795-a5b0-7234-ba76-5c5f0e029334"
DIGEST = "a" * 64


def _blank_workflow(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "component_type": "Workflow",
        "workflow_id": new_uuid7(),
        "slug": "new-workflow",
        "name": "New Workflow",
        "description": "A blank Workflow that orchestrates Agents.",
        "version": "1.0.0",
        "inputs": {"prompt": "string"},
        "outputs": {"result": "string"},
        "nodes": [
            {"id": "start", "component_type": "Start"},
            {"id": "output", "component_type": "Output", "output_name": "result"},
        ],
        "transitions": [{"from": "start", "port": "next", "to": "output"}],
        "extensions": {
            "veyra": {
                "permissions": {"network_hosts": [], "tools": []},
                "verification": {"required": False, "checks": []},
            }
        },
        "ui": {
            "positions": {"start": {"x": 90, "y": 80}, "output": {"x": 330, "y": 80}}
        },
        "lock": {},
    }
    payload.update(overrides)
    return payload


def test_blank_workflow_allows_empty_lock() -> None:
    source = WorkflowSource.from_dict(_blank_workflow())
    assert source.lock == {}
    assert (
        source.component_type == "Workflow"
        or source.to_dict()["component_type"] == "Workflow"
    )
    assert len(source.behavior_hash) == 64
    assert (
        source.behavior_hash == WorkflowSource.from_dict(source.to_dict()).behavior_hash
    )


def test_workflow_rejects_model_and_tool_nodes() -> None:
    with pytest.raises(ContractValidationError, match="Model"):
        WorkflowSource.from_dict(
            _blank_workflow(
                nodes=[
                    {"id": "start", "component_type": "Start"},
                    {
                        "id": "model",
                        "component_type": "Model",
                        "model_ref": "model.primary",
                        "system_prompt": "x",
                    },
                    {
                        "id": "output",
                        "component_type": "Output",
                        "output_name": "result",
                    },
                ],
                transitions=[
                    {"from": "start", "port": "next", "to": "model"},
                    {"from": "model", "port": "next", "to": "output"},
                ],
                ui={
                    "positions": {
                        "start": {"x": 0, "y": 0},
                        "model": {"x": 1, "y": 0},
                        "output": {"x": 2, "y": 0},
                    }
                },
            )
        )


def test_agent_call_must_lock_id_at_version() -> None:
    ref = f"{AGENT_ID}@{new_uuid7()}"
    source = WorkflowSource.from_dict(
        _blank_workflow(
            nodes=[
                {"id": "start", "component_type": "Start"},
                {
                    "id": "call",
                    "component_type": "AgentCall",
                    "agent_ref": ref,
                    "input_mapping": {"prompt": "prompt"},
                    "output_mapping": {"result": "result"},
                },
                {"id": "output", "component_type": "Output", "output_name": "result"},
            ],
            transitions=[
                {"from": "start", "port": "next", "to": "call"},
                {"from": "call", "port": "next", "to": "output"},
            ],
            ui={
                "positions": {
                    "start": {"x": 0, "y": 0},
                    "call": {"x": 1, "y": 0},
                    "output": {"x": 2, "y": 0},
                }
            },
            lock={ref: DIGEST},
        )
    )
    assert source.nodes[1].agent_ref == ref
    with pytest.raises(ContractValidationError, match="lock"):
        WorkflowSource.from_dict(
            _blank_workflow(
                nodes=[
                    {"id": "start", "component_type": "Start"},
                    {
                        "id": "call",
                        "component_type": "AgentCall",
                        "agent_ref": ref,
                        "input_mapping": {"prompt": "prompt"},
                        "output_mapping": {"result": "result"},
                    },
                    {
                        "id": "output",
                        "component_type": "Output",
                        "output_name": "result",
                    },
                ],
                transitions=[
                    {"from": "start", "port": "next", "to": "call"},
                    {"from": "call", "port": "next", "to": "output"},
                ],
                ui={
                    "positions": {
                        "start": {"x": 0, "y": 0},
                        "call": {"x": 1, "y": 0},
                        "output": {"x": 2, "y": 0},
                    }
                },
                lock={},
            )
        )


def test_workflow_canvas_notes_do_not_change_behavior_hash() -> None:
    payload = _blank_workflow()
    original = WorkflowSource.from_dict(payload)
    payload["ui"]["notes"] = {  # type: ignore[index]
        "note_intro": {
            "x": 12,
            "y": 20,
            "text": "hello",
            "color": "amber",
            "width": 220,
            "manual_position": False,
        }
    }
    noted = WorkflowSource.from_dict(payload)
    assert noted.ui["notes"]["note_intro"]["text"] == "hello"
    assert original.behavior_hash == noted.behavior_hash
    assert original.source_hash != noted.source_hash
    payload["ui"]["notes"]["note_intro"]["x"] = 640  # type: ignore[index]
    payload["ui"]["notes"]["note_intro"]["manual_position"] = True  # type: ignore[index]
    moved = WorkflowSource.from_dict(payload)
    assert moved.behavior_hash == noted.behavior_hash
    assert moved.source_hash != noted.source_hash


def test_workflow_notes_cannot_reuse_flow_node_ids() -> None:
    with pytest.raises(ContractValidationError, match="notes collide"):
        WorkflowSource.from_dict(
            _blank_workflow(
                ui={
                    "positions": {
                        "start": {"x": 90, "y": 80},
                        "output": {"x": 330, "y": 80},
                    },
                    "notes": {"start": {"x": 0, "y": 0, "text": "nope"}},
                }
            )
        )
