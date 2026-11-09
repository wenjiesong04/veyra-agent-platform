from __future__ import annotations

from copy import deepcopy

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.legacy_graph import (
    classify_legacy_graph_agent,
    legacy_graph_migration_plan,
)
from veyra_agent_platform.local.builder.agent_loop_compiler import compile_loop_agent
from veyra_agent_platform.local.builder.specification import infer_agent_specification
from veyra_agent_platform.local.resources import ResourceCatalog


def _loop_payload() -> dict:
    spec = infer_agent_specification("创建一个翻译助手，把中文翻译成自然英语。")
    return compile_loop_agent(spec, ResourceCatalog(), requirement=spec.goal).to_dict()


def test_loop_agent_is_not_migrated() -> None:
    source = AgentSource.from_dict(_loop_payload())
    assert classify_legacy_graph_agent(source) == "loop_agent"
    plan = legacy_graph_migration_plan(source)
    assert plan["action"] == "keep"
    assert plan["silent_migrate"] == "false"


def test_simple_graph_is_a_loop_candidate_without_silent_migrate() -> None:
    payload = _loop_payload()
    payload["extensions"]["veyra"]["execution_kind"] = "graph"
    source = AgentSource.from_dict(payload)
    assert classify_legacy_graph_agent(source) == "simple_graph_loop_candidate"
    plan = legacy_graph_migration_plan(source)
    assert plan["action"] == "convert_to_loop_agent"
    assert plan["silent_migrate"] == "false"


def test_approval_graph_is_a_workflow_candidate_without_silent_migrate() -> None:
    payload = _loop_payload()
    payload["extensions"]["veyra"]["execution_kind"] = "graph"
    payload["nodes"] = [
        {"id": "start", "component_type": "Start"},
        {
            "id": "model",
            "component_type": "Model",
            "model_ref": "model.primary",
            "system_prompt": "Draft a report.",
        },
        {
            "id": "approval",
            "component_type": "HumanApproval",
            "prompt": "Approve the report?",
        },
        {"id": "output", "component_type": "Output", "output_name": "translation"},
    ]
    payload["transitions"] = [
        {"from": "start", "port": "next", "to": "model"},
        {"from": "model", "port": "next", "to": "approval"},
        {"from": "approval", "port": "approved", "to": "output"},
        {"from": "approval", "port": "rejected", "to": "output"},
    ]
    payload["ui"]["positions"] = {
        "start": {"x": 0, "y": 80},
        "model": {"x": 220, "y": 80},
        "approval": {"x": 440, "y": 80},
        "output": {"x": 660, "y": 80},
    }
    source = AgentSource.from_dict(payload)
    assert classify_legacy_graph_agent(source) == "orchestration_workflow_candidate"
    plan = legacy_graph_migration_plan(source)
    assert plan["action"] == "convert_to_workflow"
    assert plan["silent_migrate"] == "false"
    round_trip = AgentSource.from_dict(deepcopy(payload))
    assert round_trip.execution_kind == "graph"
