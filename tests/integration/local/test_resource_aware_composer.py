from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.resource_plan import PlannedResource, ResourcePlan
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.builder.agent_loop_compiler import compile_loop_agent
from veyra_agent_platform.local.builder.specification import infer_agent_specification
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.factory.service import (
    FactoryError,
    _assert_snapshot_locks,
)
from veyra_agent_platform.local.resources import ResourceCatalog

from .test_factory_routes import ScriptedKimiTransport, _completion


@pytest.fixture(autouse=True)
def isolate_resolver_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)


def _client(tmp_path: Path, transport: ScriptedKimiTransport) -> TestClient:
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
    created = client.post("/api/v1/projects", json={"name": "Resolver"})
    assert created.status_code == 201
    return created.json()["project_id"]


def _generate(client: TestClient, project_id: str, goal: str) -> dict:
    created = client.post(
        f"/api/v1/projects/{project_id}/factory/sessions",
        json={"goal": goal},
    )
    assert created.status_code in {200, 201}, created.text
    session_id = created.json()["session_id"]
    generated = client.post(
        f"/api/v1/projects/{project_id}/factory/sessions/{session_id}/generate"
    )
    assert generated.status_code == 200, generated.text
    return generated.json()


def test_translation_proposal_does_not_bind_tools(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([_completion("What should success look like?")])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        session = _generate(
            client,
            project_id,
            "创建一个中英文翻译助手。用户输入一段文本，Agent 翻译成目标语言。",
        )
        bound = [item for item in session["resource_plan"] if item.get("bind_status")]
        assert not any(item.get("kind") == "tool" for item in bound)
        assert not any(item.get("bind_status") == "will_bind" for item in bound)


def test_github_proposal_needs_configuration(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([_completion("What should success look like?")])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        session = _generate(
            client,
            project_id,
            "创建一个助手，读取 GitHub repository 中的文件内容。",
        )
        github = [
            item
            for item in session["resource_plan"]
            if "github.read" in item.get("reference", "")
        ]
        assert github
        assert github[0]["bind_status"] in {
            "needs_configuration",
            "requires_configuration",
        }
        assert not any(
            "web.search" in item.get("reference", "")
            and item.get("bind_status") == "will_bind"
            for item in session["resource_plan"]
        )


def test_image_generation_proposal_is_missing(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([_completion("What should success look like?")])
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        session = _generate(
            client,
            project_id,
            "创建一个可以直接生成最终包装设计图片的 Agent。",
        )
        assert not any(
            item.get("capability") == "image_generation"
            for item in session["resource_plan"]
        )
        image_slot = next(
            item
            for item in session["proposal_preview"]["models"]
            if "image_generation" in item["required"]
        )
        assert image_slot["status"] == "needs_setup"
        assert image_slot["issue"]["missing"] == ["image_generation"]
        assert session["run_availability"] == "requires_configuration"


def test_apply_pins_exact_resource_plan_snapshot(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport([_completion("What should success look like?")])
    catalog = ResourceCatalog()
    search = catalog.detail("veyra.tool.web.search", "1.0.0")
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        session = _generate(
            client,
            project_id,
            "创建一个研究助手。它可以搜索公开网页，整理证据并输出结构化研究报告。",
        )
        search_plan = next(
            item
            for item in session["resource_plan"]
            if "web.search" in item["reference"]
        )
        assert search_plan["bind_status"] == "will_bind"
        applied = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{session['session_id']}/apply-draft",
            json={"confirm": True},
        )
        assert applied.status_code == 200, applied.text
        listed = client.get(f"/api/v1/projects/{project_id}/resources").json()
        pin = next(
            item
            for item in listed["resources"]
            if item["reference"] == search_plan["reference"]
        )
        assert pin["bound_content_hash"] == search["content_hash"]
        agent_id = applied.json()["agent"]["agent_id"]
        draft = client.get(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/draft"
        ).json()["source"]
        assert draft["lock"][search_plan["reference"]] == pin["bound_content_hash"]
        skills = draft["extensions"]["veyra"]["skill_refs"]
        assert skills


def test_apply_is_idempotent_when_resources_already_bound(tmp_path: Path) -> None:
    transport = ScriptedKimiTransport(
        [
            _completion("What should success look like?"),
            _completion("What should success look like?"),
        ]
    )
    with _client(tmp_path, transport) as client:
        project_id = _project(client)
        first = _generate(
            client,
            project_id,
            "创建一个研究助手。它可以搜索公开网页，输出结构化研究报告。",
        )
        applied = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{first['session_id']}/apply-draft",
            json={"confirm": True},
        )
        assert applied.status_code == 200, applied.text
        second = _generate(
            client,
            project_id,
            "创建一个研究助手。它可以搜索公开网页，输出结构化研究报告。",
        )
        search_plan = next(
            item
            for item in second["resource_plan"]
            if "web.search" in item["reference"]
        )
        assert search_plan["bind_status"] == "already_bound"
        again = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/{second['session_id']}/apply-draft",
            json={"confirm": True},
        )
        assert again.status_code == 200, again.text


def test_apply_fails_closed_when_snapshot_lock_mismatches() -> None:
    spec = infer_agent_specification("创建一个助手，可以搜索公开网页。")
    source = compile_loop_agent(spec, ResourceCatalog(), requirement=spec.goal)
    reference = next(key for key in source.lock if "web.search" in key)
    plan = ResourcePlan(
        will_bind=(
            PlannedResource(
                resource_id="veyra.tool.web.search",
                version="1.0.0",
                content_hash="0" * 64,
                kind="tool",
                capabilities=("web_search",),
                reason="stale",
                bind_status="will_bind",
                reference=reference,
                name="Web Search",
            ),
        ),
    )
    with pytest.raises(FactoryError) as caught:
        _assert_snapshot_locks(source, plan)
    assert caught.value.code == "resource_identity_conflict"
