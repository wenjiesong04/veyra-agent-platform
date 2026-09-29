from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.builder.agent_loop_compiler import compile_loop_agent
from veyra_agent_platform.local.builder.specification import infer_agent_specification
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.tools import ToolExecution
from veyra_agent_platform.local.secrets import MacOSKeychainSecretStore

from .test_runtime_routes import (
    ScriptedRuntimeTransport,
    _command_until_settled,
    _run_until_settled,
)

_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)
_KNOWLEDGE_MARKER = "VEYRA_KNOWLEDGE_MARKER_928"
_DOC_MARKER = "VEYRA_DOCUMENT_MARKER_441"


@pytest.fixture(autouse=True)
def isolate_runtime_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MacOSKeychainSecretStore, "get", lambda self, ref: None)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("VEYRA_RUNTIME_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("VEYRA_RUNTIME_MODEL_ID", raising=False)


def _client(
    tmp_path: Path, transport: ScriptedRuntimeTransport, **kwargs: Any
) -> TestClient:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    return TestClient(create_app(settings, runtime_transport=transport, **kwargs))


def _set_io(
    source: dict[str, Any],
    inputs: dict[str, str],
    outputs: dict[str, str],
) -> dict[str, Any]:
    payload = deepcopy(source)
    payload["inputs"] = inputs
    payload["outputs"] = outputs
    primary = next(iter(outputs))
    nodes = []
    for node in payload.get("nodes") or []:
        item = dict(node)
        if item.get("component_type") == "Output":
            item["output_name"] = primary
        nodes.append(item)
    payload["nodes"] = nodes
    return payload


def _loop_source(requirement: str) -> dict[str, Any]:
    spec = infer_agent_specification(requirement)
    return compile_loop_agent(
        spec, ResourceCatalog(), requirement=requirement
    ).to_dict()


def _create_project(client: TestClient, source: dict[str, Any]) -> dict[str, Any]:
    created = client.post("/api/v1/projects", json={"agents": [source]})
    assert created.status_code == 201, created.text
    return created.json()


def _attach(source: dict[str, Any], *resources: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(source)
    lock = dict(payload.get("lock") or {})
    ui = dict(payload.get("ui") or {})
    bindings = dict(ui.get("bindings") or {})
    veyra = dict(payload["extensions"]["veyra"])
    permissions = dict(veyra.get("permissions") or {})
    skill_refs = list(veyra.get("skill_refs") or [])
    for resource in resources:
        reference = str(resource["reference"])
        lock[reference] = str(resource["content_hash"])
        kind = str(resource["kind"])
        bindings[f"bind_{len(bindings) + 1}"] = {
            "kind": "mcp_tool" if kind == "mcp_tool" else kind,
            "reference": reference,
            "x": 40,
            "y": 40,
        }
        if kind == "skill" and reference not in skill_refs:
            skill_refs.append(reference)
        required = resource.get("required_permissions") or {}
        for field in (
            "tools",
            "network_hosts",
            "filesystem_read_roots",
            "filesystem_write_roots",
        ):
            permissions[field] = list(
                dict.fromkeys(
                    [*(permissions.get(field) or []), *(required.get(field) or [])]
                )
            )
        if required.get("shell_workspace_only"):
            permissions["shell_workspace_only"] = True
    veyra["permissions"] = permissions
    veyra["skill_refs"] = skill_refs
    payload["lock"] = lock
    payload["extensions"] = {**payload["extensions"], "veyra": veyra}
    payload["ui"] = {**ui, "bindings": bindings}
    return payload


def _pin(client: TestClient, project_id: str, *resources: dict[str, Any]) -> None:
    for resource in resources:
        response = client.post(
            f"/api/v1/projects/{project_id}/resources",
            json={key: resource[key] for key in ("reference", "content_hash")},
        )
        assert response.status_code == 201, response.text


def _fake_search(**kwargs: Any) -> ToolExecution:
    values = kwargs["values"]
    authorization = kwargs["authorization"]
    output = {
        "provider": "duckduckgo",
        "query": values.get("query"),
        "results": [
            {
                "title": "Fixture search hit",
                "url": "https://example.test/research",
                "snippet": "VEYRA_SEARCH_HIT",
            }
        ],
        "status": 200,
    }
    return ToolExecution(
        output=output,
        receipt={
            "tool_reference": authorization.tool_reference,
            "adapter": authorization.adapter,
            "permission": "allowed",
            "authorization": "allowed",
            "input_digest": authorization.input_digest,
            "output_digest": "a" * 64,
            "byte_length": 12,
            "relative_path": "html.duckduckgo.com",
        },
    )


def _message_blob(calls: list[Any]) -> str:
    return json.dumps(calls, ensure_ascii=False)


def test_research_loop_loads_skill_knowledge_and_search_tool(tmp_path: Path) -> None:
    catalog = ResourceCatalog()
    search = catalog.detail("veyra.tool.web.search", "1.0.0")
    skill = catalog.detail("veyra.skill.research-brief", "1.0.0")
    source = _attach(
        _loop_source("创建一个研究助手，可以搜索网页并整理成报告。"),
        search,
        skill,
    )
    transport = ScriptedRuntimeTransport(
        [
            json.dumps(
                {
                    "action": "tool",
                    "tool": search["reference"],
                    "arguments": {"query": "test topic", "count": 3},
                }
            ),
            json.dumps(
                {
                    "action": "final",
                    "outputs": {"report": "Summary with VEYRA_SEARCH_HIT"},
                }
            ),
        ]
    )
    with _client(
        tmp_path,
        transport,
        tool_adapters={"veyra.runtime.web.search": _fake_search},
    ) as client:
        project = _create_project(client, source)
        project_id = project["project_id"]
        agent_id = project["agents"][0]["agent_id"]
        _pin(client, project_id, search, skill)
        knowledge = client.post(
            f"/api/v1/projects/{project_id}/knowledge",
            json={
                "name": "sample.md",
                "text": f"项目资料 {_KNOWLEDGE_MARKER}",
            },
        ).json()
        assert (
            client.post(
                f"/api/v1/projects/{project_id}/knowledge/{knowledge['knowledge_id']}/index"
            ).status_code
            == 200
        )
        ref = f"{knowledge['knowledge_id']}@{knowledge['version']}"
        url = f"/api/v1/projects/{project_id}/agents/{agent_id}"
        draft = client.get(f"{url}/draft").json()
        draft["source"]["extensions"]["veyra"]["knowledge_refs"] = [ref]
        draft["source"]["lock"][ref] = knowledge["source_file_hash"]
        ui = dict(draft["source"].get("ui") or {})
        bindings = dict(ui.get("bindings") or {})
        bindings["bind_knowledge1"] = {
            "kind": "knowledge",
            "reference": ref,
            "x": 40,
            "y": 220,
        }
        draft["source"]["ui"] = {**ui, "bindings": bindings}
        saved = client.patch(
            f"{url}/draft",
            json={"source": draft["source"], "expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert saved.status_code == 200, saved.text
        waiting = _run_until_settled(
            client,
            f"{url}/run",
            {"query": "请研究一个测试主题，并结合项目资料给出总结。"},
        )
        assert waiting["status"] == "waiting", waiting
        completed = _command_until_settled(
            client, f"{url}/run", str(waiting["run_id"]), "approve"
        )
        assert completed["status"] == "unverified", completed
        assert "VEYRA_SEARCH_HIT" in str(completed["result"])
        events = client.get(f"{url}/runs/{completed['run_id']}").json()["events"]
        kinds = [event["kind"] for event in events]
        assert "skill.loaded" in kinds
        assert "knowledge.retrieved" in kinds
        assert "tool.requested" in kinds
        assert "approval.requested" in kinds
        assert "tool.completed" in kinds
        skill_event = next(event for event in events if event["kind"] == "skill.loaded")
        assert skill_event["payload"]["skill_id"] == skill["resource_id"]
        knowledge_event = next(
            event for event in events if event["kind"] == "knowledge.retrieved"
        )
        assert knowledge_event["payload"]["source_count"] == 1
        assert _KNOWLEDGE_MARKER not in json.dumps(events)
        blob = _message_blob(transport.calls)
        assert "Research Brief" in blob
        assert "State scope, evidence" in blob
        assert _KNOWLEDGE_MARKER in blob
        assert "VEYRA_SEARCH_HIT" in blob
        assert len(transport.calls) == 2


def test_unbound_loop_tool_fails_closed(tmp_path: Path) -> None:
    catalog = ResourceCatalog()
    search = catalog.detail("veyra.tool.web.search", "1.0.0")
    source = _attach(
        _loop_source("创建一个研究助手，可以搜索网页并整理成报告。"),
        search,
    )
    transport = ScriptedRuntimeTransport(
        json.dumps(
            {
                "action": "tool",
                "tool": search["reference"],
                "arguments": {"query": "x", "count": 1},
            }
        )
    )
    with _client(tmp_path, transport) as client:
        project = _create_project(client, source)
        agent = project["agents"][0]
        url = f"/api/v1/projects/{project['project_id']}/agents/{agent['agent_id']}/run"
        failed = _run_until_settled(client, url, {"query": "search"})
        assert failed["status"] == "failed"
        assert failed["error"]["code"] == "resource_unbound"


def test_loop_skill_missing_and_removed_binding(tmp_path: Path) -> None:
    catalog = ResourceCatalog()
    skill = catalog.detail("veyra.skill.research-brief", "1.0.0")
    source = _attach(
        _loop_source("创建一个翻译助手，把中文翻译成自然英语。"),
        skill,
    )
    transport = ScriptedRuntimeTransport(
        '{"action":"final","outputs":{"translation":"Hello"}}'
    )
    with _client(tmp_path, transport) as client:
        project = _create_project(client, source)
        project_id = project["project_id"]
        agent_id = project["agents"][0]["agent_id"]
        url = f"/api/v1/projects/{project_id}/agents/{agent_id}"
        missing = _run_until_settled(client, f"{url}/run", {"text": "你好"})
        assert missing["status"] == "failed"
        assert missing["error"]["code"] == "resource_unbound"
        _pin(client, project_id, skill)
        loaded = _run_until_settled(client, f"{url}/run", {"text": "你好"})
        assert loaded["status"] == "unverified"
        assert "Research Brief" in _message_blob(transport.calls)
        draft = client.get(f"{url}/draft").json()
        draft["source"]["extensions"]["veyra"]["skill_refs"] = []
        draft["source"]["ui"]["bindings"] = {
            key: value
            for key, value in (draft["source"]["ui"].get("bindings") or {}).items()
            if value.get("kind") != "skill"
        }
        draft["source"]["lock"].pop(skill["reference"], None)
        saved = client.patch(
            f"{url}/draft",
            json={"source": draft["source"], "expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert saved.status_code == 200, saved.text
        transport.calls.clear()
        gone = _run_until_settled(client, f"{url}/run", {"text": "你好"})
        assert gone["status"] == "unverified"
        assert "Research Brief" not in _message_blob(transport.calls)


def test_loop_image_input_becomes_provider_image_part(tmp_path: Path) -> None:
    source = _set_io(
        _loop_source("创建一个翻译助手，把中文翻译成自然英语。"),
        {"item-image": "image", "description": "string"},
        {"analysis": "object"},
    )
    transport = ScriptedRuntimeTransport(
        '{"action":"final","outputs":{"analysis":{"ok":true,"note":"seen"}}}'
    )
    with _client(tmp_path, transport) as client:
        project = _create_project(client, source)
        uploaded = client.post(
            f"/api/v1/projects/{project['project_id']}/artifacts",
            files={"file": ("item.png", _PNG, "image/png")},
        ).json()
        ref = {
            "kind": "artifact",
            "artifact_id": uploaded["artifact_id"],
            "media_type": "image/png",
            "filename": "item.png",
        }
        url = (
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{project['agents'][0]['agent_id']}/run"
        )
        result = _run_until_settled(
            client,
            url,
            {"item-image": ref, "description": "gift box"},
        )
        assert result["status"] == "unverified", result
        assert result["result"]["analysis"]["ok"] is True
        user = transport.calls[0][1]
        content = user["content"]
        assert isinstance(content, list)
        image_parts = [
            part
            for part in content
            if isinstance(part, dict) and part.get("type") == "image_url"
        ]
        assert image_parts
        url_value = image_parts[0]["image_url"]["url"]
        assert url_value.startswith("data:image/png;base64,")
        assert uploaded["artifact_id"] not in url_value
        dumped = json.dumps(content)
        assert "artifact://" not in dumped
        assert str(tmp_path) not in dumped


def test_loop_document_input_uses_extracted_text(tmp_path: Path) -> None:
    source = _set_io(
        _loop_source("创建一个翻译助手，把中文翻译成自然英语。"),
        {"brief": "document"},
        {"result": "string"},
    )
    transport = ScriptedRuntimeTransport(
        '{"action":"final","outputs":{"result":"noted"}}'
    )
    with _client(tmp_path, transport) as client:
        project = _create_project(client, source)
        uploaded = client.post(
            f"/api/v1/projects/{project['project_id']}/artifacts",
            files={"file": ("notes.md", _DOC_MARKER.encode("utf-8"), "text/markdown")},
        ).json()
        ref = {
            "kind": "artifact",
            "artifact_id": uploaded["artifact_id"],
            "media_type": "text/markdown",
            "filename": "notes.md",
        }
        url = (
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{project['agents'][0]['agent_id']}/run"
        )
        result = _run_until_settled(client, url, {"brief": ref})
        assert result["status"] == "unverified", result
        blob = _message_blob(transport.calls)
        assert _DOC_MARKER in blob
        assert "notes.md" in blob
        assert uploaded["artifact_id"] not in blob
        assert str(tmp_path) not in blob
        user = transport.calls[0][1]["content"]
        assert isinstance(user, str)
        assert "base64" not in user.casefold()


def test_loop_pdf_input_uses_extracted_text(tmp_path: Path) -> None:
    source = _set_io(
        _loop_source("创建一个翻译助手，把中文翻译成自然英语。"),
        {"brief": "pdf"},
        {"result": "string"},
    )
    pdf = (
        b"%PDF-1.4\n1 0 obj\n<< /Length 40 >>\nstream\n"
        b"BT (Santa candy box) Tj ET\nendstream\nendobj\n"
    )
    transport = ScriptedRuntimeTransport(
        '{"action":"final","outputs":{"result":"noted"}}'
    )
    with _client(tmp_path, transport) as client:
        project = _create_project(client, source)
        uploaded = client.post(
            f"/api/v1/projects/{project['project_id']}/artifacts",
            files={"file": ("box.pdf", pdf, "application/pdf")},
        ).json()
        ref = {
            "kind": "artifact",
            "artifact_id": uploaded["artifact_id"],
            "media_type": "application/pdf",
            "filename": "box.pdf",
        }
        url = (
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{project['agents'][0]['agent_id']}/run"
        )
        result = _run_until_settled(client, url, {"brief": ref})
        assert result["status"] == "unverified", result
        blob = _message_blob(transport.calls)
        assert "Santa candy box" in blob
        assert "box.pdf" in blob
        assert uploaded["artifact_id"] not in blob
        assert "%PDF" not in blob
        assert str(tmp_path) not in blob


def test_workspace_inspector_completes_search_then_read(tmp_path: Path) -> None:
    catalog = ResourceCatalog()
    search = catalog.detail("veyra.tool.filesystem.search", "1.0.0")
    read = catalog.detail("veyra.tool.filesystem.read", "1.0.0")
    source = _set_io(
        _attach(
            _loop_source("创建一个翻译助手，把中文翻译成自然英语。"),
            search,
            read,
        ),
        {"request": "string"},
        {"result": "string"},
    )
    transport = ScriptedRuntimeTransport(
        [
            json.dumps(
                {
                    "action": "tool",
                    "tool": search["reference"],
                    "arguments": {"path": ".", "query": "inspector-marker"},
                }
            ),
            json.dumps(
                {
                    "action": "tool",
                    "tool": read["reference"],
                    "arguments": {"path": "notes/alpha.txt"},
                }
            ),
            json.dumps(
                {"action": "final", "outputs": {"result": "found inspector-marker"}}
            ),
        ]
    )
    with _client(tmp_path, transport) as client:
        project = _create_project(client, source)
        project_id = project["project_id"]
        _pin(client, project_id, search, read)
        notes = Path(project["root_path"]) / "notes"
        notes.mkdir()
        (notes / "alpha.txt").write_text("inspector-marker in file", encoding="utf-8")
        url = (
            f"/api/v1/projects/{project_id}/agents/"
            f"{project['agents'][0]['agent_id']}/run"
        )
        result = _run_until_settled(client, url, {"request": "inspect workspace"})
        assert result["status"] == "unverified", result
        assert result["result"] == {"result": "found inspector-marker"}
        assert len(transport.calls) == 3
        events = client.get(
            f"/api/v1/projects/{project_id}/agents/"
            f"{project['agents'][0]['agent_id']}/runs/{result['run_id']}"
        ).json()["events"]
        completed = [
            event["payload"]["tool_reference"]
            for event in events
            if event["kind"] == "tool.completed"
        ]
        assert completed == [search["reference"], read["reference"]]


def test_project_pin_reuses_hash_and_rejects_mismatch(tmp_path: Path) -> None:
    catalog = ResourceCatalog()
    search = catalog.detail("veyra.tool.web.search", "1.0.0")
    transport = ScriptedRuntimeTransport(
        '{"action":"final","outputs":{"translation":"Hello"}}'
    )
    with _client(tmp_path, transport) as client:
        project = client.post("/api/v1/projects", json={"name": "Pins"}).json()
        project_id = project["project_id"]
        url = f"/api/v1/projects/{project_id}/resources"
        mismatched = client.post(
            url,
            json={"reference": search["reference"], "content_hash": "0" * 64},
        )
        assert mismatched.status_code == 409
        assert mismatched.json()["code"] == "resource_identity_conflict"
        first = client.post(
            url,
            json={
                "reference": search["reference"],
                "content_hash": search["content_hash"],
            },
        )
        assert first.status_code == 201, first.text
        reused = client.post(
            url,
            json={
                "reference": search["reference"],
                "content_hash": search["content_hash"],
            },
        )
        assert reused.status_code == 201, reused.text
        pins = [
            item
            for item in reused.json()["resources"]
            if item.get("reference") == search["reference"]
            and item.get("scope") == "project"
        ]
        assert len(pins) == 1
        assert pins[0]["bound_content_hash"] == search["content_hash"]
        conflict = client.post(
            url,
            json={"reference": search["reference"], "content_hash": "1" * 64},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "resource_binding_conflict"


def test_loop_missing_knowledge_is_blocked(tmp_path: Path) -> None:
    source = _loop_source("创建一个翻译助手，把中文翻译成自然英语。")
    ref = f"{new_uuid7()}@1.0.0"
    source["extensions"]["veyra"]["knowledge_refs"] = [ref]
    source["lock"][ref] = "a" * 64
    transport = ScriptedRuntimeTransport(
        '{"action":"final","outputs":{"translation":"Hello"}}'
    )
    with _client(tmp_path, transport) as client:
        project = _create_project(client, source)
        url = (
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{project['agents'][0]['agent_id']}/run"
        )
        failed = _run_until_settled(client, url, {"text": "你好"})
        assert failed["status"] == "failed"
        assert failed["error"]["code"] == "project_invalid"
        assert "Knowledge" in failed["error"]["message"]


def test_loop_object_input_stays_structured_json(tmp_path: Path) -> None:
    source = _set_io(
        _loop_source("创建一个翻译助手，把中文翻译成自然英语。"),
        {"details": "object"},
        {"result": "string"},
    )
    transport = ScriptedRuntimeTransport('{"action":"final","outputs":{"result":"ok"}}')
    with _client(tmp_path, transport) as client:
        project = _create_project(client, source)
        url = (
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{project['agents'][0]['agent_id']}/run"
        )
        result = _run_until_settled(
            client,
            url,
            {
                "details": {
                    "occasion": "Christmas",
                    "recipient": "friend",
                    "budget": 200,
                }
            },
        )
        assert result["status"] == "unverified", result
        user = transport.calls[0][1]["content"]
        assert isinstance(user, str)
        assert '"occasion": "Christmas"' in user
        assert '"budget": 200' in user
        assert "artifact://" not in user
