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


def test_conversation_without_provider_and_generate_requires_key(
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
        assert generate.status_code == 503
        assert generate.json()["code"] == "factory_provider_not_configured"


def test_generate_repairs_then_applies_draft_without_running(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport(
        [
            _completion("What should success look like?"),
            _completion("{"),
            _completion(json.dumps(VALID_SEMANTIC_PLAN)),
        ]
    )
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "Prepare a research brief"},
        )
        session_id = created.json()["session_id"]
        generated = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/generate"
        )
        assert generated.status_code == 200
        session = generated.json()
        assert session["state"] == "review"
        assert session["candidate"]["name"] == "礼物包装 Agent"
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
        prompt = source["nodes"][1]["system_prompt"]
        assert "包装" in prompt
        assert "理解礼物与对象" in prompt
        assert source["extensions"]["veyra"]["skill_refs"] == []
        bindings = source["ui"].get("bindings") or {}
        assert not any(item.get("kind") == "skill" for item in bindings.values())
        runs = client.get(f"/api/v1/projects/{project_id}/agents/{agent_id}/runs")
        assert runs.status_code == 200
        assert runs.json()["runs"] == []


def test_apply_draft_can_create_a_child_of_an_existing_agent(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport(
        [
            _completion("What should success look like?"),
            _completion(json.dumps(VALID_SEMANTIC_PLAN)),
        ]
    )
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
            json={"goal": "Revise the parent Agent into a research brief"},
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


def test_apply_draft_uses_semantic_plan_name_and_deconflicts(tmp_path: Path) -> None:
    def _script() -> ScriptedKimiTransport:
        return ScriptedKimiTransport(
            [
                _completion("What should success look like?"),
                _completion(json.dumps(VALID_SEMANTIC_PLAN)),
            ]
        )

    with _client(tmp_path, _script()) as client:
        project_id = _project(client)
        first_session = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "Wrap gifts"},
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
        assert first.json()["agent"]["name"] == "礼物包装 Agent"
        client.app.state.factory.client.transport = _script()
        second_session = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "Wrap gifts again"},
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
        assert second.json()["agent"]["name"] == "礼物包装 Agent(1)"
        assert second.json()["agent"]["agent_id"] != first.json()["agent"]["agent_id"]


def test_unknown_github_tool_is_quarantined_not_registered(tmp_path: Path) -> None:
    plan = json.loads(json.dumps(VALID_SEMANTIC_PLAN))
    plan["capability_intents"] = ["read GitHub issues"]
    transport = ScriptedKimiTransport(
        [_completion("Need more detail?"), _completion(json.dumps(plan))]
    )
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
        assert session["state"] == "missing_capability"
        assert "github" in session["missing_capabilities"][0]["reference"].casefold()
        assert session["missing_capabilities"][0]["proposal"]["executable"] is False
        assert session["missing_capabilities"][0]["proposal"]["action"] == (
            "quarantined_resource_draft"
        )
        applied = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{created.json()['session_id']}/apply-draft",
            json={"confirm": True},
        )
        assert applied.status_code == 422
        assert applied.json()["code"] == "factory_blueprint_missing"
        drafted = client.post(
            "/api/v1/resources/drafts",
            json={
                "confirm": True,
                "kind": "tool",
                "requested_reference": "veyra.tool.github.issues@1.0.0",
                "name": "GitHub Read proposal",
            },
        )
        assert drafted.status_code == 201
        resource = drafted.json()["resource"]
        assert resource["availability"] == "quarantined"
        assert resource["factory_selectable"] is False
        assert resource["origin"] == "workshop"
        assert drafted.json()["executable"] is False
        listed = client.get("/api/v1/resources", params={"availability": "quarantined"})
        assert listed.status_code == 200
        assert any(
            item["resource_id"] == resource["resource_id"]
            for item in listed.json()["resources"]
        )


def test_generate_uploaded_item_agent_does_not_require_filesystem(
    tmp_path: Path,
) -> None:
    plan = json.loads(json.dumps(VALID_SEMANTIC_PLAN))
    plan["capability_intents"] = [
        "read files",
        "read uploaded files",
        "接受用户上传的物品图片",
    ]
    transport = ScriptedKimiTransport(
        [_completion("Need more detail?"), _completion(json.dumps(plan))]
    )
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
        assert session["blueprint"] is not None


def test_exhausted_repairs_stay_retryable(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport(
        [
            _completion("What should success look like?"),
            _completion("{"),
            _completion("{"),
            _completion("{"),
            _completion(json.dumps(VALID_SEMANTIC_PLAN)),
        ]
    )
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "Prepare a research brief"},
        )
        session_id = created.json()["session_id"]
        failed = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/generate"
        )
        assert failed.status_code == 422
        assert failed.json()["code"] == "factory_generation_invalid"
        session = client.get(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}"
        )
        assert session.status_code == 200
        payload = session.json()
        assert payload["state"] == "ready"
        assert payload["ready"] is True
        assert payload["diagnostics"]
        retried = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/generate"
        )
        assert retried.status_code == 200
        assert retried.json()["state"] == "review"


def test_generate_sends_moonshot_compatible_schema_without_creating_draft(
    tmp_path: Path,
) -> None:
    transport = ScriptedKimiTransport(
        [
            _completion("What should success look like?"),
            _completion(json.dumps(VALID_SEMANTIC_PLAN)),
        ]
    )
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
        assert session["resource_plan"]
        after_generate = client.get(f"/api/v1/projects/{project_id}").json()["agents"]
        assert after_generate == before
        _messages, response_format = transport.calls[1]
        assert response_format["type"] == "json_schema"
        schema = response_format["json_schema"]["schema"]
        assert response_format["json_schema"]["strict"] is True
        dumped = json.dumps(schema)
        assert "oneOf" not in dumped
        assert '"const"' not in dumped
        assert "$ref" not in dumped
        assert "nodes" not in schema["properties"]
        assert "required_capabilities" not in schema["properties"]
        assert schema["properties"]["goal"]["type"] == "string"
        assert schema["properties"]["suggested_name"]["type"] == "string"
        items = schema["properties"]["capability_intents"]["items"]
        assert items["type"] == "string"
        refused = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/apply-draft",
            json={"confirm": False},
        )
        assert refused.status_code == 422
        assert client.get(f"/api/v1/projects/{project_id}").json()["agents"] == before


def test_schema_invalid_blueprint_does_not_create_a_draft(tmp_path: Path) -> None:
    invalid = {"schema_version": "1.0", "goal": "wrap a gift"}
    transport = ScriptedKimiTransport(
        [
            _completion("What should success look like?"),
            _completion(json.dumps(invalid)),
            _completion(json.dumps(invalid)),
            _completion(json.dumps(invalid)),
        ]
    )
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "帮我生成礼物包装 agent"},
        )
        session_id = created.json()["session_id"]
        failed = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/generate"
        )
        assert failed.status_code == 422
        assert failed.json()["code"] == "factory_generation_invalid"
        session = client.get(
            f"/api/v1/projects/{project_id}/factory/sessions/{session_id}"
        )
        diagnostics = session.json()["diagnostics"]
        assert any("AgentSemanticPlan" in item for item in diagnostics)
        assert any("ContractValidationError" in item for item in diagnostics)
        assert any("missing field" in item for item in diagnostics)
        assert client.get(f"/api/v1/projects/{project_id}").json()["agents"] == []


def test_unknown_component_cannot_bypass_compile(tmp_path: Path) -> None:
    blueprint = json.loads(json.dumps(VALID_BLUEPRINT))
    blueprint["nodes"].insert(
        1, {"id": "magic", "component_type": "MagicWand", "uses": "veyra.tool.unknown"}
    )
    transport = ScriptedKimiTransport(
        [
            _completion("What should success look like?"),
            _completion(json.dumps(blueprint)),
            _completion(json.dumps(blueprint)),
            _completion(json.dumps(blueprint)),
        ]
    )
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "Use a magic wand"},
        )
        failed = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{created.json()['session_id']}/generate"
        )
        assert failed.status_code == 422
        assert failed.json()["code"] == "factory_generation_invalid"
        assert client.get(f"/api/v1/projects/{project_id}").json()["agents"] == []


def test_provider_400_returns_typed_diagnostic_without_secrets(
    tmp_path: Path,
) -> None:
    class RejectingTransport:
        def models(self) -> tuple[str, ...]:
            return ("kimi-k3",)

        def complete(
            self,
            messages: object,
            *,
            response_format: object = None,
        ) -> KimiCompletion:
            if response_format is None:
                return _completion("What should success look like?")
            raise FactoryProviderError(
                "factory_request_invalid",
                "Factory model request was rejected "
                "[invalid_request_error at $defs.required_capabilities]",
                details={
                    "http_status": "400",
                    "provider_error_type": "invalid_request_error",
                    "rejected_field": "$defs.required_capabilities",
                    "bounded_message": "type is not defined",
                },
            )

    with _client(tmp_path, RejectingTransport()) as client:
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "帮我生成礼物包装 agent"},
        )
        failed = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{created.json()['session_id']}/generate"
        )
        assert failed.status_code == 502
        payload = failed.json()
        assert payload["code"] == "factory_request_invalid"
        assert payload["details"]["http_status"] == "400"
        assert payload["details"]["provider_error_type"] == "invalid_request_error"
        assert "sk-" not in payload["message"]
        assert "Authorization" not in json.dumps(payload)


def test_schema_compatibility_400_retries_once_as_json_object(tmp_path: Path) -> None:
    class CompatibilityTransport:
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
            if response_format is None:
                return _completion("What should success look like?")
            if isinstance(response_format, dict) and response_format.get("type") == (
                "json_schema"
            ):
                raise FactoryProviderError(
                    "factory_request_invalid",
                    "Factory model request was rejected",
                    details={
                        "http_status": "400",
                        "provider_error_type": "invalid_request_error",
                        "rejected_field": "response_format.json_schema",
                        "bounded_message": (
                            "response_format.json_schema is not a valid "
                            "moonshot flavored json schema"
                        ),
                    },
                )
            return _completion(json.dumps(VALID_SEMANTIC_PLAN))

    transport = CompatibilityTransport()
    with _client(tmp_path, transport) as client:
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
        assert transport.formats[-2]["type"] == "json_schema"  # type: ignore[index]
        assert transport.formats[-1] == {"type": "json_object"}
        assert client.get(f"/api/v1/projects/{project_id}").json()["agents"] == []


def test_openai_compatible_host_uses_json_object_without_schema_fallback(
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
            return _completion(json.dumps(VALID_SEMANTIC_PLAN))

    transport = RecordingTransport()
    with _client(
        tmp_path,
        transport,
        factory_settings=FactorySettings(model_base_url="https://llm.example.test/v1"),
    ) as client:
        status = client.get("/api/v1/factory/status").json()
        assert status["capability_profile"]["provider_family"] == "openai_compatible"
        assert status["capability_profile"]["structured_output"] == "json_object"
        assert status["capability_profile"]["json_object_fallback"] is False
        assert status["capability_profile"]["source"] == "static_known"
        assert status["capability_profile"]["probed"] is False
        assert status["capability_profile"]["status"] == "unknown"
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
        assert transport.formats[-1] == {"type": "json_object"}
        assert not any(
            isinstance(item, dict) and item.get("type") == "json_schema"
            for item in transport.formats
        )


def test_openai_compatible_schema_400_does_not_retry(tmp_path: Path) -> None:
    class RejectingTransport:
        def __init__(self) -> None:
            self.generate_calls = 0

        def models(self) -> tuple[str, ...]:
            return ("kimi-k3",)

        def complete(
            self,
            messages: object,
            *,
            response_format: object = None,
        ) -> KimiCompletion:
            del messages
            if response_format is None:
                return _completion("What inputs should it receive?")
            self.generate_calls += 1
            raise FactoryProviderError(
                "factory_request_invalid",
                "Factory model request was rejected",
                details={
                    "http_status": "400",
                    "provider_error_type": "invalid_request_error",
                    "rejected_field": "response_format.json_schema",
                    "bounded_message": "response_format.json_schema is not a valid "
                    "moonshot flavored json schema",
                },
            )

    transport = RejectingTransport()
    with _client(
        tmp_path,
        transport,
        factory_settings=FactorySettings(model_base_url="https://llm.example.test/v1"),
    ) as client:
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "帮我生成礼物包装 agent"},
        )
        failed = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{created.json()['session_id']}/generate"
        )
        assert failed.status_code == 502
        assert failed.json()["code"] == "factory_request_invalid"
        assert transport.generate_calls == 1


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
            if response_format is None:
                return _completion("What should success look like?")
            return _completion(json.dumps(VALID_SEMANTIC_PLAN))

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
        assert any(
            isinstance(item, dict) and item.get("type") == "json_schema"
            for item in transport.formats
        )
        assert all(PROBE_USER_CONTENT not in prompt for prompt in transport.prompts)


def test_generate_uses_json_object_only_when_profile_allows(
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
            if response_format is None:
                return _completion("What should success look like?")
            return _completion(json.dumps(VALID_SEMANTIC_PLAN))

    transport = RecordingTransport()
    with _client(tmp_path, transport) as client:
        factory = _factory(client)
        seed = derive_provider_capability_profile(factory.client.settings)
        factory.profiles.put(
            replace(
                seed,
                structured_output="json_object",
                strict_json_schema=False,
                json_object_fallback=False,
                strict_json_schema_support="unsupported",
                json_object_support="supported",
                source="fallback",
                status="known",
                probed=True,
                checked_at="2026-09-19T12:00:00Z",
            )
        )
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
        assert transport.formats[-1] == {"type": "json_object"}
        assert not any(
            isinstance(item, dict) and item.get("type") == "json_schema"
            for item in transport.formats
        )


def test_rate_limit_does_not_fallback_or_mark_unsupported(tmp_path: Path) -> None:
    class RateLimitedTransport:
        def __init__(self) -> None:
            self.generate_calls = 0

        def models(self) -> tuple[str, ...]:
            return ("kimi-k3",)

        def complete(
            self,
            messages: object,
            *,
            response_format: object = None,
        ) -> KimiCompletion:
            del messages
            if response_format is None:
                return _completion("What inputs should it receive?")
            self.generate_calls += 1
            raise FactoryProviderError(
                "factory_rate_limited",
                "Factory model service is rate limited",
                details={"http_status": "429"},
            )

    transport = RateLimitedTransport()
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        created = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions",
            json={"goal": "帮我生成礼物包装 agent"},
        )
        failed = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{created.json()['session_id']}/generate"
        )
        assert failed.status_code == 502
        assert failed.json()["code"] == "factory_rate_limited"
        assert transport.generate_calls == 1
        profile = client.get("/api/v1/factory/status").json()["capability_profile"]
        assert profile["strict_json_schema"] is True
        assert profile["strict_json_schema_support"] == "unknown"
        assert profile["summary"]["status"] != "Not supported"


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
