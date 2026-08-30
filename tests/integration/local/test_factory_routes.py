from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.factory.client import (
    FactoryProviderError,
    KimiCompletion,
)

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
    tmp_path: Path, transport: ScriptedKimiTransport | None = None
) -> TestClient:
    return TestClient(
        create_app(
            LocalSettings(
                database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
                project_storage_root=tmp_path / "projects",
            ),
            factory_transport=transport,
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
            _completion(json.dumps(VALID_BLUEPRINT)),
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
        assert "Research Brief" in source["nodes"][1]["system_prompt"]
        assert source["extensions"]["veyra"]["skill_refs"] == [
            "veyra.skill.research-brief@1.0.0"
        ]
        bindings = source["ui"].get("bindings") or {}
        assert any(
            item["kind"] == "skill"
            and item["reference"] == "veyra.skill.research-brief@1.0.0"
            for item in bindings.values()
        )
        runs = client.get(f"/api/v1/projects/{project_id}/agents/{agent_id}/runs")
        assert runs.status_code == 200
        assert runs.json()["runs"] == []


def test_unknown_github_tool_is_quarantined_not_registered(tmp_path: Path) -> None:
    blueprint = json.loads(json.dumps(VALID_BLUEPRINT))
    blueprint["nodes"].insert(
        1,
        {
            "id": "read_github",
            "component_type": "Tool",
            "uses": "veyra.tool.github.read@1.0.0",
        },
    )
    blueprint["transitions"] = [
        {"from": "start", "port": "next", "to": "read_github"},
        {"from": "read_github", "port": "next", "to": "analyze"},
        {"from": "analyze", "port": "next", "to": "output"},
    ]
    blueprint["required_capabilities"]["component_types"] = [
        "Start",
        "Tool",
        "Agent",
        "Output",
    ]
    blueprint["required_capabilities"]["tool_refs"] = ["veyra.tool.github.read@1.0.0"]
    transport = ScriptedKimiTransport(
        [_completion("Need more detail?"), _completion(json.dumps(blueprint))]
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
        assert session["missing_capabilities"][0]["reference"] == (
            "veyra.tool.github.read@1.0.0"
        )
        assert session["missing_capabilities"][0]["proposal"]["executable"] is False
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
                "requested_reference": "veyra.tool.github.read@1.0.0",
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


def test_exhausted_repairs_stay_retryable(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport(
        [
            _completion("What should success look like?"),
            _completion("{"),
            _completion("{"),
            _completion("{"),
            _completion(json.dumps(VALID_BLUEPRINT)),
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
