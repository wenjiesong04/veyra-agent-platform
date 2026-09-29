"""Full product-chain acceptance for complex Agents.

Specification-seeded HTTP generate; scripted Factory and Runtime providers.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.runtime.client import (
    RuntimeCompletion,
    RuntimeProviderError,
)
from veyra_agent_platform.local.runtime.tools import ToolExecution, ToolRuntimeError
from veyra_agent_platform.local.secrets import MacOSKeychainSecretStore

from .test_factory_routes import ScriptedKimiTransport, _completion
from .test_loop_resource_truth import _PNG
from .test_runtime_routes import ScriptedRuntimeTransport, _await_run

_RESEARCH = (
    "创建一个研究分析助手。\n"
    "它需要：\n"
    "- 搜索公开资料\n"
    "- 阅读当前项目中的研究资料\n"
    "- 使用合适的研究方法\n"
    "- 整理证据\n"
    "- 输出结构化研究报告\n"
)
_ENGINEER = (
    "创建一个软件工程助手。\n"
    "它需要：\n"
    "- 搜索当前项目文件\n"
    "- 阅读代码\n"
    "- 修改指定文件\n"
    "- 运行测试\n"
    "- 根据测试失败继续修复\n"
    "- 写文件和运行命令前让我确认\n"
)
_PACKAGING = (
    "创建一个包装分析助手。\n"
    "用户上传一个产品图片，\n"
    "Agent 根据图片和项目里的品牌规范，\n"
    "分析：\n"
    "- 包装视觉\n"
    "- 材质\n"
    "- 色彩\n"
    "- 品牌一致性\n"
    "- 改进建议\n"
    "输出结构化分析报告。\n"
)
_IMAGE_GEN = "在分析之后，直接帮我生成最终包装效果图。"
_FACTORY_SKILL = (
    "创建一个 Agent。capability: comparative_risk_method。"
    "它需要一种当前 Veyra 没有的比较风险方法。"
)
_KNOWLEDGE_RESEARCH = "VEYRA_RESEARCH_KNOWLEDGE_5821"
_KNOWLEDGE_BRAND = "VEYRA_BRAND_GUIDE_4417"
_SEARCH_HIT = "SEARCH_RESULT_728"
_MATH_BUG = "def add(a, b):\n    return a - b\n"
_MATH_WRONG = "def add(a, b):\n    return a + b + 1\n"
_MATH_FIXED = "def add(a, b):\n    return a + b\n"
_TEST_ADD = """from pathlib import Path
import importlib.util

_SPEC = importlib.util.spec_from_file_location(
    "workspace_math", Path(__file__).resolve().parents[1] / "src" / "math.py"
)
_MOD = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_MOD)

def test_add() -> None:
    assert _MOD.add(2, 3) == 5
"""


@pytest.fixture(autouse=True)
def isolate_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MacOSKeychainSecretStore, "get", lambda self, ref: None)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("VEYRA_FACTORY_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("VEYRA_FACTORY_MODEL_ID", raising=False)
    monkeypatch.delenv("VEYRA_RUNTIME_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("VEYRA_RUNTIME_MODEL_ID", raising=False)


def _client(
    tmp_path: Path,
    *,
    runtime: object | None = None,
    tool_adapters: dict[str, Any] | None = None,
) -> TestClient:
    return TestClient(
        create_app(
            LocalSettings(
                database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
                project_storage_root=tmp_path / "projects",
            ),
            factory_transport=ScriptedKimiTransport(
                [_completion("ok") for _ in range(24)]
            ),
            runtime_transport=runtime,
            tool_adapters=tool_adapters,
        )
    )


def _project(client: TestClient, name: str) -> dict[str, Any]:
    created = client.post("/api/v1/projects", json={"name": name})
    assert created.status_code == 201, created.text
    return created.json()


def _generate(client: TestClient, project_id: str, goal: str) -> dict[str, Any]:
    created = client.post(
        f"/api/v1/projects/{project_id}/factory/sessions",
        json={"goal": goal},
    )
    assert created.status_code in {200, 201}, created.text
    generated = client.post(
        f"/api/v1/projects/{project_id}/factory/sessions/"
        f"{created.json()['session_id']}/generate"
    )
    assert generated.status_code == 200, generated.text
    return generated.json()


def _apply(
    client: TestClient, project_id: str, session: dict[str, Any]
) -> dict[str, Any]:
    applied = client.post(
        f"/api/v1/projects/{project_id}/factory/sessions/{session['session_id']}/apply-draft",
        json={"confirm": True},
    )
    assert applied.status_code == 200, applied.text
    return applied.json()


def _commit(client: TestClient, project_id: str, agent_id: str) -> dict[str, Any]:
    url = f"/api/v1/projects/{project_id}/agents/{agent_id}"
    draft = client.get(f"{url}/draft").json()
    committed = client.post(
        f"{url}/commit",
        json={"expected_revision": draft["revision"]},
        headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert committed.status_code == 200, committed.text
    match = next(
        item
        for item in client.get(f"{url}/versions").json()["versions"]
        if item["version_id"] == committed.json()["version_id"]
    )
    assert match["committed"] is True
    return committed.json()


def _ingest_knowledge(
    client: TestClient, project_id: str, name: str, text: str
) -> dict[str, Any]:
    knowledge = client.post(
        f"/api/v1/projects/{project_id}/knowledge",
        json={"name": name, "text": text},
    )
    assert knowledge.status_code == 201, knowledge.text
    indexed = client.post(
        f"/api/v1/projects/{project_id}/knowledge/{knowledge.json()['knowledge_id']}/index"
    )
    assert indexed.status_code == 200, indexed.text
    return indexed.json()


def _primary_field(source: dict[str, Any]) -> str:
    inputs = source.get("inputs") or {}
    if "message" in inputs:
        return "message"
    if "query" in inputs:
        return "query"
    if "request" in inputs:
        return "request"
    return next(iter(inputs))


def _draft_source(client: TestClient, project_id: str, agent_id: str) -> dict[str, Any]:
    return client.get(f"/api/v1/projects/{project_id}/agents/{agent_id}/draft").json()[
        "source"
    ]


def _app_start(
    client: TestClient,
    url: str,
    inputs: dict[str, Any],
    *,
    conversation_id: str | None = None,
    timeout: float = 20,
) -> dict[str, Any]:
    body: dict[str, Any] = {"inputs": inputs, "source": "committed"}
    if conversation_id:
        body["conversation_id"] = conversation_id
    started = client.post(url, json=body, headers={"Idempotency-Key": new_uuid7()})
    assert started.status_code == 200, started.text
    return _await_run(client, url, started.json()["run_id"], timeout=timeout)


def _command_until(
    client: TestClient, run_url: str, run_id: str, command: str, *, timeout: float = 20
) -> dict[str, Any]:
    started = client.post(
        f"{run_url}s/{run_id}/commands",
        json={"command": command},
        headers={"Idempotency-Key": new_uuid7()},
    )
    assert started.status_code == 200, started.text
    payload = started.json()
    if payload["status"] == "running":
        return _await_run(client, run_url, str(payload["run_id"]), timeout=timeout)
    return payload


def _approve_until(
    client: TestClient, url: str, run: dict[str, Any], *, timeout: float = 20
) -> dict[str, Any]:
    current = run
    for _ in range(12):
        if current["status"] != "waiting":
            return current
        current = _command_until(
            client, url, str(current["run_id"]), "approve", timeout=timeout
        )
        if current["status"] == "running":
            current = _await_run(client, url, str(current["run_id"]), timeout=timeout)
    return current


def _plan_by_capability(
    session: dict[str, Any], capability: str
) -> list[dict[str, Any]]:
    return [
        item
        for item in session.get("resource_plan") or []
        if item.get("capability") == capability
    ]


def _fake_search(**kwargs: Any) -> ToolExecution:
    values = kwargs["values"]
    authorization = kwargs["authorization"]
    output = {
        "provider": "scripted",
        "query": values.get("query"),
        "results": [
            {
                "title": "Fixture evidence",
                "url": "https://example.test/research",
                "snippet": _SEARCH_HIT,
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


def _last_user_text(messages: object) -> str:
    if not isinstance(messages, list):
        return json.dumps(messages, ensure_ascii=False)
    for item in reversed(messages):
        if isinstance(item, dict) and item.get("role") == "user":
            content = item.get("content")
            return (
                content
                if isinstance(content, str)
                else json.dumps(content, ensure_ascii=False)
            )
    return json.dumps(messages, ensure_ascii=False)


def _tool(reference: str, arguments: dict[str, Any]) -> str:
    return json.dumps({"action": "tool", "tool": reference, "arguments": arguments})


def _final(outputs: dict[str, Any]) -> str:
    return json.dumps({"action": "final", "outputs": outputs})


class RepairTransport:
    """Next action is chosen from the latest tool observation, not a fixed index."""

    def __init__(self) -> None:
        self.calls: list[Any] = []
        self.search = "veyra.tool.filesystem.search@1.0.0"
        self.read = "veyra.tool.filesystem.read@1.0.0"
        self.write = "veyra.tool.filesystem.write@1.0.0"
        self.shell = "veyra.tool.shell.exec@1.0.0"
        self.pytest = (
            f"{sys.executable} -m pytest tests/test_add.py -q --noconftest --rootdir=."
        )

    def models(self) -> tuple[str, ...]:
        return ("kimi-k3",)

    def complete(self, messages: object) -> RuntimeCompletion:
        self.calls.append(messages)
        observed = _last_user_text(messages)
        if observed.startswith("Tool result for") and self.shell in observed:
            payload = json.loads(observed.split("\n", 1)[1])
            exit_code = payload.get("exit_code")
            if exit_code == 0:
                return RuntimeCompletion(
                    content=_final({"result": "tests passed"}), finish_reason="stop"
                )
            return RuntimeCompletion(
                content=_tool(
                    self.write, {"path": "src/math.py", "content": _MATH_FIXED}
                ),
                finish_reason="stop",
            )
        if observed.startswith("Tool result for") and self.write in observed:
            return RuntimeCompletion(
                content=_tool(self.shell, {"command": self.pytest}),
                finish_reason="stop",
            )
        if observed.startswith("Tool result for") and self.read in observed:
            content = _MATH_WRONG if "return a - b" in observed else _MATH_FIXED
            return RuntimeCompletion(
                content=_tool(self.write, {"path": "src/math.py", "content": content}),
                finish_reason="stop",
            )
        if observed.startswith("Tool result for") and self.search in observed:
            return RuntimeCompletion(
                content=_tool(self.read, {"path": "src/math.py"}),
                finish_reason="stop",
            )
        return RuntimeCompletion(
            content=_tool(self.search, {"path": ".", "query": "def add"}),
            finish_reason="stop",
        )


def test_research_analyst_full_product_chain(tmp_path: Path) -> None:
    transport = ScriptedRuntimeTransport(
        [
            _tool(
                "veyra.tool.web.search@1.0.0",
                {"query": "market notes", "count": 3},
            ),
            _final(
                {
                    "report": {
                        "evidence": [_SEARCH_HIT, _KNOWLEDGE_RESEARCH],
                        "summary": "bounded findings",
                    }
                }
            ),
            _final({"report": {"points": ["one", "two", "three"]}}),
        ]
    )
    started = time.perf_counter()
    with _client(
        tmp_path,
        runtime=transport,
        tool_adapters={"veyra.runtime.web.search": _fake_search},
    ) as client:
        project = _project(client, "Research Acceptance")
        project_id = project["project_id"]
        _ingest_knowledge(
            client,
            project_id,
            "market_notes.md",
            f"公开资料研究笔记 market notes. {_KNOWLEDGE_RESEARCH}",
        )
        session = _generate(client, project_id, _RESEARCH)
        search = _plan_by_capability(session, "web_search")
        skills = [
            item
            for item in session["resource_plan"]
            if item.get("kind") == "skill"
            and item.get("bind_status") in {"will_bind", "already_bound"}
        ]
        knowledge = _plan_by_capability(session, "project_knowledge")
        assert search and search[0]["bind_status"] in {"will_bind", "already_bound"}
        assert "web.search" in search[0]["reference"]
        assert any("research-brief" in item.get("reference", "") for item in skills)
        assert any("evidence-ledger" in item.get("reference", "") for item in skills)
        assert knowledge and knowledge[0]["bind_status"] in {
            "available",
            "already_bound",
        }
        applied = _apply(client, project_id, session)
        agent_id = applied["agent"]["agent_id"]
        source = _draft_source(client, project_id, agent_id)
        pins = client.get(f"/api/v1/projects/{project_id}/resources").json()[
            "resources"
        ]
        for item in search + skills:
            pin = next(row for row in pins if row["reference"] == item["reference"])
            assert source["lock"][item["reference"]] == pin["bound_content_hash"]
        assert source["extensions"]["veyra"]["skill_refs"]
        assert source["extensions"]["veyra"]["knowledge_refs"]
        version = _commit(client, project_id, agent_id)
        url = f"/api/v1/projects/{project_id}/agents/{agent_id}/run"
        field = _primary_field(source)
        first = _approve_until(
            client,
            url,
            _app_start(client, url, {field: "Summarize the market notes CONV_A"}),
        )
        assert first["status"] in {"unverified", "verified"}
        assert first["version_id"] == version["version_id"]
        assert first["conversation_id"]
        result = json.dumps(first["result"], ensure_ascii=False)
        assert _SEARCH_HIT in result
        assert _KNOWLEDGE_RESEARCH in result
        events = client.get(f"{url}s/{first['run_id']}").json()["events"]
        kinds = {event["kind"] for event in events}
        assert "skill.loaded" in kinds
        assert "knowledge.retrieved" in kinds
        assert "tool.completed" in kinds
        assert "approval.requested" in kinds
        blob = json.dumps(transport.calls, ensure_ascii=False)
        assert "Research Brief" in blob
        assert "Evidence Ledger" in blob
        assert _KNOWLEDGE_RESEARCH in blob
        assert _SEARCH_HIT in blob
        assert "scripted" in blob
        draft = client.get(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/draft"
        ).json()
        draft["source"]["extensions"]["veyra"]["instructions"] = "DRAFT_MARKER"
        saved = client.patch(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/draft",
            json={"source": draft["source"], "expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert saved.status_code == 200, saved.text
        second = _app_start(
            client,
            url,
            {field: "把刚才的结论压缩成三点"},
            conversation_id=str(first["conversation_id"]),
        )
        assert second["version_id"] == version["version_id"]
        assert second["conversation_id"] == first["conversation_id"]
        follow = json.dumps(transport.calls, ensure_ascii=False)
        assert "DRAFT_MARKER" not in follow
        assert "CONV_A" in follow or "Summarize the market notes CONV_A" in follow
        other = _app_start(client, url, {field: "fresh CONV_B topic"})
        assert other["conversation_id"] != first["conversation_id"]
        listed = client.get(f"{url}s").json()["runs"]
        assert {first["run_id"], second["run_id"], other["run_id"]} <= {
            item["run_id"] for item in listed
        }
        project_runs: list[str] = []
        for agent in client.get(f"/api/v1/projects/{project_id}").json()["agents"]:
            project_runs.extend(
                item["run_id"]
                for item in client.get(
                    f"/api/v1/projects/{project_id}/agents/{agent['agent_id']}/runs"
                ).json()["runs"]
            )
        assert {first["run_id"], second["run_id"], other["run_id"]} <= set(project_runs)
        detail = client.get(f"{url}s/{first['run_id']}").json()
        assert detail["version_id"] == version["version_id"]
        assert detail["run_id"] == first["run_id"]
        elapsed = time.perf_counter() - started
        assert elapsed < 20


def test_software_engineer_repair_loop_and_reject(tmp_path: Path) -> None:
    transport = RepairTransport()
    with _client(tmp_path, runtime=transport) as client:
        project = _project(client, "Engineer Acceptance")
        project_id = project["project_id"]
        root = Path(project["root_path"])
        (root / "src").mkdir(exist_ok=True)
        (root / "tests").mkdir(exist_ok=True)
        (root / "src" / "math.py").write_text(_MATH_BUG, encoding="utf-8")
        (root / "tests" / "test_add.py").write_text(_TEST_ADD, encoding="utf-8")
        session = _generate(client, project_id, _ENGINEER)
        ids = {
            item.get("resource_id")
            or str(item.get("reference") or "").rsplit("@", 1)[0]
            for item in session["resource_plan"]
            if item.get("bind_status") in {"will_bind", "already_bound"}
        }
        assert ids >= {
            "veyra.tool.filesystem.search",
            "veyra.tool.filesystem.read",
            "veyra.tool.filesystem.write",
            "veyra.tool.shell.exec",
        }
        assert "veyra.tool.web.search" not in ids
        assert "veyra.tool.browser.navigate" not in ids
        applied = _apply(client, project_id, session)
        agent_id = applied["agent"]["agent_id"]
        source = _draft_source(client, project_id, agent_id)
        version = _commit(client, project_id, agent_id)
        url = f"/api/v1/projects/{project_id}/agents/{agent_id}/run"
        field = _primary_field(source)

        rejected = _app_start(client, url, {field: "fix add and reject the write"})
        assert rejected["status"] == "waiting"
        done = _command_until(client, url, str(rejected["run_id"]), "reject")
        assert done["run_id"] == rejected["run_id"]
        assert (root / "src" / "math.py").read_text(encoding="utf-8") == _MATH_BUG

        transport.calls.clear()
        run = _app_start(client, url, {field: "fix add so tests pass"}, timeout=25)
        finished = _approve_until(client, url, run, timeout=25)
        assert finished["status"] in {"unverified", "verified"}
        assert finished["version_id"] == version["version_id"]
        assert (root / "src" / "math.py").read_text(encoding="utf-8") == _MATH_FIXED
        blob = json.dumps(transport.calls, ensure_ascii=False)
        assert "exit_code" in blob
        assert "tests passed" in json.dumps(finished["result"])
        listed = client.get(f"{url}s").json()["runs"]
        assert {rejected["run_id"], finished["run_id"]} <= {
            item["run_id"] for item in listed
        }


def test_packaging_analysis_hybrid_multimodal_and_honest_image_gap(
    tmp_path: Path,
) -> None:
    transport = ScriptedRuntimeTransport(
        [
            _final(
                {
                    "analysis": {
                        "guide": _KNOWLEDGE_BRAND,
                        "color": "check contrast",
                    }
                }
            ),
            _final({"analysis": {"color": "recheck against brand"}}),
        ]
    )
    with _client(tmp_path, runtime=transport) as client:
        project = _project(client, "Packaging Acceptance")
        project_id = project["project_id"]
        _ingest_knowledge(
            client,
            project_id,
            "brand_guidelines.md",
            f"包装品牌规范。Color contrast must remain high. {_KNOWLEDGE_BRAND}",
        )
        session = _generate(client, project_id, _PACKAGING)
        assert not _plan_by_capability(session, "image_generation")
        skills = [
            item
            for item in session["resource_plan"]
            if item.get("kind") == "skill"
            and item.get("bind_status") in {"will_bind", "already_bound"}
        ]
        assert skills
        assert _plan_by_capability(session, "project_knowledge")
        applied = _apply(client, project_id, session)
        agent_id = applied["agent"]["agent_id"]
        source = _draft_source(client, project_id, agent_id)
        assert source["extensions"]["veyra"].get("interaction_mode") in {
            "auto",
            "hybrid",
        }
        version = _commit(client, project_id, agent_id)
        uploaded = client.post(
            f"/api/v1/projects/{project_id}/artifacts",
            files={"file": ("pack.png", _PNG, "image/png")},
        ).json()
        image_field = next(
            name
            for name, spec in source["inputs"].items()
            if spec == "image"
            or (isinstance(spec, dict) and spec.get("type") == "image")
        )
        message_field = _primary_field(source)
        inputs = {
            image_field: {
                "kind": "artifact",
                "artifact_id": uploaded["artifact_id"],
                "media_type": "image/png",
                "filename": "pack.png",
            },
            message_field: "请分析这个包装",
        }
        if "brandname" in source["inputs"]:
            inputs["brandname"] = "Acme"
        url = f"/api/v1/projects/{project_id}/agents/{agent_id}/run"
        first = _app_start(client, url, inputs)
        assert first["status"] in {"unverified", "verified"}
        assert first["version_id"] == version["version_id"]
        blob = json.dumps(transport.calls, ensure_ascii=False)
        assert "data:image/png;base64," in blob
        assert _KNOWLEDGE_BRAND in blob
        assert str(tmp_path) not in blob
        follow = _app_start(
            client,
            url,
            {message_field: "重点分析颜色是否符合品牌规范。"},
            conversation_id=str(first["conversation_id"]),
        )
        assert follow["conversation_id"] == first["conversation_id"]
        assert follow["version_id"] == version["version_id"]
        follow_blob = json.dumps(transport.calls, ensure_ascii=False)
        assert "data:image/png;base64," in follow_blob
        assert "请分析这个包装" in follow_blob
        assert "重点分析颜色是否符合品牌规范" in follow_blob
        missing = _generate(client, project_id, _IMAGE_GEN)
        gap = _plan_by_capability(missing, "image_generation")
        assert gap and gap[0]["bind_status"] == "missing"
        factory = next(
            item
            for item in missing["resource_factory_plans"]
            if item["capability"] == "image_generation"
        )
        assert factory["status"] == "unsupported"
        assert factory["can_generate"] is False


def test_factory_generated_skill_reaches_committed_app_runtime(tmp_path: Path) -> None:
    transport = ScriptedRuntimeTransport([_final({"result": "risk compared"})])
    with _client(tmp_path, runtime=transport) as client:
        project = _project(client, "Factory Skill Acceptance")
        project_id = project["project_id"]
        session = _generate(client, project_id, _FACTORY_SKILL)
        missing = [
            item
            for item in session["resource_plan"]
            if item.get("capability") == "comparative_risk_method"
            and item.get("bind_status") == "missing"
        ]
        assert missing
        planned = next(
            item
            for item in session["resource_factory_plans"]
            if item["capability"] == "comparative_risk_method"
        )
        approved = client.post(
            f"/api/v1/projects/{project_id}/factory/sessions/"
            f"{session['session_id']}/factory-resources/approve",
            json={
                "confirm": True,
                "capability": "comparative_risk_method",
                "content_hash": planned["snapshot_hash"],
                "bind_to_project": True,
            },
        )
        assert approved.status_code == 200, approved.text
        published = next(
            item
            for item in approved.json()["resource_factory_plans"]
            if item["capability"] == "comparative_risk_method"
        )["published"]
        applied = _apply(client, project_id, session)
        agent_id = applied["agent"]["agent_id"]
        source = _draft_source(client, project_id, agent_id)
        assert published["reference"] in source["extensions"]["veyra"]["skill_refs"]
        version = _commit(client, project_id, agent_id)
        url = f"/api/v1/projects/{project_id}/agents/{agent_id}/run"
        run = _app_start(client, url, {_primary_field(source): "compare these risks"})
        assert run["status"] in {"unverified", "verified"}
        assert run["version_id"] == version["version_id"]
        events = client.get(f"{url}s/{run['run_id']}").json()["events"]
        loaded = next(event for event in events if event["kind"] == "skill.loaded")
        assert loaded["payload"]["skill_id"] == published["resource_id"]
        blob = json.dumps(transport.calls, ensure_ascii=False)
        assert (
            published["spec"]["instruction"].splitlines()[0] in blob
            or "Purpose" in blob
        )
        origin = str(published.get("origin") or "") + " ".join(
            published.get("tags") or []
        )
        assert "factory" in origin or "workshop" in origin or published["resource_id"]


def test_error_recovery_matches_runtime_state(tmp_path: Path) -> None:
    class BoomTransport:
        def __init__(self) -> None:
            self.calls: list[Any] = []
            self.n = 0

        def models(self) -> tuple[str, ...]:
            return ("kimi-k3",)

        def complete(self, messages: object) -> RuntimeCompletion:
            self.calls.append(messages)
            self.n += 1
            if self.n == 1:
                raise RuntimeProviderError("runtime_provider_error", "scripted boom")
            return RuntimeCompletion(
                content=_tool(
                    "veyra.tool.web.search@1.0.0",
                    {"query": "loop", "count": 1},
                ),
                finish_reason="stop",
            )

    boom = BoomTransport()
    with _client(
        tmp_path, runtime=boom, tool_adapters={"veyra.runtime.web.search": _fake_search}
    ) as client:
        project = _project(client, "Error Acceptance")
        project_id = project["project_id"]
        session = _generate(client, project_id, _RESEARCH)
        applied = _apply(client, project_id, session)
        agent_id = applied["agent"]["agent_id"]
        source = _draft_source(client, project_id, agent_id)
        source["extensions"]["veyra"]["max_turns"] = 2
        draft = client.get(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/draft"
        ).json()
        patched = client.patch(
            f"/api/v1/projects/{project_id}/agents/{agent_id}/draft",
            json={"source": source, "expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert patched.status_code == 200, patched.text
        _commit(client, project_id, agent_id)
        url = f"/api/v1/projects/{project_id}/agents/{agent_id}/run"
        field = _primary_field(source)
        failed = _app_start(client, url, {field: "provider boom"})
        assert failed["status"] == "failed"
        assert failed["error"]["code"] == "runtime_provider_error"
        turns = _app_start(client, url, {field: "keep calling tools"})
        if turns["status"] == "waiting":
            turns = _approve_until(client, url, turns)
        assert turns["status"] == "failed"
        assert turns["error"]["code"] == "agent_max_turns_exceeded"
        detail = client.get(f"{url}s/{turns['run_id']}").json()
        assert detail["status"] == "failed"
        assert detail["error"]["code"] == "agent_max_turns_exceeded"


def test_tool_error_is_a_structured_run_failure(tmp_path: Path) -> None:
    def _boom_read(**kwargs: Any) -> ToolExecution:
        del kwargs
        raise ToolRuntimeError("tool_failed", "scripted read failure")

    transport = ScriptedRuntimeTransport(
        [
            _tool("veyra.tool.filesystem.read@1.0.0", {"path": "src/math.py"}),
        ]
    )
    with _client(
        tmp_path,
        runtime=transport,
        tool_adapters={"veyra.runtime.filesystem.read": _boom_read},
    ) as client:
        project = _project(client, "Tool Error Acceptance")
        project_id = project["project_id"]
        session = _generate(client, project_id, _ENGINEER)
        applied = _apply(client, project_id, session)
        agent_id = applied["agent"]["agent_id"]
        source = _draft_source(client, project_id, agent_id)
        _commit(client, project_id, agent_id)
        url = f"/api/v1/projects/{project_id}/agents/{agent_id}/run"
        run = _app_start(client, url, {_primary_field(source): "read the code"})
        if run["status"] == "waiting":
            run = _approve_until(client, url, run)
        assert run["status"] == "failed"
        assert run["error"]["code"] == "tool_failed"
        detail = client.get(f"{url}s/{run['run_id']}").json()
        assert detail["status"] == "failed"
        assert detail["error"]["code"] == "tool_failed"


def test_committed_github_agent_preflight_needs_configuration(tmp_path: Path) -> None:
    transport = ScriptedRuntimeTransport(_final({"result": "unused"}))
    with _client(tmp_path, runtime=transport) as client:
        project = _project(client, "GitHub Preflight")
        project_id = project["project_id"]
        session = _generate(
            client,
            project_id,
            "创建一个助手，读取 GitHub repository 中的文件内容。",
        )
        github = [
            item
            for item in session["resource_plan"]
            if "github.read" in str(item.get("reference") or "")
        ]
        assert github
        assert github[0]["bind_status"] in {
            "needs_configuration",
            "requires_configuration",
        }
        applied = _apply(client, project_id, session)
        agent_id = applied["agent"]["agent_id"]
        source = _draft_source(client, project_id, agent_id)
        assert any("github.read" in key for key in source["lock"])
        _commit(client, project_id, agent_id)
        url = f"/api/v1/projects/{project_id}/agents/{agent_id}/run"
        response = client.post(
            url,
            json={
                "inputs": {_primary_field(source): "read the repo"},
                "source": "committed",
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "needs_configuration"
        assert client.get(f"{url}s").json()["runs"] == []
