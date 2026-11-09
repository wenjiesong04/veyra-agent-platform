from __future__ import annotations

import json
import threading
from contextlib import AbstractContextManager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.secrets import MacOSKeychainSecretStore

from .test_factory_routes import ScriptedKimiTransport, _completion
from .test_runtime_routes import (
    ScriptedRuntimeTransport,
    _command_until_settled,
    _run_until_settled,
)
from .verified_runtime_model import verified_client

_SKILL_GOAL = (
    "创建一个 Agent。capability: structured_comparison_method。"
    "它需要一种当前 Veyra 没有的结构化比较方法。"
)
_SKILL_INSTRUCTION = (
    "Purpose\n"
    "Compare supplied product options using the customer's stated priorities.\n\n"
    "When to use\n"
    "Use when option specifications and a customer priority list are provided.\n\n"
    "Procedure\n"
    "1. Extract price, material, and delivery time from each provided option.\n"
    "2. Mark missing values as unknown.\n"
    "3. Rank options by the customer's priority order, recording supporting facts.\n\n"
    "Expected output\n"
    "A comparison table, ordered recommendation, and unresolved questions.\n\n"
    "Constraints\n"
    "Use only provided facts; do not invent specifications or external access.\n\n"
    "Failure handling\n"
    "Ask the customer for priorities or missing information before ranking."
)
_LOOKUP_GOAL = "创建一个 Agent。capability: mock_status_lookup。"
_SHELL_GOAL = "创建一个 Agent。capability: run_arbitrary_shell。"
_IMAGE_GOAL = "创建一个可以直接生成最终包装设计图片的 Agent。"
_MOCK_MARKER = "VEYRA_MOCK_STATUS"


@pytest.fixture(autouse=True)
def isolate_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MacOSKeychainSecretStore, "get", lambda self, ref: None)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("VEYRA_FACTORY_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("VEYRA_FACTORY_MODEL_ID", raising=False)
    monkeypatch.delenv("VEYRA_RUNTIME_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("VEYRA_RUNTIME_MODEL_ID", raising=False)


def _app_client(
    tmp_path: Path,
    *,
    factory_transport: ScriptedKimiTransport | None = None,
    runtime_transport: ScriptedRuntimeTransport | None = None,
) -> AbstractContextManager[TestClient]:
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    factory = factory_transport or ScriptedKimiTransport([_completion("ok")])
    if runtime_transport is None:
        return TestClient(create_app(settings, factory_transport=factory))
    return verified_client(settings, runtime_transport, factory_transport=factory)


def _project(client: TestClient) -> str:
    created = client.post("/api/v1/projects", json={"name": "Factory"})
    assert created.status_code == 201
    return created.json()["project_id"]


def _generate(client: TestClient, project_id: str, goal: str) -> dict[str, Any]:
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


def _plan_for(session: dict[str, Any], capability: str) -> dict[str, Any]:
    return next(
        item
        for item in session["resource_factory_plans"]
        if item["capability"] == capability
    )


def _approve_user_method(
    client: TestClient, project_id: str, session: dict[str, Any]
) -> dict[str, Any]:
    planned = _plan_for(session, "structured_comparison_method")
    factory_url = (
        f"/api/v1/projects/{project_id}/factory/sessions/"
        f"{session['session_id']}/factory-resources/approve"
    )
    scaffold_approval = client.post(
        factory_url,
        json={
            "confirm": True,
            "capability": "structured_comparison_method",
            "content_hash": planned["snapshot_hash"],
            "bind_to_project": True,
        },
    )
    assert scaffold_approval.status_code == 422, scaffold_approval.text
    assert scaffold_approval.json()["code"] == "factory_skill_instruction_required"
    resource = planned["draft"]
    workshop_url = (
        f"/api/v1/resources/{resource['resource_id']}/versions/"
        f"{resource['version']}/approve"
    )
    shortcut = client.post(workshop_url, json={})
    assert shortcut.status_code == 422, shortcut.text
    assert shortcut.json()["code"] == "workshop_instruction_required"
    supplied = client.post(workshop_url, json={"instruction": _SKILL_INSTRUCTION})
    assert supplied.status_code == 200, supplied.text
    reviewed = supplied.json()["resource"]
    assert reviewed["availability"] == "ready"
    assert reviewed["spec"]["instruction"] == _SKILL_INSTRUCTION
    assert reviewed["spec"]["instruction_status"] == "provided"
    assert reviewed["content_hash"] != resource["content_hash"]
    approved = client.post(
        factory_url,
        json={
            "confirm": True,
            "capability": "structured_comparison_method",
            "content_hash": reviewed["content_hash"],
            "bind_to_project": True,
        },
    )
    assert approved.status_code == 200, approved.text
    return approved.json()


def _start_mock_http() -> tuple[HTTPServer, int]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0] == "/status":
                body = json.dumps({"state": "ok", "marker": _MOCK_MARKER}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, int(server.server_address[1])


def test_generate_skill_approve_resolver_runtime(tmp_path: Path) -> None:
    runtime = ScriptedRuntimeTransport(
        [
            json.dumps(
                {"action": "final", "outputs": {"result": "compared"}},
            )
        ]
    )
    with _app_client(tmp_path, runtime_transport=runtime) as client:
        project_id = _project(client)
        session = _generate(client, project_id, _SKILL_GOAL)
        missing = [
            item
            for item in session["resource_plan"]
            if item.get("capability") == "structured_comparison_method"
            and item.get("bind_status") == "missing"
        ]
        assert missing
        assert missing[0]["factory_status"] == "requires_user_configuration"
        planned = _plan_for(session, "structured_comparison_method")
        assert planned["strategy"] == "skill_instruction"
        assert planned["draft"]["availability"] == "quarantined"
        assert planned["validation"]["passed"] is False
        assert planned["requirements"] == ["skill_instruction"]
        assert planned["draft"]["spec"]["instruction_status"] == "scaffold"
        first_hash = planned["snapshot_hash"]
        reloaded = client.get(
            f"/api/v1/projects/{project_id}/factory/sessions/{session['session_id']}"
        ).json()
        again = _plan_for(reloaded, "structured_comparison_method")
        assert again["proposal_id"] == planned["proposal_id"]
        assert again["operation_id"] == planned["operation_id"]
        assert again["snapshot_hash"] == first_hash
        assert (
            again["draft"]["spec"]["instruction"]
            == planned["draft"]["spec"]["instruction"]
        )

        tampered = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{session['session_id']}/factory-resources/approve",
            json={
                "confirm": True,
                "capability": "structured_comparison_method",
                "content_hash": "0" * 64,
            },
        )
        assert tampered.status_code == 422
        assert tampered.json()["code"] == "factory_snapshot_mismatch"

        approved = _approve_user_method(client, project_id, session)
        published_plan = _plan_for(approved, "structured_comparison_method")
        assert published_plan["status"] == "generatable"
        assert published_plan["requirements"] == []
        assert published_plan["validation"]["passed"] is True
        published = published_plan["published"]
        selected = next(
            item
            for item in approved["resource_plan"]
            if item.get("capability") == "structured_comparison_method"
        )
        assert selected["bind_status"] in {"will_bind", "already_bound"}
        assert selected["reference"] == published["reference"]

        second = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{session['session_id']}/factory-resources/approve",
            json={
                "confirm": True,
                "capability": "structured_comparison_method",
                "content_hash": published["content_hash"],
                "bind_to_project": True,
            },
        )
        assert second.status_code == 200, second.text
        assert (
            _plan_for(second.json(), "structured_comparison_method")["published"][
                "content_hash"
            ]
            == published["content_hash"]
        )

        applied = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{session['session_id']}/apply-draft",
            json={"confirm": True},
        )
        assert applied.status_code == 200, applied.text
        agent_id = applied.json()["agent"]["agent_id"]
        draft = client.get(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/draft"
        ).json()
        assert (
            published["reference"]
            in draft["source"]["extensions"]["veyra"]["skill_refs"]
        )
        assert (
            draft["source"]["lock"][published["reference"]] == published["content_hash"]
        )
        waiting = _run_until_settled(
            client,
            f"/api/v1/projects/{project_id}/agents/{agent_id}/run",
            {"request": "compare two options"},
        )
        if waiting["status"] == "waiting":
            waiting = _command_until_settled(
                client,
                f"/api/v1/projects/{project_id}/agents/{agent_id}/run",
                str(waiting["run_id"]),
                "approve",
            )
        assert waiting["status"] == "unverified", waiting
        events = client.get(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/runs/{waiting['run_id']}"
        ).json()["events"]
        loaded = next(event for event in events if event["kind"] == "skill.loaded")
        assert loaded["payload"]["skill_id"] == published["resource_id"]
        blob = json.dumps(runtime.calls, ensure_ascii=False)
        assert "Structured Comparison Method" in blob
        assert "Purpose" in blob
        assert _SKILL_INSTRUCTION in runtime.calls[-1][0]["content"]


def test_generated_http_wrapper_runs_against_localhost(tmp_path: Path) -> None:
    server, port = _start_mock_http()
    try:
        runtime = ScriptedRuntimeTransport([])
        with _app_client(tmp_path, runtime_transport=runtime) as client:
            project_id = _project(client)
            session = _generate(client, project_id, _LOOKUP_GOAL)
            missing = next(
                item
                for item in session["resource_plan"]
                if item.get("capability") == "mock_status_lookup"
            )
            assert missing["bind_status"] == "missing"
            assert missing["factory_status"] == "requires_user_configuration"
            drafted = client.post(
                f"/api/v1/projects/{project_id}/factory/sessions/"
                f"{session['session_id']}/factory-resources/drafts",
                json={
                    "confirm": True,
                    "capability": "mock_status_lookup",
                    "wrapper": {
                        "base_adapter": "veyra.runtime.http.request",
                        "allowed_hosts": ["127.0.0.1"],
                        "methods": ["GET"],
                        "path_prefix": "/status",
                        "port": port,
                        "scheme": "http",
                        "input_schema": {"code": "string"},
                        "timeout_ms": 2000,
                        "max_response_bytes": 4096,
                    },
                },
            )
            assert drafted.status_code == 200, drafted.text
            planned = _plan_for(drafted.json(), "mock_status_lookup")
            assert planned["status"] == "generatable"
            assert planned["draft"]["spec"]["adapter"] == "veyra.runtime.http.request"
            approved = client.post(
                f"/api/v1/projects/{project_id}/factory/sessions/"
                f"{session['session_id']}/factory-resources/approve",
                json={
                    "confirm": True,
                    "capability": "mock_status_lookup",
                    "content_hash": planned["snapshot_hash"],
                    "bind_to_project": True,
                },
            )
            assert approved.status_code == 200, approved.text
            published = _plan_for(approved.json(), "mock_status_lookup")["published"]
            selected = next(
                item
                for item in approved.json()["resource_plan"]
                if item.get("capability") == "mock_status_lookup"
            )
            assert selected["bind_status"] in {"will_bind", "already_bound"}
            applied = client.post(
                f"/api/v1/projects/{project_id}/factory/sessions/"
                f"{session['session_id']}/apply-draft",
                json={"confirm": True},
            )
            assert applied.status_code == 200, applied.text
            agent_id = applied.json()["agent"]["agent_id"]
            runtime.script = [
                json.dumps(
                    {
                        "action": "tool",
                        "tool": published["reference"],
                        "arguments": {"code": "ok"},
                    }
                ),
                json.dumps(
                    {
                        "action": "final",
                        "outputs": {"result": _MOCK_MARKER},
                    }
                ),
            ]
            waiting = _run_until_settled(
                client,
                f"/api/v1/projects/{project_id}/agents/{agent_id}/run",
                {"request": "lookup status"},
            )
            assert waiting["status"] == "waiting", waiting
            completed = _command_until_settled(
                client,
                f"/api/v1/projects/{project_id}/agents/{agent_id}/run",
                str(waiting["run_id"]),
                "approve",
            )
            assert completed["status"] == "unverified", completed
            assert _MOCK_MARKER in str(completed["result"])
            events = client.get(
                f"/api/v1/projects/{project_id}/agents/{agent_id}/runs/"
                f"{completed['run_id']}"
            ).json()["events"]
            finished = next(
                event for event in events if event["kind"] == "tool.completed"
            )
            receipt = finished["payload"]
            assert receipt["factory_resource_id"] == published["resource_id"]
            assert receipt["factory_resource_version"] == published["version"]
            assert receipt["base_adapter"] == "veyra.runtime.http.request"
            assert receipt["relative_path"] == "127.0.0.1"
            blob = json.dumps(runtime.calls, ensure_ascii=False)
            assert _MOCK_MARKER in blob
            assert "api.example.com" not in blob
    finally:
        server.shutdown()
        server.server_close()


def test_unsafe_shell_factory_is_unsupported(tmp_path: Path) -> None:
    with _app_client(tmp_path) as client:
        project_id = _project(client)
        session = _generate(client, project_id, _SHELL_GOAL)
        planned = _plan_for(session, "run_arbitrary_shell")
        assert planned["status"] == "unsupported"
        assert planned["can_generate"] is False
        refused = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{session['session_id']}/factory-resources/drafts",
            json={
                "confirm": True,
                "capability": "run_arbitrary_shell",
                "wrapper": {"base_adapter": "veyra.runtime.shell.exec"},
            },
        )
        assert refused.status_code == 422
        assert refused.json()["code"] == "factory_unsupported"
        catalog = client.get("/api/v1/resources", params={"kind": "tool"}).json()
        assert not any(
            "run-arbitrary-shell" in item["resource_id"]
            for item in catalog["resources"]
            if item.get("origin") == "workshop"
        )


def test_unrestricted_http_wrapper_is_rejected(tmp_path: Path) -> None:
    with _app_client(tmp_path) as client:
        project_id = _project(client)
        session = _generate(client, project_id, _LOOKUP_GOAL)
        refused = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{session['session_id']}/factory-resources/drafts",
            json={
                "confirm": True,
                "capability": "mock_status_lookup",
                "wrapper": {
                    "base_adapter": "veyra.runtime.http.request",
                    "allowed_hosts": ["*"],
                    "methods": ["GET", "*"],
                    "path_prefix": "/",
                    "input_schema": {
                        "url": "string",
                        "method": "string",
                        "headers": "object",
                    },
                },
            },
        )
        assert refused.status_code == 422
        code = refused.json()["code"]
        assert code in {
            "factory_unsupported",
            "factory_validation_failed",
            "factory_requires_configuration",
        }


def test_image_generation_stays_missing_and_unsupported(tmp_path: Path) -> None:
    with _app_client(tmp_path) as client:
        project_id = _project(client)
        session = _generate(client, project_id, _IMAGE_GOAL)
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
        refused = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{session['session_id']}/factory-resources/drafts",
            json={"confirm": True, "capability": "image_generation"},
        )
        assert refused.status_code == 422
        assert refused.json()["code"] == "factory_capability_missing"


def test_disable_published_skill_drops_resolver_selection(tmp_path: Path) -> None:
    runtime = ScriptedRuntimeTransport(
        [json.dumps({"action": "final", "outputs": {"result": "compared"}})]
    )
    with _app_client(tmp_path, runtime_transport=runtime) as client:
        project_id = _project(client)
        session = _generate(client, project_id, _SKILL_GOAL)
        planned = _plan_for(session, "structured_comparison_method")
        assert planned["status"] == "requires_user_configuration"
        assert planned["validation"]["passed"] is False
        approved = _approve_user_method(client, project_id, session)
        published = _plan_for(approved, "structured_comparison_method")["published"]
        applied = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{session['session_id']}/apply-draft",
            json={"confirm": True},
        )
        assert applied.status_code == 200, applied.text
        agent_id = applied.json()["agent"]["agent_id"]
        disabled = client.post(
            f"/api/v1/resources/{published['resource_id']}/versions/"
            f"{published['version']}/enable",
            json={"enabled": False},
        )
        assert disabled.status_code == 200, disabled.text
        assert disabled.json()["resource"]["availability"] == "disabled"
        refused = client.post(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/run",
            json={"inputs": {"request": "compare two provided options"}},
        )
        assert refused.status_code == 422, refused.text
        assert not runtime.calls
        retry = _generate(client, project_id, _SKILL_GOAL)
        missing = [
            item
            for item in retry["resource_plan"]
            if item.get("capability") == "structured_comparison_method"
            and item.get("bind_status") == "missing"
        ]
        assert missing
        assert not any(
            item.get("reference") == published["reference"]
            and item.get("bind_status") in {"will_bind", "already_bound"}
            for item in retry["resource_plan"]
        )
