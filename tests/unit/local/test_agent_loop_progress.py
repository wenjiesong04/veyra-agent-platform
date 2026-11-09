from __future__ import annotations

from pathlib import Path

import pytest

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.typed_io import parse_typed_fields
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.agent_loop import (
    LOOP_STATE_KEY,
    parse_loop_action,
)
from veyra_agent_platform.local.runtime.loop_progress import (
    MAX_PLAN_STEPS,
    executed_call_state,
    final_turn_notice,
    is_repeated_call,
    public_plan,
)
from veyra_agent_platform.local.runtime.service import RuntimeError as LoopRuntimeError

from .test_agent_loop_runtime import (
    _HarnessHost,
    _ScriptedLoopModel,
    _tool_loop_source,
)


def _read_tool() -> dict:
    return ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")


def _kinds(host: _HarnessHost, kind: str) -> list[dict]:
    return [payload for _, name, payload in host.events if name == kind]


def test_public_plan_normalizes_bounded_steps_and_rejects_unusable_input() -> None:
    plan = public_plan(
        {
            "goal": " 汇总报告 ",
            "steps": ["读取文件", {"title": "比较", "status": "done"}],
        }
    )
    assert plan == {
        "steps": [
            {"title": "读取文件", "status": "pending"},
            {"title": "比较", "status": "done"},
        ],
        "goal": "汇总报告",
    }
    assert public_plan(None) is None
    assert public_plan({"steps": []}) is None
    assert public_plan({"steps": ["x"] * (MAX_PLAN_STEPS + 1)}) is None
    assert public_plan({"steps": [{"title": "x", "status": "thinking"}]}) is None
    assert public_plan({"steps": ["x" * 201]}) is None
    assert public_plan({"steps": [{"title": "  "}]}) is None


def test_plan_is_not_an_output_unless_the_agent_declares_one() -> None:
    outputs = parse_typed_fields({"result": "string"}, "outputs")
    action = parse_loop_action(
        '{"action":"final","result":"done","plan":{"steps":["a"]}}', outputs
    )
    assert action["outputs"] == {"action": "final", "result": "done"}
    assert action["plan"] == {"steps": ["a"]}

    declared = parse_typed_fields({"plan": "string"}, "outputs")
    action = parse_loop_action('{"action":"final","plan":"ship it"}', declared)
    assert action["outputs"]["plan"] == "ship it"
    assert "plan" not in action


def test_plan_updates_are_public_events_and_survive_a_pause(tmp_path: Path) -> None:
    tool = _read_tool()
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    plan = {"goal": "整理", "steps": [{"title": "读取", "status": "in_progress"}]}
    model = _ScriptedLoopModel(
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"path": "a.txt"},
            "plan": plan,
        },
        {"action": "ask_user", "question": "继续吗？", "plan": plan},
        {
            "action": "final",
            "outputs": {"translation": "ok"},
            "plan": {"steps": [{"title": "读取", "status": "done"}]},
        },
    )
    paused = host._execute_loop("project", "run", source, {}, model)
    assert paused.pause is not None
    assert paused.pause.values[LOOP_STATE_KEY]["plan"]["goal"] == "整理"
    assert len(_kinds(host, "agent.plan_updated")) == 1

    reply = {**paused.pause.values, "$agent_reply": "继续"}
    finished = host._execute_loop("project", "run", source, reply, model)
    assert finished.result == {"translation": "ok"}
    updates = _kinds(host, "agent.plan_updated")
    assert [update["plan"]["steps"][0]["status"] for update in updates] == [
        "in_progress",
        "done",
    ]


def test_invalid_plan_is_ignored_without_failing_the_action(tmp_path: Path) -> None:
    tool = _read_tool()
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    model = _ScriptedLoopModel(
        {"action": "final", "outputs": {"translation": "ok"}, "plan": "think"}
    )
    outcome = host._execute_loop("project", "run", source, {}, model)
    assert outcome.result == {"translation": "ok"}
    assert not _kinds(host, "agent.plan_updated")


def test_identical_consecutive_call_is_not_executed_and_can_be_corrected(
    tmp_path: Path,
) -> None:
    tool = _read_tool()
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    call = {"action": "tool", "tool": tool["reference"], "arguments": {"path": "a"}}
    model = _ScriptedLoopModel(
        call,
        call,
        {"action": "tool", "tool": tool["reference"], "arguments": {"path": "b"}},
        {"action": "final", "outputs": {"translation": "ok"}},
    )
    outcome = host._execute_loop("project", "run", source, {}, model)
    assert outcome.result == {"translation": "ok"}
    assert host.effects == [{"path": "a"}, {"path": "b"}]
    rejected = _kinds(host, "tool.input_rejected")
    assert [item["code"] for item in rejected] == ["tool_call_repeated"]
    assert rejected[0]["effect_started"] is False
    assert "identical arguments" in model.calls[2][-1]["content"]


def test_repeating_the_same_call_again_stops_without_another_effect(
    tmp_path: Path,
) -> None:
    tool = _read_tool()
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    call = {"action": "tool", "tool": tool["reference"], "arguments": {"path": "a"}}
    model = _ScriptedLoopModel(call, call, call)
    with pytest.raises(LoopRuntimeError) as caught:
        host._execute_loop("project", "run", source, {}, model)
    assert caught.value.code == "agent_no_progress"
    assert host.effects == [{"path": "a"}]
    assert len(caught.value.tool_calls) == 1


def test_same_call_after_another_call_or_user_reply_is_allowed(
    tmp_path: Path,
) -> None:
    tool = _read_tool()
    payload = _tool_loop_source(tool).to_dict()
    payload["extensions"]["veyra"]["max_turns"] = 6
    source = AgentSource.from_dict(payload)
    host = _HarnessHost(tmp_path, tool)
    call_a = {"action": "tool", "tool": tool["reference"], "arguments": {"path": "a"}}
    call_b = {"action": "tool", "tool": tool["reference"], "arguments": {"path": "b"}}
    model = _ScriptedLoopModel(
        call_a,
        call_b,
        call_a,
        {"action": "ask_user", "question": "Re-read?"},
        call_a,
        {"action": "final", "outputs": {"translation": "ok"}},
    )
    paused = host._execute_loop("project", "run", source, {}, model)
    assert paused.pause is not None
    reply = {**paused.pause.values, "$agent_reply": "yes"}
    finished = host._execute_loop("project", "run", source, reply, model)
    assert finished.result == {"translation": "ok"}
    assert host.effects == [{"path": "a"}, {"path": "b"}, {"path": "a"}, {"path": "a"}]
    assert not _kinds(host, "tool.input_rejected")


def test_repeated_write_is_rejected_before_a_second_approval(tmp_path: Path) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.write", "1.0.0")
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    call = {
        "action": "tool",
        "tool": tool["reference"],
        "arguments": {"path": "report.txt", "content": "x"},
    }
    model = _ScriptedLoopModel(
        call, call, {"action": "final", "outputs": {"translation": "done"}}
    )
    waiting = host._execute_loop("project", "run", source, {}, model)
    assert waiting.pause is not None
    finished = host._execute_loop(
        "project", "run", source, waiting.pause.values, model, approved=True
    )
    assert finished.result == {"translation": "done"}
    assert len(host.effects) == 1
    assert [item["code"] for item in _kinds(host, "tool.input_rejected")] == [
        "tool_call_repeated"
    ]


def test_only_a_timed_out_observation_may_be_repeated_identically() -> None:
    timed_out = executed_call_state(
        "t", {"q": 1}, {"outcome": "failed", "code": "tool_timeout"}
    )
    failed = executed_call_state(
        "t", {"q": 1}, {"outcome": "failed", "code": "tool_input_invalid"}
    )
    succeeded = executed_call_state("t", {"q": 1}, {"content": "x"})
    assert not is_repeated_call(timed_out, "t", {"q": 1})
    assert is_repeated_call(failed, "t", {"q": 1})
    assert is_repeated_call(succeeded, "t", {"q": 1})
    assert not is_repeated_call(succeeded, "t", {"q": 2})
    assert not is_repeated_call(None, "t", {"q": 1})


def test_last_turn_is_announced_once_to_the_model(tmp_path: Path) -> None:
    tool = _read_tool()
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    model = _ScriptedLoopModel(
        *[
            {"action": "tool", "tool": tool["reference"], "arguments": {"path": p}}
            for p in "abc"
        ],
        {"action": "final", "outputs": {"translation": "ok"}},
    )
    outcome = host._execute_loop("project", "run", source, {}, model)
    assert outcome.result == {"translation": "ok"}
    notice = final_turn_notice(source.max_turns)
    assert [notice in call[-1]["content"] for call in model.calls] == [
        False,
        False,
        False,
        True,
    ]
    assert model.calls[3][-1]["role"] == "user"
    assert model.calls[3][-1]["content"].count(notice) == 1
