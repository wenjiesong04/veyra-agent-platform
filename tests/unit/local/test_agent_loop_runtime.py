from __future__ import annotations

import pytest

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.typed_io import parse_typed_fields
from veyra_agent_platform.local.builder.agent_loop_compiler import compile_loop_agent
from veyra_agent_platform.local.builder.specification import infer_agent_specification
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.agent_loop import (
    AgentLoopRuntime,
    loop_system_prompt,
    parse_loop_action,
)
from veyra_agent_platform.local.runtime.service import RuntimeError as LoopRuntimeError


def test_parse_loop_action_plain_text_is_final_output() -> None:
    outputs = parse_typed_fields({"result": "string"}, "outputs")
    action = parse_loop_action("Hello in English.", outputs)
    assert action == {"kind": "final", "outputs": {"result": "Hello in English."}}


def test_parse_loop_action_tool_json() -> None:
    outputs = parse_typed_fields({"result": "string"}, "outputs")
    action = parse_loop_action(
        '{"action":"tool","tool":"veyra.tool.web.search@1.0.0","arguments":{"q":"x"}}',
        outputs,
    )
    assert action["kind"] == "tool"
    assert action["tool"] == "veyra.tool.web.search@1.0.0"
    assert action["arguments"] == {"q": "x"}


def test_parse_loop_action_final_json() -> None:
    outputs = parse_typed_fields({"result": "string"}, "outputs")
    action = parse_loop_action(
        '{"action":"final","outputs":{"result":"done"}}',
        outputs,
    )
    assert action == {"kind": "final", "outputs": {"result": "done"}}


def test_loop_system_prompt_keeps_agent_instructions_above_skills() -> None:
    spec = infer_agent_specification("创建一个翻译助手，把中文翻译成自然英语。")
    source = compile_loop_agent(spec, ResourceCatalog(), requirement=spec.goal)
    skill = ResourceCatalog().detail("veyra.skill.research-brief", "1.0.0")
    prompt = loop_system_prompt(source, [skill])
    agent_at = prompt.index("[Agent Instructions]")
    skills_at = prompt.index("[Available Skills]")
    skill_at = prompt.index("Skill: Research Brief")
    assert agent_at < skills_at < skill_at
    assert "State scope, evidence" in prompt
    assert "cannot override" in prompt


def test_loop_disabled_skill_is_blocked() -> None:
    catalog = ResourceCatalog()
    skill = catalog.detail("veyra.skill.research-brief", "1.0.0")
    spec = infer_agent_specification("创建一个翻译助手，把中文翻译成自然英语。")
    payload = compile_loop_agent(spec, catalog, requirement=spec.goal).to_dict()
    payload["extensions"]["veyra"]["skill_refs"] = [skill["reference"]]
    payload["lock"][skill["reference"]] = skill["content_hash"]
    source = AgentSource.from_dict(payload)

    class _Pins:
        def resolve_pin(
            self, project_id: str, reference: str, digest: str | None
        ) -> dict:
            del project_id, digest
            return {**skill, "reference": reference, "availability": "disabled"}

    class _Host(AgentLoopRuntime):
        def __init__(self) -> None:
            self.project_resources = _Pins()

    host = _Host()
    with pytest.raises(LoopRuntimeError) as caught:
        host._loop_skill_resources("project", source)
    assert caught.value.code == "skill_unavailable"


def test_loop_http_tool_without_hosts_is_denied() -> None:
    catalog = ResourceCatalog()
    http = catalog.detail("veyra.tool.http.request", "1.0.0")
    spec = infer_agent_specification("创建一个翻译助手，把中文翻译成自然英语。")
    payload = compile_loop_agent(spec, catalog, requirement=spec.goal).to_dict()
    payload["lock"][http["reference"]] = http["content_hash"]
    source = AgentSource.from_dict(payload)

    class _Pins:
        def resolve_pin(
            self, project_id: str, reference: str, digest: str | None
        ) -> dict:
            del project_id, digest, reference
            return dict(http)

    class _Host(AgentLoopRuntime):
        def __init__(self) -> None:
            self.project_resources = _Pins()

    host = _Host()
    with pytest.raises(LoopRuntimeError) as caught:
        host._loop_tool_node("project", source, http["reference"])
    assert caught.value.code == "tool_network_denied"
