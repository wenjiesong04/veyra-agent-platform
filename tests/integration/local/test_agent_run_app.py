from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.contracts.interaction import (
    INTERACTION_AUTO,
    INTERACTION_CHAT,
    INTERACTION_FORM,
    INTERACTION_HYBRID,
    derive_interaction_mode,
    resolve_interaction_mode,
)
from veyra_agent_platform.contracts.typed_io import parse_typed_fields
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.approvals import tool_approval_summary
from veyra_agent_platform.local.runtime.client import (
    RuntimeCompletion,
    RuntimeProviderError,
)
from veyra_agent_platform.local.secrets import MacOSKeychainSecretStore

from .test_loop_resource_truth import (
    _PNG,
    _attach,
    _create_project,
    _loop_source,
    _pin,
    _set_io,
)
from .test_runtime_routes import (
    ScriptedRuntimeTransport,
    _await_run,
    _command_until_settled,
)


@pytest.fixture(autouse=True)
def isolate_runtime_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MacOSKeychainSecretStore, "get", lambda self, ref: None)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("VEYRA_RUNTIME_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("VEYRA_RUNTIME_MODEL_ID", raising=False)


def _make_client(tmp_path: Path, transport: object, **kwargs: Any) -> TestClient:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    return TestClient(create_app(settings, runtime_transport=transport, **kwargs))


def _commit(client: TestClient, project_id: str, agent_id: str) -> dict[str, Any]:
    url = f"/api/v1/projects/{project_id}/agents/{agent_id}"
    draft = client.get(f"{url}/draft").json()
    committed = client.post(
        f"{url}/commit",
        json={"expected_revision": draft["revision"]},
        headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert committed.status_code == 200, committed.text
    payload = committed.json()
    versions = client.get(f"{url}/versions").json()["versions"]
    match = next(
        item for item in versions if item["version_id"] == payload["version_id"]
    )
    assert match["committed"] is True
    return payload


def _save(
    client: TestClient, project_id: str, agent_id: str, source: dict[str, Any]
) -> dict[str, Any]:
    url = f"/api/v1/projects/{project_id}/agents/{agent_id}/draft"
    draft = client.get(url).json()
    saved = client.patch(
        url,
        json={"source": source, "expected_revision": draft["revision"]},
        headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert saved.status_code == 200, saved.text
    return saved.json()


def _app_run(
    client: TestClient,
    url: str,
    inputs: dict[str, Any],
    *,
    conversation_id: str | None = None,
    version_id: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"inputs": inputs, "source": "committed"}
    if conversation_id:
        body["conversation_id"] = conversation_id
    if version_id:
        body["version_id"] = version_id
    started = client.post(
        url,
        json=body,
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert started.status_code == 200, started.text
    return _await_run(client, url, started.json()["run_id"])


def test_interaction_mode_derives_without_domain_keywords() -> None:
    assert derive_interaction_mode({"message": "string"}) == INTERACTION_CHAT
    assert (
        derive_interaction_mode({"topic": "string", "audience": "string"})
        == INTERACTION_FORM
    )
    assert (
        derive_interaction_mode({"item_image": "image", "brand": "string"})
        == INTERACTION_HYBRID
    )
    fields = parse_typed_fields({"request": "string"}, "inputs")
    assert resolve_interaction_mode(INTERACTION_AUTO, fields) == INTERACTION_CHAT


def test_approval_summary_is_server_built() -> None:
    summary = tool_approval_summary(
        "veyra.tool.filesystem.write@1.0.0",
        {"path": "docs/report.md", "content": "secret-looking"},
    )
    assert summary["action"] == "Write file"
    assert summary["target"] == "docs/report.md"
    dumped = json.dumps(summary)
    assert "secret-looking" not in dumped


def test_app_runs_committed_chat_version_not_draft(tmp_path: Path) -> None:
    source = _set_io(
        _loop_source("创建一个翻译助手，把中文翻译成自然英语。"),
        {"message": "string"},
        {"translation": "string"},
    )
    source["extensions"]["veyra"]["interaction_mode"] = "chat"
    source["extensions"]["veyra"]["instructions"] = "COMMITTED_V1"
    transport = ScriptedRuntimeTransport("hello")
    with _make_client(tmp_path, transport) as client:
        project = _create_project(client, source)
        project_id = project["project_id"]
        agent_id = project["agents"][0]["agent_id"]
        url = f"/api/v1/projects/{project_id}/agents/{agent_id}/run"
        missing = client.post(
            url,
            json={"inputs": {"message": "hi"}, "source": "committed"},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert missing.status_code == 422
        assert missing.json()["code"] == "agent_has_no_committed_version"
        v1 = _commit(client, project_id, agent_id)
        first = _app_run(client, url, {"message": "alpha"})
        assert first["status"] in {"unverified", "verified"}
        assert first["version_id"] == v1["version_id"]
        assert first["result"]["translation"] == "hello"
        blob = json.dumps(transport.calls)
        assert "COMMITTED_V1" in blob
        draft = client.get(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/draft"
        ).json()
        draft["source"]["extensions"]["veyra"]["instructions"] = "DRAFT_MARKER"
        _save(client, project_id, agent_id, draft["source"])
        transport.calls.clear()
        second = _app_run(
            client,
            url,
            {"message": "beta"},
            conversation_id=str(first["conversation_id"]),
        )
        assert second["version_id"] == v1["version_id"]
        assert "DRAFT_MARKER" not in json.dumps(transport.calls)
        assert "COMMITTED_V1" in json.dumps(transport.calls)
        assert "alpha" in json.dumps(transport.calls)
        draft_run = client.post(
            url,
            json={"inputs": {"message": "gamma"}, "source": "draft"},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert draft_run.status_code == 200
        settled = _await_run(client, url, draft_run.json()["run_id"])
        assert settled["status"] in {"unverified", "verified"}
        assert "DRAFT_MARKER" in json.dumps(transport.calls)


def test_new_conversation_uses_latest_committed_version(tmp_path: Path) -> None:
    source = _set_io(
        _loop_source("创建一个翻译助手，把中文翻译成自然英语。"),
        {"message": "string"},
        {"translation": "string"},
    )
    source["extensions"]["veyra"]["instructions"] = "VERSION_ONE"
    transport = ScriptedRuntimeTransport(["one", "two", "three"])
    with _make_client(tmp_path, transport) as client:
        project = _create_project(client, source)
        project_id = project["project_id"]
        agent_id = project["agents"][0]["agent_id"]
        url = f"/api/v1/projects/{project_id}/agents/{agent_id}/run"
        v1 = _commit(client, project_id, agent_id)
        first = _app_run(client, url, {"message": "keep me"})
        assert first["version_id"] == v1["version_id"]
        draft = client.get(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/draft"
        ).json()
        draft["source"]["extensions"]["veyra"]["instructions"] = "VERSION_TWO"
        _save(client, project_id, agent_id, draft["source"])
        v2 = _commit(client, project_id, agent_id)
        assert v2["version_id"] != v1["version_id"]
        pinned = _app_run(
            client,
            url,
            {"message": "still v1"},
            conversation_id=str(first["conversation_id"]),
        )
        assert pinned["version_id"] == v1["version_id"]
        mismatch = client.post(
            url,
            json={
                "inputs": {"message": "nope"},
                "source": "committed",
                "conversation_id": first["conversation_id"],
                "version_id": v2["version_id"],
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert mismatch.status_code == 422
        assert mismatch.json()["code"] == "conversation_version_mismatch"
        latest = _app_run(client, url, {"message": "new chat"})
        assert latest["version_id"] == v2["version_id"]
        assert latest["conversation_id"] != first["conversation_id"]


def test_app_rejects_unknown_version(tmp_path: Path) -> None:
    source = _loop_source("创建一个翻译助手，把中文翻译成自然英语。")
    transport = ScriptedRuntimeTransport("ok")
    with _make_client(tmp_path, transport) as client:
        project = _create_project(client, source)
        _commit(client, project["project_id"], project["agents"][0]["agent_id"])
        response = client.post(
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{project['agents'][0]['agent_id']}/run",
            json={
                "inputs": {next(iter(source["inputs"])): "x"},
                "source": "committed",
                "version_id": new_uuid7(),
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "agent_version_not_found"


def test_form_and_hybrid_committed_runs(tmp_path: Path) -> None:
    form = _set_io(
        _loop_source("创建一个翻译助手，把中文翻译成自然英语。"),
        {"topic": "string", "audience": "string", "length": "number"},
        {"result": "string"},
    )
    form["extensions"]["veyra"]["interaction_mode"] = "form"
    hybrid = _set_io(
        _loop_source("创建一个翻译助手，把中文翻译成自然英语。"),
        {"item-image": "image", "brand": "string", "message": "string"},
        {"analysis": "string"},
    )
    hybrid["extensions"]["veyra"]["interaction_mode"] = "hybrid"
    transport = ScriptedRuntimeTransport(["form-out", "hybrid-out", "follow-up"])
    with _make_client(tmp_path, transport) as client:
        form_project = _create_project(client, form)
        form_id = form_project["agents"][0]["agent_id"]
        _commit(client, form_project["project_id"], form_id)
        form_run = _app_run(
            client,
            f"/api/v1/projects/{form_project['project_id']}/agents/{form_id}/run",
            {"topic": "boxes", "audience": "retail", "length": 3},
        )
        assert form_run["result"]["result"] == "form-out"
        hybrid_project = _create_project(client, hybrid)
        hybrid_id = hybrid_project["agents"][0]["agent_id"]
        _commit(client, hybrid_project["project_id"], hybrid_id)
        uploaded = client.post(
            f"/api/v1/projects/{hybrid_project['project_id']}/artifacts",
            files={"file": ("item.png", _PNG, "image/png")},
        ).json()
        ref = {
            "kind": "artifact",
            "artifact_id": uploaded["artifact_id"],
            "media_type": "image/png",
            "filename": "item.png",
        }
        url = f"/api/v1/projects/{hybrid_project['project_id']}/agents/{hybrid_id}/run"
        first = _app_run(
            client,
            url,
            {"item-image": ref, "brand": "Acme", "message": "analyze"},
        )
        assert first["result"]["analysis"] == "hybrid-out"
        dumped = json.dumps(transport.calls)
        assert "data:image/png;base64," in dumped
        assert str(tmp_path) not in dumped
        follow = _app_run(
            client,
            url,
            {"message": "再重点分析材质"},
            conversation_id=str(first["conversation_id"]),
        )
        assert follow["result"]["analysis"] == "follow-up"
        assert follow["conversation_id"] == first["conversation_id"]


def test_document_input_reaches_model_context(tmp_path: Path) -> None:
    source = _set_io(
        _loop_source("创建一个翻译助手，把中文翻译成自然英语。"),
        {"brief": "document", "message": "string"},
        {"result": "string"},
    )
    source["extensions"]["veyra"]["interaction_mode"] = "hybrid"
    transport = ScriptedRuntimeTransport("noted")
    with _make_client(tmp_path, transport) as client:
        project = _create_project(client, source)
        agent_id = project["agents"][0]["agent_id"]
        _commit(client, project["project_id"], agent_id)
        uploaded = client.post(
            f"/api/v1/projects/{project['project_id']}/artifacts",
            files={"file": ("notes.md", b"VEYRA_DOC_APP_441", "text/markdown")},
        ).json()
        ref = {
            "kind": "artifact",
            "artifact_id": uploaded["artifact_id"],
            "media_type": "text/markdown",
            "filename": "notes.md",
        }
        result = _app_run(
            client,
            f"/api/v1/projects/{project['project_id']}/agents/{agent_id}/run",
            {"brief": ref, "message": "summarize"},
        )
        assert result["status"] in {"unverified", "verified"}
        blob = json.dumps(transport.calls)
        assert "VEYRA_DOC_APP_441" in blob
        assert "notes.md" in blob
        assert str(tmp_path) not in blob


def test_tool_approval_resume_and_reject(tmp_path: Path) -> None:
    catalog = ResourceCatalog()
    write = catalog.detail("veyra.tool.filesystem.write", "1.0.0")
    source = _attach(
        _set_io(
            _loop_source("创建一个可以写文件的助手。"),
            {"message": "string"},
            {"result": "string"},
        ),
        write,
    )
    script = [
        json.dumps(
            {
                "action": "tool",
                "tool": write["reference"],
                "arguments": {"path": "notes.txt", "content": "hi"},
            }
        ),
        json.dumps({"action": "final", "outputs": {"result": "wrote"}}),
    ]
    transport = ScriptedRuntimeTransport(script)
    with _make_client(tmp_path, transport) as client:
        project = _create_project(client, source)
        project_id = project["project_id"]
        agent_id = project["agents"][0]["agent_id"]
        _pin(client, project_id, write)
        _commit(client, project_id, agent_id)
        url = f"/api/v1/projects/{project_id}/agents/{agent_id}/run"
        waiting = _app_run(client, url, {"message": "write it"})
        assert waiting["status"] == "waiting"
        events = client.get(f"{url}s/{waiting['run_id']}").json()["events"]
        requested = next(
            event for event in events if event["kind"] == "approval.requested"
        )
        summary = requested["payload"]["approval_summary"]
        assert summary["action"] == "Write file"
        assert summary["target"] == "notes.txt"
        completed = _command_until_settled(
            client, url, str(waiting["run_id"]), "approve"
        )
        assert completed["status"] in {"unverified", "verified"}
        assert completed["run_id"] == waiting["run_id"]
        transport._index = 0
        reject_run = _app_run(client, url, {"message": "write again"})
        assert reject_run["status"] == "waiting"
        rejected = _command_until_settled(
            client, url, str(reject_run["run_id"]), "reject"
        )
        assert rejected["status"] in {"failed", "unverified", "verified", "cancelled"}
        assert rejected["run_id"] == reject_run["run_id"]


def test_app_cancel_and_retry(tmp_path: Path) -> None:
    source = _set_io(
        _loop_source("创建一个翻译助手，把中文翻译成自然英语。"),
        {"message": "string"},
        {"translation": "string"},
    )
    entered = threading.Event()
    release = threading.Event()

    class DelayedTransport:
        def __init__(self) -> None:
            self.calls: list[Any] = []
            self.n = 0

        def models(self) -> tuple[str, ...]:
            return ("kimi-k3",)

        def complete(self, messages: object) -> RuntimeCompletion:
            self.calls.append(messages)
            self.n += 1
            if self.n == 1:
                entered.set()
                assert release.wait(8)
                return RuntimeCompletion(content="late", finish_reason="stop")
            if self.n == 2:
                raise RuntimeProviderError("runtime_provider_error", "scripted failure")
            return RuntimeCompletion(content="retried", finish_reason="stop")

    transport = DelayedTransport()
    with _make_client(tmp_path, transport) as client:
        project = _create_project(client, source)
        agent_id = project["agents"][0]["agent_id"]
        version = _commit(client, project["project_id"], agent_id)
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent_id}/run"
        started = client.post(
            url,
            json={"inputs": {"message": "slow"}, "source": "committed"},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200
        run_id = started.json()["run_id"]
        assert entered.wait(5)
        stopped = _command_until_settled(client, url, run_id, "stop")
        release.set()
        assert stopped["status"] == "cancelled"
        assert stopped["run_id"] == run_id
        failed = _app_run(client, url, {"message": "boom"})
        assert failed["status"] == "failed"
        retried = _app_run(client, url, {"message": "boom"})
        assert retried["run_id"] != failed["run_id"]
        assert retried["version_id"] == version["version_id"]
        kept = client.get(f"{url}s/{failed['run_id']}").json()
        assert kept["status"] == "failed"


def test_runtime_preflight_fail_closed(tmp_path: Path) -> None:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    source = _loop_source("创建一个翻译助手，把中文翻译成自然英语。")
    with TestClient(create_app(settings)) as client:
        project = _create_project(client, source)
        agent_id = project["agents"][0]["agent_id"]
        _commit(client, project["project_id"], agent_id)
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent_id}/run"
        response = client.post(
            url,
            json={
                "inputs": {next(iter(source["inputs"])): "hi"},
                "source": "committed",
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "runtime_not_configured"
        runs = client.get(f"{url}s").json()["runs"]
        assert runs == []


def test_github_preflight_needs_configuration(tmp_path: Path) -> None:
    catalog = ResourceCatalog()
    github = catalog.detail("veyra.tool.github.read", "1.0.0")
    github_source = _attach(
        _loop_source("创建一个可以读取 GitHub 仓库的助手。"),
        github,
    )
    transport = ScriptedRuntimeTransport("unused")
    with _make_client(tmp_path, transport) as client:
        project = _create_project(client, github_source)
        project_id = project["project_id"]
        agent_id = project["agents"][0]["agent_id"]
        _pin(client, project_id, github)
        committed = _commit(client, project_id, agent_id)
        url = f"/api/v1/projects/{project_id}/agents/{agent_id}/run"
        blocked = client.post(
            url,
            json={
                "inputs": {next(iter(github_source["inputs"])): "hi"},
                "source": "committed",
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert blocked.status_code == 422
        assert blocked.json()["code"] == "needs_configuration"
        assert "GitHub" in blocked.json()["message"]
        ready = client.get(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/runtime-readiness",
            params={"version_id": committed["version_id"]},
        ).json()
        assert any(
            item["code"] == "needs_configuration" for item in ready["tool_checks"]
        )
        assert client.get(f"{url}s").json()["runs"] == []


def test_conversation_title_never_returns_a_raw_uuid(tmp_path: Path) -> None:
    source = _set_io(
        _loop_source("创建一个翻译助手。"),
        {"message": "string"},
        {"translation": "string"},
    )
    transport = ScriptedRuntimeTransport("hello")
    leaked = "01a0ca54-c517-787b-bd8d-d4034403f38c"
    with _make_client(tmp_path, transport) as client:
        project = _create_project(client, source)
        project_id = project["project_id"]
        agent_id = project["agents"][0]["agent_id"]
        _commit(client, project_id, agent_id)
        created = client.post(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/conversations",
            json={"title": leaked},
        )
        assert created.status_code == 201, created.text
        assert created.json()["title"] == "New conversation"
        assert leaked not in created.json()["title"]
        listed = client.get(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/conversations"
        ).json()["conversations"]
        assert listed[0]["title"] == "New conversation"
        run_url = f"/api/v1/projects/{project_id}/agents/{agent_id}/run"
        finished = _app_run(
            client,
            run_url,
            {"message": "Translate packaging copy"},
        )
        conversation_id = finished["conversation_id"]
        detail = client.get(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/conversations/{conversation_id}"
        ).json()
        assert detail["title"] == "Translate packaging copy"
        assert leaked not in json.dumps(detail)
