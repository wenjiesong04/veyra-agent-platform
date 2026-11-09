from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from veyra_agent_platform.contracts.agent import AgentSource, FlowNode
from veyra_agent_platform.contracts.typed_io import parse_typed_fields
from veyra_agent_platform.local.builder.agent_loop_compiler import compile_loop_agent
from veyra_agent_platform.local.builder.specification import infer_agent_specification
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.resources.project import ProjectResourceError
from veyra_agent_platform.local.runtime.agent_loop import (
    LOOP_STATE_KEY,
    AgentLoopRuntime,
    _observation_text,
    _resolve_tool_reference,
    _tool_input_error,
    loop_system_prompt,
    parse_loop_action,
)
from veyra_agent_platform.local.runtime.service import RuntimeError as LoopRuntimeError
from veyra_agent_platform.local.runtime.service import _RunAbandoned, _uses_image_model
from veyra_agent_platform.local.runtime.tools import (
    ToolExecution,
    ToolRuntime,
    ToolRuntimeError,
)


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


def test_large_tool_observation_is_valid_json_with_explicit_incomplete_evidence() -> (
    None
):
    reference = "fixture.large-report@1.0.0"
    output = {"rows": [{"note": 'quoted "text"\\path\n下一行' * 1_000}], "total": 37}
    raw = json.dumps(output, ensure_ascii=False)
    observation = _observation_text(reference, output)
    heading, body = observation.split("\n", 1)
    assert heading == f"Tool result for {reference}:"
    assert len(body) <= 8_000
    partial = json.loads(body)
    assert partial["truncated"] is True
    assert partial["original_char_count"] == len(raw)
    assert raw.startswith(partial["excerpt"])
    assert 0 < len(partial["excerpt"]) < len(raw)
    assert "only a prefix" in partial["notice"]
    assert "Do not infer absence or complete coverage" in partial["notice"]
    assert "total" not in partial

    complete = {"rows": [{"note": 'quoted "text"\\path\n下一行'}], "total": 1}
    small_body = _observation_text(reference, complete).split("\n", 1)[1]
    assert json.loads(small_body) == complete
    assert "truncated" not in json.loads(small_body)


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


def _image_loop_source() -> AgentSource:
    spec = infer_agent_specification("创建一个翻译助手，把中文翻译成自然英语。")
    source = compile_loop_agent(spec, ResourceCatalog(), requirement=spec.goal)
    payload = source.to_dict()
    payload["outputs"] = {
        "render": {"type": "artifact", "artifact_kind": "image"},
        "result": "object",
    }
    for node in payload["nodes"]:
        if node["component_type"] == "Output":
            node["output_name"] = "render"
    return AgentSource.from_dict(payload)


def test_loop_prompt_leaves_image_outputs_to_the_image_model() -> None:
    prompt = loop_system_prompt(_image_loop_source())
    assert "Declared outputs: result:object." in prompt
    assert "Image outputs (render) must use actual images" in prompt
    assert "actual artifact references returned by render_images" in prompt
    assert "Do not return them" not in prompt


def test_loop_renders_declared_image_outputs_with_image_model() -> None:
    source = _image_loop_source()
    calls: list[FlowNode] = []
    events: list[tuple[str | None, str]] = []

    class _Host(AgentLoopRuntime):
        def _run_image_model(self, project_id, run_id, node, source, values, emit):
            del project_id, run_id, source, values, emit
            calls.append(node)
            ref = {"kind": "artifact", "artifact_id": "a1", "media_type": "image/png"}
            return {node.id: {"render": ref}, "render": ref}

    rendered = _Host()._loop_render_images(
        "project",
        "run",
        source,
        {"message": "gift", "render": "text the model invented"},
        {"result": {"style": "warm paper wrap"}},
        lambda node_id, kind, payload: events.append((node_id, kind)),
    )
    assert rendered["render"]["artifact_id"] == "a1"
    assert len(calls) == 1
    assert calls[0].model_ref == "model.image"
    assert set(calls[0].outputs or {}) == {"render"}
    assert "warm paper wrap" in (calls[0].system_prompt or "")
    assert events == [
        ("render_render", "node.started"),
        ("render_render", "node.completed"),
    ]


def test_loop_image_output_requires_image_model_binding() -> None:
    assert _uses_image_model(_image_loop_source())


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


def _tool_loop_source(resource: dict[str, Any]) -> AgentSource:
    catalog = ResourceCatalog()
    spec = infer_agent_specification("创建一个翻译助手，把中文翻译成自然英语。")
    payload = compile_loop_agent(spec, catalog, requirement=spec.goal).to_dict()
    reference = resource["reference"]
    payload["lock"][reference] = resource["content_hash"]
    payload["ui"].setdefault("bindings", {})["tool_fixture"] = {
        "kind": "tool",
        "reference": reference,
        "x": 40,
        "y": 40,
    }
    payload["extensions"]["veyra"]["permissions"] = deepcopy(
        resource["required_permissions"]
    )
    payload["extensions"]["veyra"]["max_turns"] = 4
    return AgentSource.from_dict(payload)


class _PinnedResources:
    def __init__(self, resource: dict[str, Any]) -> None:
        self.resource = resource

    def resolve_pin(self, project_id, reference, digest):
        del project_id
        if (
            reference != self.resource["reference"]
            or digest != self.resource["content_hash"]
        ):
            raise ProjectResourceError("resource_lock_mismatch", "Pin mismatch")
        return deepcopy(self.resource)


class _ScriptedLoopModel:
    def __init__(self, *actions: dict[str, Any]) -> None:
        self.actions = iter(actions)
        self.calls: list[list[dict[str, Any]]] = []

    def complete(self, messages):
        self.calls.append(deepcopy(messages))
        return SimpleNamespace(
            content=json.dumps(next(self.actions)), finish_reason="stop"
        )


class _HarnessHost(AgentLoopRuntime):
    def __init__(self, root: Path, resource: dict[str, Any], adapter=None) -> None:
        self.project_resources = _PinnedResources(resource)
        self.resource = resource
        self.events: list[tuple[str | None, str, dict[str, Any]]] = []
        self.effects: list[dict[str, Any]] = []
        self.repository = SimpleNamespace(
            project=lambda project_id: {"root_path": str(root)}
        )
        self.projects = SimpleNamespace(_existing_root=Path)
        self.tools = ToolRuntime(
            ResourceCatalog(),
            adapters={resource["spec"]["adapter"]: adapter or self._adapter},
        )

    def _adapter(self, **kwargs):
        self.effects.append(dict(kwargs["values"]))
        return ToolExecution(
            output={"content": "fixture observation"},
            receipt={
                "outcome": "succeeded",
                "tool_reference": self.resource["reference"],
            },
        )

    def _persist_event(self, run_id, node_id, kind, payload):
        del run_id
        self.events.append((node_id, kind, payload))

    def _is_running(self, run_id):
        del run_id
        return True

    def _require_bound_model_capabilities(self, *args):
        del args

    def _runtime_model_capabilities_for_slot(self, *args):
        del args
        return None

    def _model_user_content(self, project_id, source, values, capabilities):
        del project_id, source, capabilities
        return json.dumps(values)

    def _provider_user_content(self, project_id, content):
        del project_id
        return content

    def _prepare_outputs(self, project_id, source, values):
        del project_id
        return {name: values[name] for name in source.outputs if name in values}

    def _authorize_tool(self, project_id, source, node, values):
        resource = self.project_resources.resolve_pin(
            project_id, node.uses, source.lock[node.uses]
        )
        return self.tools.authorize(
            source=source, node=node, values=values, resource=resource
        )


def test_loop_prompt_exposes_pinned_tool_schema_and_approval_without_host_secrets(
    tmp_path: Path,
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.write", "1.0.0")
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    messages = host._loop_opening_messages("project", source, {}, None, "", [], "")
    prompt = messages[0]["content"]
    assert tool["reference"] in prompt
    assert tool["description"] in prompt
    assert '"input_schema": {"content": "string", "path": "string"}' in prompt
    assert '"output_schema": {"written": "boolean"}' in prompt
    assert '"approval_required": true' in prompt
    assert "veyra.runtime.filesystem.write" not in prompt
    assert not host.effects

    configured = deepcopy(tool)
    configured["spec"].update(
        secret_ref="host-reference",
        secret_env="HOST_ENV",
        secret_value="fixture-secret",
    )
    projection = loop_system_prompt(source, [], [configured])
    assert "host-reference" not in projection
    assert "HOST_ENV" not in projection
    assert "fixture-secret" not in projection


def test_loop_exposes_complete_output_contract_and_repairs_declared_constraints(
    tmp_path: Path,
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    payload = _tool_loop_source(tool).to_dict()
    payload["outputs"]["translation"] = {
        "type": "string",
        "multiple": True,
        "enum": ["ready", "blocked"],
        "description": "Return a list of declared readiness labels",
    }
    payload["outputs"]["summary"] = {
        "type": "object",
        "required": False,
        "json_schema": {
            "type": "object",
            "properties": {"count": {"type": "integer", "minimum": 1}},
            "required": ["count"],
        },
    }
    source = AgentSource.from_dict(payload)
    host = _HarnessHost(tmp_path, tool)
    model = _ScriptedLoopModel(
        {"action": "final", "outputs": {"translation": ["unknown"]}},
        {
            "action": "final",
            "outputs": {"translation": ["ready"], "summary": {"count": 1}},
        },
    )
    outcome = host._execute_loop("project", "run", source, {}, model)
    assert outcome.result == {"translation": ["ready"], "summary": {"count": 1}}
    prompt = model.calls[0][0]["content"]
    assert (
        json.dumps({name: field.to_wire() for name, field in source.outputs.items()})
        in prompt
    )
    feedback = json.loads(model.calls[1][-1]["content"].split("\n", 1)[1])
    assert feedback["fields"] == [
        {
            "name": "translation",
            "reason": "value_does_not_match_contract",
            "contract": source.outputs["translation"].to_wire(),
        }
    ]
    assert not host.effects


def test_loop_output_validation_feedback_is_bounded_and_does_not_echo_values(
    tmp_path: Path,
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    model = _ScriptedLoopModel(
        {"action": "final", "outputs": {"translation": {"private": "a" * 30_000}}},
        {"action": "final", "outputs": {"translation": "corrected"}},
    )
    outcome = host._execute_loop("project", "run", source, {}, model)
    assert outcome.result == {"translation": "corrected"}
    feedback = model.calls[1][-1]["content"]
    assert len(feedback) <= 8_000
    assert "a" * 200 not in feedback
    assert "value_does_not_match_contract" in feedback


@pytest.mark.parametrize(
    ("invalid", "keyword"),
    [
        ({"answer": {}}, "required"),
        ({"answer": {"count": 1}, "extra": "private-value"}, "additionalProperties"),
        ({"answer": {"count": "private-value"}}, "type"),
        ({"answer": {"count": 0}}, "minimum"),
        ({"answer": {"count": float("nan")}}, "json_value"),
    ],
)
def test_loop_nested_output_schema_returns_safe_keywords_and_can_be_corrected(
    tmp_path: Path, invalid: dict[str, Any], keyword: str
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    payload = _tool_loop_source(tool).to_dict()
    payload["outputs"]["translation"] = {
        "type": "object",
        "json_schema": {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "object",
                    "properties": {"count": {"type": "integer", "minimum": 1}},
                    "required": ["count"],
                    "additionalProperties": False,
                }
            },
            "required": ["answer"],
            "additionalProperties": False,
        },
    }
    source = AgentSource.from_dict(payload)
    host = _HarnessHost(tmp_path, tool)
    corrected = {"answer": {"count": 1}}
    model = _ScriptedLoopModel(
        {"action": "final", "outputs": {"translation": invalid}},
        {"action": "final", "outputs": {"translation": corrected}},
    )
    outcome = host._execute_loop("project", "run", source, {}, model)
    assert outcome.result == {"translation": corrected}
    assert outcome.verified is False
    feedback = model.calls[1][-1]["content"]
    assert "private-value" not in feedback
    error = json.loads(feedback.split("\n", 1)[1])["fields"][0]
    assert error["reason"] == "json_schema_violation"
    assert error["keywords"] == [keyword]
    assert error["contract"] == source.outputs["translation"].to_wire()


def test_loop_multiple_output_schema_validates_each_item(tmp_path: Path) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    payload = _tool_loop_source(tool).to_dict()
    payload["outputs"]["translation"] = {
        "type": "object",
        "multiple": True,
        "json_schema": {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
        },
    }
    source = AgentSource.from_dict(payload)
    host = _HarnessHost(tmp_path, tool)
    corrected = [{"count": 1}, {"count": 2}]
    model = _ScriptedLoopModel(
        {"action": "final", "outputs": {"translation": [{"count": 1}, {}]}},
        {"action": "final", "outputs": {"translation": corrected}},
    )
    outcome = host._execute_loop("project", "run", source, {}, model)
    assert outcome.result == {"translation": corrected}
    error = json.loads(model.calls[1][-1]["content"].split("\n", 1)[1])["fields"][0]
    assert error["keywords"] == ["required"]


def test_loop_optional_output_schema_can_be_omitted(tmp_path: Path) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    payload = _tool_loop_source(tool).to_dict()
    payload["outputs"]["summary"] = {
        "type": "object",
        "required": False,
        "json_schema": {"type": "object", "required": ["count"]},
    }
    source = AgentSource.from_dict(payload)
    host = _HarnessHost(tmp_path, tool)
    model = _ScriptedLoopModel(
        {"action": "final", "outputs": {"translation": "finished"}}
    )
    outcome = host._execute_loop("project", "run", source, {}, model)
    assert outcome.result == {"translation": "finished"}
    assert len(model.calls) == 1


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "imaginary"},
        {"$ref": "https://example.invalid/private-schema"},
        {"allOf": [{"type": "object"}]},
        {
            "type": "object",
            "properties": {str(index): {"type": "string"} for index in range(257)},
        },
    ],
)
def test_loop_unsupported_output_schema_fails_before_model_or_tool_calls(
    tmp_path: Path, schema: dict[str, Any]
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    payload = _tool_loop_source(tool).to_dict()
    payload["outputs"]["translation"] = {"type": "object", "json_schema": schema}
    source = AgentSource.from_dict(payload)
    host = _HarnessHost(tmp_path, tool)
    model = _ScriptedLoopModel(
        {"action": "final", "outputs": {"translation": {"count": 1}}}
    )
    with pytest.raises(LoopRuntimeError) as caught:
        host._execute_loop("project", "run", source, {}, model)
    assert caught.value.code == "agent_output_schema_unsupported"
    assert not model.calls
    assert not host.effects
    assert not host.events


def test_loop_native_read_failure_can_change_tool_then_correct_its_arguments(
    tmp_path: Path,
) -> None:
    catalog = ResourceCatalog()
    read = catalog.detail("veyra.tool.filesystem.read", "1.0.0")
    listing = catalog.detail("veyra.tool.filesystem.list", "1.0.0")
    payload = _tool_loop_source(read).to_dict()
    payload["lock"][listing["reference"]] = listing["content_hash"]
    payload["ui"]["bindings"]["tool_list"] = {
        "kind": "tool",
        "reference": listing["reference"],
        "x": 80,
        "y": 80,
    }
    payload["extensions"]["veyra"]["permissions"]["tools"].append(
        listing["resource_id"]
    )
    source = AgentSource.from_dict(payload)
    host = _HarnessHost(tmp_path, read)
    resources = {item["reference"]: item for item in (read, listing)}

    def resolve_pin(project_id, reference, digest):
        del project_id
        resource = resources[reference]
        assert digest == resource["content_hash"]
        return deepcopy(resource)

    host.project_resources = SimpleNamespace(resolve_pin=resolve_pin)
    host.tools = ToolRuntime(catalog)
    (tmp_path / "notes.txt").write_text("Synthetic evidence", encoding="utf-8")
    model = _ScriptedLoopModel(
        {
            "action": "tool",
            "tool": read["reference"],
            "arguments": {"path": "absent.txt"},
        },
        {"action": "tool", "tool": listing["reference"], "arguments": {"path": "."}},
        {
            "action": "tool",
            "tool": read["reference"],
            "arguments": {"path": "notes.txt"},
        },
        {"action": "final", "outputs": {"translation": "finished"}},
    )
    outcome = host._execute_loop("project", "run", source, {}, model)
    assert outcome.result == {"translation": "finished"}
    assert len(outcome.tool_calls) == 3
    assert outcome.tool_calls[0].receipt["outcome"] == "failed"
    assert outcome.tool_calls[0].receipt["recovery"] == "observe"
    feedback = json.loads(model.calls[1][-1]["content"].split("\n", 1)[1])
    assert feedback["outcome"] == "failed"
    assert feedback["effect_status"] == "read_only"
    assert feedback["input_schema"] == read["spec"]["input_schema"]
    assert "not retried" in feedback["notice"]
    assert any(kind == "tool.failed" for _, kind, _ in host.events)
    assert "Synthetic evidence" in model.calls[3][-1]["content"]
    assert len(model.calls) == source.max_turns


def test_loop_native_search_failure_preserves_approval_and_does_not_echo_exception(
    tmp_path: Path,
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.web.search", "1.0.0")
    host = _HarnessHost(tmp_path, tool)
    requests: list[httpx.Request] = []

    def search(request):
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ReadTimeout("private-host-path-and-secret", request=request)
        return httpx.Response(200, text="<html><body>Synthetic result</body></html>")

    host.tools = ToolRuntime(
        ResourceCatalog(),
        http_client=httpx.Client(transport=httpx.MockTransport(search)),
    )
    source = _tool_loop_source(tool)
    model = _ScriptedLoopModel(
        {"action": "tool", "tool": tool["reference"], "arguments": {"query": "first"}},
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"query": "revised"},
        },
        {"action": "final", "outputs": {"translation": "finished"}},
    )
    first = host._execute_loop("project", "run", source, {}, model)
    assert first.pause is not None
    assert not requests
    second = host._execute_loop(
        "project", "run", source, first.pause.values, model, approved=True
    )
    assert second.pause is not None
    assert len(requests) == 1
    assert second.tool_calls[0].receipt["outcome"] == "failed"
    assert second.tool_calls[0].receipt["code"] == "tool_timeout"
    feedback = model.calls[1][-1]["content"]
    assert "private-host-path-and-secret" not in feedback
    assert '"code": "tool_timeout"' in feedback
    assert '"recoverable": true' in feedback
    finished = host._execute_loop(
        "project", "run", source, second.pause.values, model, approved=True
    )
    assert finished.result == {"translation": "finished"}
    assert len(requests) == 2


def test_loop_native_arithmetic_failure_uses_existing_turn_budget(
    tmp_path: Path,
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.math.calculate", "1.0.0")
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    host.tools = ToolRuntime(ResourceCatalog())
    model = _ScriptedLoopModel(
        *[
            {
                "action": "tool",
                "tool": tool["reference"],
                "arguments": {"expression": f"sum(1, {index})"},
            }
            for index in range(source.max_turns)
        ]
    )
    outcome = host._execute_loop("project", "run", source, {}, model)
    assert outcome.pause is not None and outcome.pause.details["kind"] == "budget"
    assert len(model.calls) == source.max_turns
    assert len(outcome.tool_calls) == source.max_turns
    assert len([kind for _, kind, _ in host.events if kind == "tool.failed"]) == (
        source.max_turns
    )


def test_loop_read_failure_receipt_survives_a_later_provider_failure(
    tmp_path: Path,
) -> None:
    from veyra_agent_platform.local.runtime.client import RuntimeProviderError

    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    host.tools = ToolRuntime(ResourceCatalog())

    class Model:
        def __init__(self):
            self.calls = 0

        def complete(self, messages):
            del messages
            self.calls += 1
            if self.calls > 1:
                raise RuntimeProviderError("runtime_rate_limited", "Synthetic limit")
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "action": "tool",
                        "tool": tool["reference"],
                        "arguments": {"path": "absent.txt"},
                    }
                )
            )

    model = Model()
    with pytest.raises(LoopRuntimeError) as caught:
        host._execute_loop("project", "run", source, {}, model)
    assert caught.value.code == "runtime_rate_limited"
    assert len(caught.value.tool_calls) == 1
    assert caught.value.tool_calls[0].receipt["outcome"] == "failed"
    assert caught.value.tool_calls[0].receipt["recovery"] == "observe"
    assert model.calls == 2


@pytest.mark.parametrize(
    ("next_failure", "code"),
    [
        ("authorization", "tool_unavailable"),
        ("tool_contract", "tool_schema_invalid"),
        ("output_binding", "output_invalid"),
        ("image", "image_model_failed"),
        ("image_provider", "runtime_timeout"),
        ("image_tool", "tool_failed"),
        ("unknown", "executor_failed"),
    ],
)
def test_loop_read_failure_receipt_survives_every_terminal_exit(
    tmp_path: Path, next_failure: str, code: str
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    payload = _tool_loop_source(tool).to_dict()
    if next_failure in {"image", "image_provider", "image_tool"}:
        payload["outputs"]["render"] = {"type": "artifact", "artifact_kind": "image"}
    source = AgentSource.from_dict(payload)
    host = _HarnessHost(tmp_path, tool)
    host.tools = ToolRuntime(ResourceCatalog())

    def binding_failure(*args):
        del args
        raise LoopRuntimeError("output_invalid", "Synthetic binding failure")

    def image_failure(*args):
        del args
        if next_failure == "image_provider":
            from veyra_agent_platform.local.runtime.client import RuntimeProviderError

            raise RuntimeProviderError("runtime_timeout", "Synthetic image timeout")
        if next_failure == "image_tool":
            raise ToolRuntimeError("tool_failed", "Synthetic image tool failure")
        raise LoopRuntimeError("image_model_failed", "Synthetic image failure")

    if next_failure == "output_binding":
        host._prepare_outputs = binding_failure
    if next_failure in {"image", "image_provider", "image_tool"}:
        host._run_image_model = image_failure

    class Model:
        def __init__(self):
            self.calls = 0

        def complete(self, messages):
            del messages
            self.calls += 1
            if self.calls == 1:
                action = {
                    "action": "tool",
                    "tool": tool["reference"],
                    "arguments": {"path": "absent.txt"},
                }
            else:
                if next_failure == "authorization":
                    tool["availability"] = "disabled"
                elif next_failure == "tool_contract":
                    tool["spec"]["input_constraints"] = {"path": {"type": "imaginary"}}
                elif next_failure == "unknown":
                    raise ValueError("private-exception-body")
                action = (
                    {
                        "action": "tool",
                        "tool": tool["reference"],
                        "arguments": {"path": "notes.txt"},
                    }
                    if next_failure in {"authorization", "tool_contract"}
                    else {"action": "final", "outputs": {"translation": "finished"}}
                )
            return SimpleNamespace(content=json.dumps(action))

    model = Model()
    with pytest.raises(LoopRuntimeError) as caught:
        host._execute_loop("project", "run", source, {}, model)
    assert caught.value.code == code
    assert len(caught.value.tool_calls) == 1
    assert caught.value.tool_calls[0].receipt["outcome"] == "failed"
    assert caught.value.tool_calls[0].receipt["recovery"] == "observe"
    assert "private-exception-body" not in str(caught.value)
    assert model.calls == 2


def test_loop_native_path_denial_is_not_recoverable(tmp_path: Path) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    host.tools = ToolRuntime(ResourceCatalog())
    model = _ScriptedLoopModel(
        {"action": "tool", "tool": tool["reference"], "arguments": {"path": ".env"}},
        {"action": "final", "outputs": {"translation": "must not continue"}},
    )
    with pytest.raises(LoopRuntimeError) as caught:
        host._execute_loop("project", "run", source, {}, model)
    assert caught.value.code == "tool_path_denied"
    assert len(model.calls) == 1


def test_loop_native_write_failure_remains_terminal_after_approval(
    tmp_path: Path,
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.write", "1.0.0")
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    host.tools = ToolRuntime(ResourceCatalog())
    (tmp_path / "directory").mkdir()
    model = _ScriptedLoopModel(
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"path": "directory", "content": "Synthetic material"},
        },
        {"action": "final", "outputs": {"translation": "must not continue"}},
    )
    waiting = host._execute_loop("project", "run", source, {}, model)
    assert waiting.pause is not None
    with pytest.raises(LoopRuntimeError) as caught:
        host._execute_loop(
            "project", "run", source, waiting.pause.values, model, approved=True
        )
    assert caught.value.code == "tool_input_invalid"
    assert len(model.calls) == 1


def test_loop_missing_secret_is_not_recoverable(tmp_path: Path) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    tool["spec"].update(secret_ref="synthetic-secret", secret_env="SYNTHETIC_SECRET")
    payload = _tool_loop_source(tool).to_dict()
    payload["extensions"]["veyra"]["secret_refs"] = ["synthetic-secret"]
    source = AgentSource.from_dict(payload)
    host = _HarnessHost(tmp_path, tool)
    host.tools._secret_value = lambda *args: ""
    model = _ScriptedLoopModel(
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"path": "notes.txt"},
        },
        {"action": "final", "outputs": {"translation": "must not continue"}},
    )
    with pytest.raises(LoopRuntimeError) as caught:
        host._execute_loop("project", "run", source, {}, model)
    assert caught.value.code == "secret_not_configured"
    assert len(model.calls) == 1
    assert not host.effects


@pytest.mark.parametrize("state", ["disabled", "requires_configuration"])
def test_loop_prompt_omits_tools_not_ready_for_runtime(
    tmp_path: Path, state: str
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    source = _tool_loop_source(tool)
    tool["availability"] = state
    host = _HarnessHost(tmp_path, tool)
    prompt = host._loop_opening_messages("project", source, {}, None, "", [], "")[0][
        "content"
    ]
    assert tool["reference"] not in prompt
    assert not host.effects


@pytest.mark.parametrize(
    "bad_arguments", [{"path": 17}, {"filename": "notes.txt"}, ["notes.txt"]]
)
def test_loop_recovers_only_from_offline_input_validation_before_one_effect(
    tmp_path: Path, bad_arguments: Any
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    model = _ScriptedLoopModel(
        {"action": "tool", "tool": tool["reference"], "arguments": bad_arguments},
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"path": "notes.txt"},
        },
        {"action": "final", "outputs": {"translation": "done"}},
    )
    outcome = host._execute_loop("project", "run", source, {}, model)
    assert outcome.result == {"translation": "done"}
    assert host.effects == [{"path": "notes.txt"}]
    assert len(model.calls) == 3
    assert "No tool was executed" in model.calls[1][-1]["content"]
    assert "fixture observation" in model.calls[2][-1]["content"]
    assert len(outcome.tool_calls) == 1
    assert outcome.tool_calls[0].receipt["outcome"] == "succeeded"
    rejected = [
        payload for _, kind, payload in host.events if kind == "tool.input_rejected"
    ]
    assert len(rejected) == 1
    assert rejected[0]["effect_started"] is False
    assert len([kind for _, kind, _ in host.events if kind == "tool.started"]) == 1


def test_loop_authorization_denial_is_not_a_recoverable_tool_error(
    tmp_path: Path,
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    payload = _tool_loop_source(tool).to_dict()
    payload["extensions"]["veyra"]["permissions"]["tools"] = []
    source = AgentSource.from_dict(payload)
    host = _HarnessHost(tmp_path, tool)
    model = _ScriptedLoopModel(
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"path": "notes.txt"},
        },
        {"action": "final", "outputs": {"translation": "must not continue"}},
    )
    with pytest.raises(LoopRuntimeError) as caught:
        host._execute_loop("project", "run", source, {}, model)
    assert caught.value.code == "tool_permission_denied"
    assert len(model.calls) == 1
    assert tool["reference"] not in model.calls[0][0]["content"]
    assert not host.effects
    assert not any(kind == "tool.input_rejected" for _, kind, _ in host.events)


def test_loop_corrects_unknown_tool_name_without_executing_it(tmp_path: Path) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    host = _HarnessHost(tmp_path, tool)
    model = _ScriptedLoopModel(
        {"action": "tool", "tool": "invented.search", "arguments": {}},
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"path": "notes.txt"},
        },
        {"action": "final", "outputs": {"translation": "done"}},
    )
    outcome = host._execute_loop("project", "run", _tool_loop_source(tool), {}, model)
    assert outcome.result == {"translation": "done"}
    assert host.effects == [{"path": "notes.txt"}]
    assert "No tool was executed" in model.calls[1][-1]["content"]
    assert len(outcome.tool_calls) == 1
    rejected = [
        payload for _, kind, payload in host.events if kind == "tool.input_rejected"
    ]
    assert rejected[0]["code"] == "tool_reference_invalid"
    assert rejected[0]["effect_started"] is False


def test_loop_ambiguous_short_tool_name_requires_exact_reference() -> None:
    catalog = ResourceCatalog()
    read = catalog.detail("veyra.tool.filesystem.read", "1.0.0")
    entity = catalog.detail("veyra.tool.entity.read", "1.0.0")
    payload = _tool_loop_source(read).to_dict()
    payload["lock"][entity["reference"]] = entity["content_hash"]
    payload["extensions"]["veyra"]["permissions"]["tools"].append(entity["resource_id"])
    source = AgentSource.from_dict(payload)
    assert _resolve_tool_reference(source, "read") is None
    assert _resolve_tool_reference(source, read["reference"]) == read["reference"]
    assert _resolve_tool_reference(source, entity["reference"]) == entity["reference"]


def test_loop_prompt_never_exposes_a_tool_after_pin_hash_mismatch(
    tmp_path: Path,
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    payload = _tool_loop_source(tool).to_dict()
    payload["lock"][tool["reference"]] = "0" * 64
    source = AgentSource.from_dict(payload)
    host = _HarnessHost(tmp_path, tool)
    prompt = host._loop_opening_messages("project", source, {}, None, "", [], "")[0][
        "content"
    ]
    assert tool["reference"] not in prompt
    assert not host.effects


def test_loop_corrected_write_request_still_pauses_for_explicit_approval(
    tmp_path: Path,
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.write", "1.0.0")
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    model = _ScriptedLoopModel(
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"path": 17, "content": "fixture"},
        },
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"path": "notes.txt", "content": "fixture"},
        },
        {"action": "final", "outputs": {"translation": "done"}},
    )
    waiting = host._execute_loop("project", "run", source, {}, model)
    assert waiting.pause is not None
    assert waiting.pause.details["kind"] == "tool_permission"
    assert waiting.pause.values[LOOP_STATE_KEY]["turn"] == 2
    assert not host.effects
    finished = host._execute_loop(
        "project", "run", source, waiting.pause.values, model, approved=True
    )
    assert finished.result == {"translation": "done"}
    assert host.effects == [{"path": "notes.txt", "content": "fixture"}]
    assert len(finished.tool_calls) == 1


def test_loop_resumed_transcript_refreshes_catalog_after_tool_is_disabled(
    tmp_path: Path,
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.write", "1.0.0")
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    model = _ScriptedLoopModel(
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"path": "notes.txt", "content": "fixture"},
        },
        {"action": "final", "outputs": {"translation": "finished without writing"}},
    )
    waiting = host._execute_loop("project", "run", source, {}, model)
    tool["availability"] = "disabled"
    finished = host._execute_loop("project", "run", source, waiting.pause.values, model)
    assert finished.result == {"translation": "finished without writing"}
    assert tool["reference"] not in model.calls[1][0]["content"]
    assert not host.effects


def test_loop_does_not_retry_adapter_error_even_if_it_uses_input_invalid_code(
    tmp_path: Path,
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    effects: list[str] = []

    def adapter(**kwargs):
        effects.append(kwargs["values"]["path"])
        raise ToolRuntimeError(
            "tool_input_invalid", "An adapter may already have performed an effect"
        )

    host = _HarnessHost(tmp_path, tool, adapter)
    model = _ScriptedLoopModel(
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"path": "notes.txt"},
        },
        {"action": "final", "outputs": {"translation": "must not continue"}},
    )
    with pytest.raises(LoopRuntimeError) as caught:
        host._execute_loop("project", "run", _tool_loop_source(tool), {}, model)
    assert caught.value.code == "tool_input_invalid"
    assert len(model.calls) == 1
    assert effects == ["notes.txt"]


def test_loop_schema_repairs_consume_existing_max_turns_budget(tmp_path: Path) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    host = _HarnessHost(tmp_path, tool)
    source = _tool_loop_source(tool)
    bad = {"action": "tool", "tool": tool["reference"], "arguments": {"path": 17}}
    model = _ScriptedLoopModel(*[bad] * source.max_turns)
    outcome = host._execute_loop("project", "run", source, {}, model)
    assert outcome.pause is not None and outcome.pause.details["kind"] == "budget"
    assert len(model.calls) == source.max_turns
    assert not host.effects


def test_loop_preserves_failed_effect_receipt_without_asking_model_to_retry(
    tmp_path: Path,
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    receipt = {"outcome": "failed", "code": "tool_failed", "input_digest": "a" * 64}
    effects: list[str] = []

    def adapter(**kwargs):
        effects.append(kwargs["values"]["path"])
        raise ToolRuntimeError("tool_failed", "Fixture adapter failed", receipt=receipt)

    host = _HarnessHost(tmp_path, tool, adapter)
    model = _ScriptedLoopModel(
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"path": "notes.txt"},
        },
        {"action": "final", "outputs": {"translation": "must not continue"}},
    )
    with pytest.raises(LoopRuntimeError) as caught:
        host._execute_loop("project", "run", _tool_loop_source(tool), {}, model)
    assert effects == ["notes.txt"]
    assert len(model.calls) == 1
    assert len(caught.value.tool_calls) == 1
    assert caught.value.tool_calls[0].authorization == "allowed"
    assert caught.value.tool_calls[0].receipt == receipt
    assert any(
        kind == "tool.failed" and payload == receipt for _, kind, payload in host.events
    )


def test_compact_schema_does_not_invent_required_adapter_default_arguments() -> None:
    search = ResourceCatalog().detail("veyra.tool.web.search", "1.0.0")
    assert _tool_input_error(search, {"query": "fixture query"}) is None


def test_query_limits_are_public_and_validated_before_execution(tmp_path: Path) -> None:
    tool = ResourceCatalog().detail("veyra.tool.entity.query", "1.0.0")
    assert _tool_input_error(tool, {"entity_type": "task", "limit": 1000}) is not None
    assert _tool_input_error(tool, {"entity_type": "task", "limit": 0}) is not None
    assert _tool_input_error(tool, {"entity_type": "task", "limit": 50}) is None
    assert '"maximum": 50' in loop_system_prompt(_tool_loop_source(tool), [], [tool])
    host = _HarnessHost(tmp_path, tool)
    model = _ScriptedLoopModel(
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"entity_type": "task", "limit": 1000},
        },
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"entity_type": "task", "limit": 50},
        },
        {"action": "final", "outputs": {"translation": "done"}},
    )
    host._execute_loop("project", "run", _tool_loop_source(tool), {}, model)
    assert host.effects == [{"entity_type": "task", "limit": 50}]
    assert (
        len([kind for _, kind, _ in host.events if kind == "tool.input_rejected"]) == 1
    )


@pytest.mark.parametrize("repeat_empty", [False, True])
def test_one_empty_provider_completion_can_be_recovered_before_any_action(
    tmp_path: Path, repeat_empty: bool
) -> None:
    from veyra_agent_platform.local.runtime.client import RuntimeProviderError

    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    host = _HarnessHost(tmp_path, tool)

    class Model:
        def __init__(self):
            self.calls = []

        def complete(self, messages):
            self.calls.append(deepcopy(messages))
            if repeat_empty or len(self.calls) == 1:
                raise RuntimeProviderError(
                    "runtime_invalid_response",
                    "Empty completion",
                    diagnostic={"finish_reason": "stop", "content_empty": True},
                )
            return SimpleNamespace(
                content=json.dumps(
                    {"action": "final", "outputs": {"translation": "Recovered"}}
                ),
                finish_reason="stop",
            )

    model = Model()
    if repeat_empty:
        with pytest.raises(LoopRuntimeError) as caught:
            host._execute_loop("project", "run", _tool_loop_source(tool), {}, model)
        assert caught.value.code == "runtime_invalid_response"
    else:
        outcome = host._execute_loop(
            "project", "run", _tool_loop_source(tool), {}, model
        )
        assert outcome.result == {"translation": "Recovered"}
    assert len(model.calls) == 2
    assert not host.effects
    assert (
        len([kind for _, kind, _ in host.events if kind == "model.output_rejected"])
        == 1
    )


def test_mcp_input_schema_is_checked_offline_and_invalid_contract_fails_closed() -> (
    None
):
    from veyra_agent_platform.local.mcp.schema import prepare_contract

    schema = {
        "type": "object",
        "properties": {"query": {"type": "string", "minLength": 1}},
        "required": ["query"],
        "additionalProperties": False,
    }
    tool = {"spec": {"adapter": "veyra.runtime.mcp.call", **prepare_contract(schema)}}
    assert _tool_input_error(tool, {"query": "fixture"}) is None
    assert _tool_input_error(tool, {}) is not None
    assert _tool_input_error(tool, {"query": 17}) is not None
    projected = {"reference": "fixture.mcp@1.0.0", **tool}
    prompt = loop_system_prompt(_image_loop_source(), [], [projected])
    assert '"schema_format": "json_schema"' in prompt
    assert '"output_schema_target": "result.structuredContent"' in prompt
    assert '"required": ["query"]' in prompt
    tool["spec"]["schema_contract_hash"] = "tampered"
    with pytest.raises(LoopRuntimeError) as caught:
        _tool_input_error(tool, {"query": "fixture"})
    assert caught.value.code == "mcp_schema_unsupported"


def test_user_reply_does_not_approve_a_following_write_tool(tmp_path: Path) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.write", "1.0.0")
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    model = _ScriptedLoopModel(
        {"action": "ask_user", "question": "Which report should be written?"},
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"path": "report.txt", "content": "fixture"},
        },
        {"action": "final", "outputs": {"translation": "done"}},
    )
    question = host._execute_loop("project", "run", source, {}, model)
    assert question.pause is not None
    assert question.pause.details["kind"] == "input"
    assert not host.effects
    reply = {**question.pause.values, "$agent_reply": "The review report"}
    approval = host._execute_loop("project", "run", source, reply, model, approved=True)
    assert approval.pause is not None
    assert approval.pause.details["kind"] == "tool_permission"
    assert not host.effects
    finished = host._execute_loop(
        "project", "run", source, approval.pause.values, model, approved=True
    )
    assert finished.result == {"translation": "done"}
    assert len(host.effects) == 1


def test_stopped_run_cannot_execute_its_previously_approved_pending_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.write", "1.0.0")
    source = _tool_loop_source(tool)
    host = _HarnessHost(tmp_path, tool)
    model = _ScriptedLoopModel(
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"path": "report.txt", "content": "synthetic report"},
        },
        {"action": "final", "outputs": {"translation": "must not finish"}},
    )
    waiting = host._execute_loop("project", "run", source, {}, model)
    assert waiting.pause is not None
    assert waiting.pause.details["kind"] == "tool_permission"
    monkeypatch.setattr(host, "_is_running", lambda run_id: False)

    with pytest.raises(_RunAbandoned):
        host._execute_loop(
            "project", "run", source, waiting.pause.values, model, approved=True
        )

    assert len(model.calls) == 1
    assert not host.effects
    assert not any(kind == "tool.started" for _, kind, _ in host.events)


@pytest.mark.parametrize("action_kind", ["tool", "image"])
def test_stop_during_model_completion_prevents_following_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action_kind: str
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    host = _HarnessHost(tmp_path, tool)
    image_calls: list[str] = []
    running = True
    source = _image_loop_source() if action_kind == "image" else _tool_loop_source(tool)
    action = (
        {"action": "final", "outputs": {"result": {"brief": "a blue square"}}}
        if action_kind == "image"
        else {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"path": "notes.txt"},
        }
    )
    model = _ScriptedLoopModel(action)
    complete = model.complete

    def stop_then_complete(messages):
        nonlocal running
        running = False
        return complete(messages)

    def render(*args, **kwargs):
        del args, kwargs
        image_calls.append("generated")
        return {"render": {"kind": "artifact", "artifact_id": "fixture-image"}}

    monkeypatch.setattr(model, "complete", stop_then_complete)
    monkeypatch.setattr(host, "_is_running", lambda run_id: running)
    monkeypatch.setattr(host, "_run_image_model", render, raising=False)
    with pytest.raises(_RunAbandoned):
        host._execute_loop("project", "run", source, {}, model)

    assert len(model.calls) == 1
    assert not host.effects
    assert not image_calls
    assert not any(kind == "tool.started" for _, kind, _ in host.events)


def test_rejecting_tool_approvals_cannot_reset_the_model_turn_budget(
    tmp_path: Path,
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.write", "1.0.0")
    payload = _tool_loop_source(tool).to_dict()
    payload["extensions"]["veyra"]["max_turns"] = 2
    source = AgentSource.from_dict(payload)
    host = _HarnessHost(tmp_path, tool)
    request = {
        "action": "tool",
        "tool": tool["reference"],
        "arguments": {"path": "report.txt", "content": "synthetic report"},
    }
    model = _ScriptedLoopModel(request, request, request)
    first = host._execute_loop("project", "run", source, {}, model)
    assert first.pause is not None
    second = host._execute_loop(
        "project", "run", source, first.pause.values, model, approved=False
    )
    assert second.pause is not None
    assert (
        second.pause.values[LOOP_STATE_KEY]["turn"]
        > first.pause.values[LOOP_STATE_KEY]["turn"]
    )
    assert "rejected the tool request" in model.calls[1][-1]["content"]
    stopped = host._execute_loop(
        "project", "run", source, second.pause.values, model, approved=False
    )
    assert stopped.pause is not None and stopped.pause.details["kind"] == "budget"
    assert len(model.calls) == 2
    assert not host.effects
    assert not any(kind == "tool.started" for _, kind, _ in host.events)


@pytest.mark.parametrize(
    "constraints",
    [{"path": {"type": "not-a-json-schema-type"}}, {"path": {"maxLength": "many"}}],
)
def test_invalid_native_tool_constraints_fail_with_a_runtime_contract_error(
    tmp_path: Path, constraints: dict[str, Any]
) -> None:
    tool = ResourceCatalog().detail("veyra.tool.filesystem.read", "1.0.0")
    tool["spec"]["input_constraints"] = constraints
    host = _HarnessHost(tmp_path, tool)
    model = _ScriptedLoopModel(
        {
            "action": "tool",
            "tool": tool["reference"],
            "arguments": {"path": "notes.txt"},
        },
        {"action": "final", "outputs": {"translation": "must not continue"}},
    )
    with pytest.raises(LoopRuntimeError) as caught:
        host._execute_loop("project", "run", _tool_loop_source(tool), {}, model)
    assert caught.value.code == "tool_schema_invalid"
    assert len(model.calls) <= 1
    assert not host.effects
    assert not any(kind == "tool.started" for _, kind, _ in host.events)
