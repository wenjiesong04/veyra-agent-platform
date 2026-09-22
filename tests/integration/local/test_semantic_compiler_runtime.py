from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.integration.local.test_runtime_routes import (
    ScriptedRuntimeTransport,
    _await_run,
)
from tests.unit.local.test_semantic_plan_compiler import (
    _empty_context,
    _plan,
    _step,
)
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.builder.semantic_compiler import compile_semantic_plan
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.factory.compiler import compile_blueprint
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.secrets import MacOSKeychainSecretStore


@pytest.fixture(autouse=True)
def isolate_runtime_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MacOSKeychainSecretStore, "get", lambda self, ref: None)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("VEYRA_RUNTIME_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("VEYRA_RUNTIME_MODEL_ID", raising=False)


def test_compiled_multi_model_graph_executes_each_model_node(tmp_path: Path) -> None:
    compiled = compile_semantic_plan(
        _plan(
            goal="Summarize, analyze risk, then advise.",
            suggested_name="研究助手",
            description="总结、风险、建议。",
            inputs=[{"name": "request", "type": "string"}],
            outputs=[{"name": "result", "type": "string"}],
            steps=["总结", "风险", "建议"],
            step_intents=[
                _step("summary", "总结资料", "先总结用户资料", "model"),
                _step(
                    "risk",
                    "风险分析",
                    "分析其中风险",
                    "model",
                    depends_on=["summary"],
                ),
                _step(
                    "advice",
                    "生成建议",
                    "生成行动建议",
                    "model",
                    depends_on=["risk"],
                ),
            ],
        ),
        _empty_context(),
    )
    assert compiled.status == "compiled"
    assert compiled.blueprint is not None
    source, _, _ = compile_blueprint(compiled.blueprint, ResourceCatalog())
    transport = ScriptedRuntimeTransport("ok")
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(create_app(settings, runtime_transport=transport)) as client:
        project = client.post(
            "/api/v1/projects", json={"agents": [source.to_dict()]}
        ).json()
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        started = client.post(
            url,
            json={"inputs": {"request": "user notes"}},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        result = _await_run(client, url, started.json()["run_id"])
        assert result["status"] in {"unverified", "verified"}, result
        assert len(transport.calls) == 3
        prompts = json_prompts(transport.calls)
        assert any("先总结用户资料" in item for item in prompts)
        assert any("分析其中风险" in item for item in prompts)
        assert any("生成行动建议" in item for item in prompts)


def json_prompts(calls: list[object]) -> list[str]:
    texts: list[str] = []
    for messages in calls:
        if not isinstance(messages, list):
            continue
        for message in messages:
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                texts.append(message["content"])
    return texts
