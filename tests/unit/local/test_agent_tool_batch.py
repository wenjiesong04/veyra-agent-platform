from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tests.unit.local.test_agent_loop_runtime import (
    _HarnessHost,
    _ScriptedLoopModel,
    _tool_loop_source,
)
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.service import RuntimeError, _RunAbandoned
from veyra_agent_platform.local.runtime.tool_batch import _bounded_observation
from veyra_agent_platform.local.runtime.tools import ToolRuntime


def _actions(reference):
    return {
        "action": "tool_batch",
        "calls": [
            {"tool": reference, "arguments": {"expression": "1+2"}},
            {"tool": reference, "arguments": {"expression": "3+4"}},
        ],
    }


@pytest.mark.parametrize("policy", ["approval", "injected", "write"])
def test_batch_cannot_execute_approval_injected_or_write_tools(
    tmp_path: Path, policy: str
) -> None:
    resource = ResourceCatalog().detail(
        "veyra.tool.filesystem.write"
        if policy == "write"
        else "veyra.tool.math.calculate",
        "1.0.0",
    )
    if policy == "approval":
        resource["spec"]["approval_required"] = True
    host = _HarnessHost(tmp_path, resource)
    if policy != "injected":
        host.tools = ToolRuntime(ResourceCatalog())
    source = _tool_loop_source(resource)
    if policy == "write":
        from dataclasses import replace

        source = replace(
            source,
            permissions=replace(
                source.permissions, filesystem_write_roots=("project",)
            ),
        )
    model = _ScriptedLoopModel(
        _actions(resource["reference"]),
        {"action": "final", "outputs": {"translation": "No batch effect"}},
    )
    result = host._execute_loop("project", "run", source, {}, model)
    assert result.result == {"translation": "No batch effect"}
    assert not host.effects
    assert not any(kind == "tool.started" for _, kind, _ in host.events)
    assert not list(tmp_path.glob("*.txt"))


@pytest.mark.parametrize("change", ["adapter", "cancel"])
def test_drift_or_cancel_stops_the_next_dispatch_and_retains_first_receipt(
    tmp_path: Path, change: str
) -> None:
    resource = ResourceCatalog().detail("veyra.tool.math.calculate", "1.0.0")
    host = _HarnessHost(tmp_path, resource)
    host.tools = ToolRuntime(ResourceCatalog())
    running = True
    original = host._persist_event

    def persist(run_id, node_id, kind, payload):
        nonlocal running
        original(run_id, node_id, kind, payload)
        if kind == "tool.completed" and payload.get("batch_index") == 0:
            if change == "adapter":
                host.tools._adapters[resource["spec"]["adapter"]] = host._adapter
            else:
                running = False

    host._persist_event = persist
    host._is_running = lambda _: running
    model = _ScriptedLoopModel(_actions(resource["reference"]))
    expected = RuntimeError if change == "adapter" else _RunAbandoned
    with pytest.raises(expected) as caught:
        host._execute_loop("project", "run", _tool_loop_source(resource), {}, model)
    assert len(caught.value.tool_calls) >= 1
    assert sum(record.receipt is not None for record in caught.value.tool_calls) == 1
    assert not host.effects
    assert sum(kind == "tool.started" for _, kind, _ in host.events) == 1


def test_bounded_batch_keeps_all_statuses_and_indices_for_large_outputs() -> None:
    observation = {
        "outcome": "observed",
        "results": [
            {
                "index": i,
                "reference": "native.read@1.0.0",
                "status": "succeeded",
                "output": '"quoted"\n' * 2000,
            }
            for i in range(16)
        ],
    }
    bounded = _bounded_observation(observation, "results", "output", limit=8000)
    assert len(json.dumps(bounded, ensure_ascii=False)) <= 8000
    assert [item["index"] for item in bounded["results"]] == list(range(16))
    assert all(item["output"]["truncated"] for item in bounded["results"])


def test_rejected_batch_cannot_reset_an_identical_write_guard(tmp_path: Path) -> None:
    resource = ResourceCatalog().detail("veyra.tool.filesystem.write", "1.0.0")
    resource["spec"]["approval_required"] = False
    host = _HarnessHost(tmp_path, resource)
    source = replace(_tool_loop_source(resource), max_turns=8)
    write = {
        "action": "tool",
        "tool": resource["reference"],
        "arguments": {"path": "result.txt", "content": "unchanged"},
    }
    bad_batch = {
        "action": "tool_batch",
        "calls": [{"tool": "undeclared.tool@1.0.0", "arguments": {}}],
    }
    model = _ScriptedLoopModel(write, bad_batch, write, bad_batch, write)
    with pytest.raises(RuntimeError) as caught:
        host._execute_loop("project", "run", source, {}, model)
    assert caught.value.code == "agent_no_progress"
    assert len(host.effects) == 1
