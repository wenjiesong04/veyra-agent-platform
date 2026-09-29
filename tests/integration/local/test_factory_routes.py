from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.factory.capability_probe import PROBE_USER_CONTENT
from veyra_agent_platform.local.factory.capability_profile import (
    derive_provider_capability_profile,
)
from veyra_agent_platform.local.factory.client import (
    FactoryProviderError,
    KimiCompletion,
    KimiTransport,
)
from veyra_agent_platform.local.factory.config import FactorySettings
from veyra_agent_platform.local.factory.service import FactoryService

VALID_BLUEPRINT = {
    "schema_version": "1.0",
    "goal": "Prepare a research brief from a question.",
    "inputs": {"question": "string"},
    "outputs": {"brief": "string"},
    "nodes": [
        {"id": "start", "component_type": "Start"},
        {
            "id": "analyze",
            "component_type": "Agent",
            "model_ref": "model.primary",
            "system_prompt": "Write a bounded research brief.",
        },
        {"id": "output", "component_type": "Output", "output_name": "brief"},
    ],
    "transitions": [
        {"from": "start", "port": "next", "to": "analyze"},
        {"from": "analyze", "port": "next", "to": "output"},
    ],
    "required_capabilities": {
        "component_types": ["Start", "Agent", "Output"],
        "tool_refs": [],
        "skill_refs": ["veyra.skill.research-brief@1.0.0"],
        "policy_refs": ["veyra.policy.local-only@1.0.0"],
    },
    "requested_permissions": {"network_hosts": [], "tools": []},
    "verification": {"required": False, "checks": []},
    "ui_suggestions": {
        "positions": {
            "start": {"x": 0, "y": 0},
            "analyze": {"x": 160, "y": 0},
            "output": {"x": 320, "y": 0},
        }
    },
}

VALID_SEMANTIC_PLAN = {
    "schema_version": "1.0",
    "goal": "根据礼物类型、收礼对象、预算和风格，输出包装方案、材料和步骤。",
    "suggested_name": "礼物包装 Agent",
    "description": "规划礼物包装方案。",
    "inputs": [
        {"name": "gift-type", "type": "string"},
        {"name": "recipient", "type": "string"},
        {"name": "budget", "type": "string"},
        {"name": "style", "type": "string"},
    ],
    "outputs": [{"name": "plan", "type": "string"}],
    "steps": ["理解礼物与对象", "给出材料与步骤"],
    "capability_intents": [],
    "knowledge_intents": [],
    "approval_points": [],
    "success_criteria": ["给出可执行的包装步骤"],
    "user_constraints": [],
}


@pytest.fixture(autouse=True)
def isolate_factory_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("VEYRA_FACTORY_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("VEYRA_FACTORY_MODEL_ID", raising=False)


class ScriptedKimiTransport:
    def __init__(self, completions: list[KimiCompletion]) -> None:
        self.completions = list(completions)
        self.calls: list[object] = []

    def models(self) -> tuple[str, ...]:
        return ("kimi-k3",)

    def complete(
        self, messages: object, *, response_format: object = None
    ) -> KimiCompletion:
        self.calls.append((messages, response_format))
        if not self.completions:
            raise FactoryProviderError(
                "factory_invalid_response", "no scripted completion remains"
            )
        return self.completions.pop(0)


def _completion(content: str) -> KimiCompletion:
    return KimiCompletion(
        content=content,
        assistant_message={"role": "assistant", "content": content},
        finish_reason="stop",
    )


def _client(
    tmp_path: Path,
    transport: KimiTransport | None = None,
    *,
    factory_settings: FactorySettings | None = None,
) -> TestClient:
    return TestClient(
        create_app(
            LocalSettings(
                database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
                project_storage_root=tmp_path / "projects",
            ),
            factory_transport=transport,
            factory_settings=factory_settings,
        )
    )


def _project(client: TestClient) -> str:
    created = client.post("/api/v1/projects", json={"name": "Factory"})
    assert created.status_code == 201
    return created.json()["project_id"]


def test_factory_status_never_claims_to_execute_drafts(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        status = client.get("/api/v1/factory/status")
        assert status.status_code == 200
        payload = status.json()
        assert payload["executes_drafts"] is False
        assert payload["model_id"] == "kimi-k3"
        assert payload["model_base_url"] == "https://api.moonshot.cn/v1"
        assert payload["configured"] is False
        assert (
            payload["capability_profile"]
            == derive_provider_capability_profile(FactorySettings()).to_dict()
        )


def test_conversation_without_provider_still_generates_deterministic_plan(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "Summarize a local document"},
        )
        assert created.status_code == 201
        session = created.json()
        assert session["ready"] is True
        assert session["executes_drafts"] is False
        assert session["messages"][0]["role"] == "user"
        assert session["messages"][1]["role"] == "assistant"
        generate = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session['session_id']}/generate"
        )
        assert generate.status_code == 200, generate.text
        payload = generate.json()
        assert payload["state"] == "review"
        assert payload["executes_drafts"] is False
        status = client.get("/api/v1/factory/status")
        assert status.status_code == 200
        assert status.json()["configured"] is False


def test_generate_loop_agent_then_applies_draft_without_running(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([_completion("What should success look like?")])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "创建一个翻译助手，把中文翻译成自然英语。"},
        )
        session_id = created.json()["session_id"]
        generated = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/generate"
        )
        assert generated.status_code == 200
        session = generated.json()
        assert session["state"] == "review"
        assert session["candidate"]["name"] == "Translation Agent"
        assert session.get("execution_kind") == "loop"
        assert session.get("target_kind") == "agent"
        types = [node["component_type"] for node in session["blueprint"]["nodes"]]
        assert types == ["Start", "Model", "Output"]
        assert "HumanApproval" not in types
        assert "Condition" not in types
        assert session["run_availability"] == "requires_configuration"
        refused = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/apply-draft",
            json={"confirm": False},
        )
        assert refused.status_code == 422
        applied = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/apply-draft",
            json={"confirm": True, "name": "Research Brief Agent"},
        )
        assert applied.status_code == 200
        payload = applied.json()
        assert payload["session"]["state"] == "completed"
        agent_id = payload["agent"]["agent_id"]
        draft = client.get(f"/api/v1/projects/{project_id}/agents/{agent_id}/draft")
        assert draft.status_code == 200
        source = draft.json()["source"]
        assert source["extensions"]["veyra"]["execution_kind"] == "loop"
        assert source["outputs"]["translation"]
        runs = client.get(f"/api/v1/projects/{project_id}/agents/{agent_id}/runs")
        assert runs.status_code == 200
        assert runs.json()["runs"] == []


def test_research_loop_apply_pins_web_search(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([_completion("What should success look like?")])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        listed = client.get(f"/api/v1/projects/{project_id}/resources").json()
        before = {
            item["reference"]
            for item in listed["resources"]
            if item.get("scope") == "project"
        }
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "创建一个研究助手，可以搜索网页并整理成报告。"},
        )
        session_id = created.json()["session_id"]
        generated = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/generate"
        )
        assert generated.status_code == 200
        session = generated.json()
        search_plan = next(
            item
            for item in session["resource_plan"]
            if "web.search" in item["reference"]
        )
        assert search_plan["bind_status"] == "will_bind"
        applied = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/apply-draft",
            json={"confirm": True},
        )
        assert applied.status_code == 200, applied.text
        listed = client.get(f"/api/v1/projects/{project_id}/resources").json()
        pinned = {
            item["reference"]
            for item in listed["resources"]
            if item.get("scope") == "project"
        }
        assert search_plan["reference"] in pinned
        assert search_plan["reference"] not in before
        agent_id = applied.json()["agent"]["agent_id"]
        draft = client.get(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/draft"
        ).json()["source"]
        pin = next(
            item
            for item in listed["resources"]
            if item["reference"] == search_plan["reference"]
        )
        assert draft["lock"][search_plan["reference"]] == pin["bound_content_hash"]


def test_apply_draft_can_create_a_child_of_an_existing_agent(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([_completion("What should success look like?")])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        parent = client.post(
            f"/api/v1/projects/{project_id}/agents",
            json={"mode": "blank", "name": "Parent Reviewer"},
        )
        assert parent.status_code == 201
        parent_id = parent.json()["agent_id"]
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "创建一个翻译助手，把中文翻译成自然英语。"},
        )
        session_id = created.json()["session_id"]
        generated = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/generate"
        )
        assert generated.status_code == 200
        applied = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/apply-draft",
            json={
                "confirm": True,
                "name": "Revised Brief Agent",
                "parent_agent_id": parent_id,
            },
        )
        assert applied.status_code == 200
        child = applied.json()["agent"]
        assert child["parent_agent_id"] == parent_id
        assert child["agent_id"] != parent_id
        listed = client.get(f"/api/v1/projects/{project_id}")
        assert listed.status_code == 200
        child_record = next(
            item
            for item in listed.json()["agents"]
            if item["agent_id"] == child["agent_id"]
        )
        assert child_record["parent_agent_id"] == parent_id


def test_apply_draft_uses_loop_agent_name_and_deconflicts(tmp_path: Path) -> None:
    def _script() -> ScriptedKimiTransport:
        return ScriptedKimiTransport([_completion("What should success look like?")])

    with _client(tmp_path, _script()) as client:
        project_id = _project(client)
        first_session = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "创建一个礼品包装设计助手。"},
        ).json()["session_id"]
        assert (
            client.post(
                f"/api/v1/projects/{project_id}/factory/sessions/{first_session}/generate"
            ).status_code
            == 200
        )
        first = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{first_session}/apply-draft",
            json={"confirm": True},
        )
        assert first.status_code == 200, first.text
        assert first.json()["agent"]["name"] == "Packaging Designer Agent"
        client.app.state.factory.client.transport = _script()
        second_session = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "创建一个礼品包装设计助手，再做一个。"},
        ).json()["session_id"]
        assert (
            client.post(
                f"/api/v1/projects/{project_id}/factory/sessions/{second_session}/generate"
            ).status_code
            == 200
        )
        second = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{second_session}/apply-draft",
            json={"confirm": True},
        )
        assert second.status_code == 200, second.text
        assert second.json()["agent"]["name"] == "Packaging Designer Agent(1)"
        assert second.json()["agent"]["agent_id"] != first.json()["agent"]["agent_id"]


def test_github_tool_is_locked_needs_configuration_not_quarantined(
    tmp_path: Path,
) -> None:
    transport = ScriptedKimiTransport([_completion("Need more detail?")])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "Triage GitHub issues"},
        )
        generated = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{created.json()['session_id']}/generate"
        )
        assert generated.status_code == 200
        session = generated.json()
        assert session["state"] == "review"
        assert session["missing_capabilities"] == []
        bindings = (session["blueprint"].get("ui_suggestions") or {}).get(
            "bindings"
        ) or {}
        assert any("github.read" in str(item).casefold() for item in bindings.values())
        github = [
            item
            for item in session.get("resource_plan") or []
            if "github.read" in str(item.get("reference") or "")
        ]
        assert github
        assert github[0]["bind_status"] in {
            "needs_configuration",
            "requires_configuration",
        }
        applied = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{created.json()['session_id']}/apply-draft",
            json={"confirm": True},
        )
        assert applied.status_code == 200
        listed = client.get("/api/v1/resources", params={"availability": "quarantined"})
        assert listed.status_code == 200
        assert not any(
            "github" in str(item.get("reference") or "").casefold()
            for item in listed.json()["resources"]
        )


def test_generate_uploaded_item_agent_does_not_require_filesystem(
    tmp_path: Path,
) -> None:
    transport = ScriptedKimiTransport([_completion("Need more detail?")])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "帮我生成一个能根据用户上传的物品生成对应的礼物包装的agent"},
        )
        generated = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{created.json()['session_id']}/generate"
        )
        assert generated.status_code == 200
        session = generated.json()
        assert session["state"] == "review"
        assert session["missing_capabilities"] == []
        permissions = session["blueprint"]["requested_permissions"]
        assert permissions["filesystem_read_roots"] == []
        assert permissions["filesystem_write_roots"] == []


def test_generate_does_not_request_semantic_plan_json(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([_completion("What should success look like?")])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        before = client.get(f"/api/v1/projects/{project_id}").json()["agents"]
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "帮我生成礼物包装 agent"},
        )
        session_id = created.json()["session_id"]
        generated = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/generate"
        )
        assert generated.status_code == 200
        session = generated.json()
        assert session["state"] == "review"
        assert session["blueprint"]["goal"]
        after_generate = client.get(f"/api/v1/projects/{project_id}").json()["agents"]
        assert after_generate == before
        formats = [item[1] for item in transport.calls]
        assert not any(
            isinstance(item, dict) and item.get("type") == "json_schema"
            for item in formats
        )
        types = [node["component_type"] for node in session["blueprint"]["nodes"]]
        assert "HumanApproval" not in types
        refused = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/apply-draft",
            json={"confirm": False},
        )
        assert refused.status_code == 422
        assert client.get(f"/api/v1/projects/{project_id}").json()["agents"] == before


def test_generate_packaging_pipeline_is_a_workflow(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([_completion("What should success look like?")])
    goal = (
        "创建一个商品包装设计流程。"
        "先让商品分析 Agent 分析上传的商品图片，"
        "再让市场研究 Agent 调研竞品，"
        "然后让包装设计 Agent 提出设计，"
        "我确认后再生成最终包装效果图。"
    )
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": goal},
        )
        session_id = created.json()["session_id"]
        generated = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/generate"
        )
        assert generated.status_code == 200, generated.text
        session = generated.json()
        assert session["state"] == "review"
        assert session.get("target_kind") == "workflow"
        assert session.get("execution_kind") == "workflow"
        types = [node["component_type"] for node in session["blueprint"]["nodes"]]
        assert types[0] == "Start"
        assert types.count("AgentCall") >= 3
        assert "HumanApproval" in types
        assert types[-1] == "Output"
        applied = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/apply-draft",
            json={"confirm": True},
        )
        assert applied.status_code == 422
        assert applied.json()["code"] == "factory_generation_blocked"


def test_generate_does_not_silently_compile_a_dag_for_simple_intents(
    tmp_path: Path,
) -> None:
    transport = ScriptedKimiTransport([_completion("What should success look like?")])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "创建一个翻译助手，把中文翻译成自然英语。"},
        )
        generated = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{created.json()['session_id']}/generate"
        )
        assert generated.status_code == 200
        types = [
            node["component_type"] for node in generated.json()["blueprint"]["nodes"]
        ]
        assert types == ["Start", "Model", "Output"]
        assert client.get(f"/api/v1/projects/{project_id}").json()["agents"] == []


def test_generate_uses_cached_strict_profile_without_probing(tmp_path: Path) -> None:
    class RecordingTransport:
        def __init__(self) -> None:
            self.formats: list[object] = []
            self.prompts: list[str] = []

        def models(self) -> tuple[str, ...]:
            return ("kimi-k3",)

        def complete(
            self,
            messages: object,
            *,
            response_format: object = None,
        ) -> KimiCompletion:
            self.formats.append(response_format)
            self.prompts.append(json.dumps(messages))
            return _completion("What should success look like?")

    transport = RecordingTransport()
    with _client(tmp_path, transport) as client:
        factory = _factory(client)
        seed = derive_provider_capability_profile(factory.client.settings)
        factory.profiles.put(
            replace(
                seed,
                status="known",
                source="probe",
                probed=True,
                strict_json_schema_support="supported",
                checked_at="2026-09-19T12:00:00Z",
            )
        )
        status = client.get("/api/v1/factory/status").json()["capability_profile"]
        assert status["status"] == "known"
        assert status["summary"]["structured_output"] == "Strict JSON Schema"
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "帮我生成礼物包装 agent"},
        )
        generated = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{created.json()['session_id']}/generate"
        )
        assert generated.status_code == 200, generated.text
        assert not any(
            isinstance(item, dict) and item.get("type") == "json_schema"
            for item in transport.formats
        )
        assert all(PROBE_USER_CONTENT not in prompt for prompt in transport.prompts)


def test_openai_compatible_host_does_not_need_json_schema_for_generate(
    tmp_path: Path,
) -> None:
    class RecordingTransport:
        def __init__(self) -> None:
            self.formats: list[object] = []

        def models(self) -> tuple[str, ...]:
            return ("kimi-k3",)

        def complete(
            self,
            messages: object,
            *,
            response_format: object = None,
        ) -> KimiCompletion:
            del messages
            self.formats.append(response_format)
            return _completion("What should success look like?")

    transport = RecordingTransport()
    with _client(
        tmp_path,
        transport,
        factory_settings=FactorySettings(model_base_url="https://llm.example.test/v1"),
    ) as client:
        status = client.get("/api/v1/factory/status").json()
        assert status["capability_profile"]["provider_family"] == "openai_compatible"
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "帮我生成礼物包装 agent"},
        )
        generated = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{created.json()['session_id']}/generate"
        )
        assert generated.status_code == 200, generated.text
        assert generated.json()["state"] == "review"
        assert not any(
            isinstance(item, dict) and item.get("type") == "json_schema"
            for item in transport.formats
        )


def test_capability_probe_endpoint_uses_synthetic_prompt(tmp_path: Path) -> None:
    class ProbeTransport:
        def __init__(self) -> None:
            self.messages: list[object] = []
            self.models_called = False

        def models(self) -> tuple[str, ...]:
            self.models_called = True
            return ("kimi-k3",)

        def complete(
            self,
            messages: object,
            *,
            response_format: object = None,
        ) -> KimiCompletion:
            del response_format
            self.messages.append(messages)
            return _completion('{"ok": true}')

    transport = ProbeTransport()
    with _client(tmp_path, transport) as client:
        probed = client.post("/api/v1/factory/capability-probe")
        assert probed.status_code == 200, probed.text
        profile = probed.json()["capability_profile"]
        assert profile["status"] == "known"
        assert profile["strict_json_schema_support"] == "supported"
        assert profile["source"] == "probe"
        assert profile["summary"]["status"] == "Known"
        assert transport.models_called is False
        assert [list(item) for item in transport.messages] == [
            [{"role": "user", "content": PROBE_USER_CONTENT}]
        ]
        cached = client.get("/api/v1/factory/status").json()["capability_profile"]
        assert cached["probed"] is True
        assert cached["status"] == "known"
        assert cached["model"] == profile["model"]
        assert cached["base_url_fingerprint"] == profile["base_url_fingerprint"]


def _factory(client: TestClient) -> FactoryService:
    return client.app.state.factory
