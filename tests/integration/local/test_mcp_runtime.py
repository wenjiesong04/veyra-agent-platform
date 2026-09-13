from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.mcp import ScriptedMcpTransport

from .test_runtime_routes import (
    ScriptedRuntimeTransport,
    _await_run,
    _command_until_settled,
    _run_until_settled,
    _source,
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "object",
            "properties": {
                "labels": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["public"]},
                }
            },
            "required": ["labels"],
            "additionalProperties": False,
        }
    },
    "required": ["query"],
    "additionalProperties": False,
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "integer"}},
    "required": ["answer"],
    "additionalProperties": False,
}


class BlockingMcp(ScriptedMcpTransport):
    def __init__(self, answer: object) -> None:
        super().__init__(
            tools=[
                {
                    "name": "lookup",
                    "inputSchema": INPUT_SCHEMA,
                    "outputSchema": OUTPUT_SCHEMA,
                }
            ]
        )
        self.answer = answer
        self.entered = threading.Event()
        self.release = threading.Event()
        self.arguments: list[object] = []

    def call_tool(self, name: str, arguments: object) -> dict[str, object]:
        self.arguments.append(arguments)
        self.entered.set()
        assert self.release.wait(5)
        return {"structuredContent": {"answer": self.answer}}


def _discover(client: TestClient, server: str, *, approve: bool = True) -> dict:
    response = client.post(f"/api/v1/mcp/servers/{server}/discover")
    assert response.status_code == 200, response.text
    tool = response.json()["tools"][0]
    if not approve:
        return tool
    response = client.post(
        f"/api/v1/mcp/servers/{server}/tools/{tool['resource_id']}"
        f"/versions/{tool['version']}/approve"
    )
    assert response.status_code == 200, response.text
    return response.json()["resource"]


def _agent(tool: dict) -> dict:
    source = _source(
        [
            {"id": "start", "component_type": "Start"},
            {"id": "approval", "component_type": "HumanApproval", "prompt": "Lookup?"},
            {
                "id": "lookup",
                "component_type": "Tool",
                "uses": tool["reference"],
                "input_mapping": {"query": "query"},
                "output_mapping": {"result": "lookup_result"},
            },
            {
                "id": "model",
                "component_type": "Agent",
                "model_ref": "model.primary",
                "system_prompt": "Summarize the lookup.",
            },
            {"id": "output", "component_type": "Output", "output_name": "result"},
        ],
        [
            {"from": "start", "port": "next", "to": "approval"},
            {"from": "approval", "port": "approved", "to": "lookup"},
            {"from": "approval", "port": "rejected", "to": "output"},
            {"from": "lookup", "port": "next", "to": "model"},
            {"from": "model", "port": "next", "to": "output"},
        ],
        {"query": "object"},
    )
    source["outputs"] = {"result": "string"}
    source["extensions"]["veyra"]["permissions"] = tool["required_permissions"]
    source["lock"][tool["reference"]] = tool["content_hash"]
    return source


@pytest.mark.parametrize(
    "query",
    [
        {"labels": ["private"]},
        {},
        {"labels": ["public"], "extra": "reject"},
    ],
)
def test_nested_input_failure_never_calls_mcp(tmp_path: Path, query: dict) -> None:
    mcp = BlockingMcp(7)
    model = ScriptedRuntimeTransport("Summary")
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(
        create_app(
            settings, runtime_transport=model, mcp_transport_factory=lambda *_: mcp
        )
    ) as client:
        server = client.post(
            "/api/v1/mcp/servers",
            json={
                "name": "demo",
                "command": "explicit-test-server",
            },
        ).json()["server"]["server_id"]
        source = _agent(_discover(client, server))
        created = client.post("/api/v1/projects", json={"agents": [source]})
        assert created.status_code == 201, created.text
        project = created.json()
        url = (
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{project['agents'][0]['agent_id']}/run"
        )
        waiting = _run_until_settled(client, url, {"query": query})
        failed = _command_until_settled(client, url, waiting["run_id"], "approve")
        assert failed["error"]["code"] == "mcp_input_schema_invalid", failed
        assert not mcp.arguments and not model.calls
        receipt = next(
            e["payload"] for e in failed["events"] if e["kind"] == "tool.failed"
        )
        assert receipt["input_digest"]
        assert receipt["output_digest"] is None
        assert receipt["schema_validation"] == {
            "input": "failed",
            "output": "not_checked",
        }


@pytest.mark.parametrize("answer", [7, "sensitive-invalid-output"])
def test_mcp_result_gates_model_and_started_event_precedes_call_return(
    tmp_path: Path,
    answer: object,
) -> None:
    mcp = BlockingMcp(answer)
    model = ScriptedRuntimeTransport("Summary")
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with TestClient(
        create_app(
            settings, runtime_transport=model, mcp_transport_factory=lambda *_: mcp
        )
    ) as client:
        server = client.post(
            "/api/v1/mcp/servers",
            json={
                "name": "demo",
                "command": "explicit-test-server",
            },
        ).json()["server"]["server_id"]
        tool = _discover(client, server)
        source = _agent(tool)
        created = client.post("/api/v1/projects", json={"agents": [source]})
        assert created.status_code == 201, created.text
        project = created.json()
        url = (
            f"/api/v1/projects/{project['project_id']}/agents/"
            f"{project['agents'][0]['agent_id']}/run"
        )
        waiting = _run_until_settled(client, url, {"query": {"labels": ["public"]}})
        run_id = waiting["run_id"]
        try:
            approved = client.post(
                f"{url}s/{run_id}/commands",
                json={"command": "approve"},
                headers={"Idempotency-Key": new_uuid7()},
            )
            assert approved.status_code == 200, approved.text
            assert mcp.entered.wait(3)
            blocked = client.get(f"{url}s/{run_id}").json()
            kinds = [e["kind"] for e in blocked["events"]]
            assert "tool.started" in kinds and "tool.completed" not in kinds
        finally:
            mcp.release.set()
        result = _await_run(client, url, run_id)
        success = isinstance(answer, int)
        assert result["status"] == ("unverified" if success else "failed"), result
        assert bool(model.calls) is success
        receipt = next(
            e["payload"]
            for e in result["events"]
            if e["kind"] == ("tool.completed" if success else "tool.failed")
        )
        assert receipt["input_digest"] and receipt["output_digest"]
        assert receipt["schema_validation"] == {
            "input": "passed",
            "output": "passed" if success else "failed",
        }
        if not success:
            assert result["error"]["code"] == "mcp_output_schema_invalid"
            assert answer not in json.dumps(result)
        # A changed nested constraint invalidates the previously bound Agent lock.
        mcp.tools[0] = {
            **mcp.tools[0],
            "outputSchema": {
                **OUTPUT_SCHEMA,
                "properties": {"answer": {"enum": [8]}},
            },
        }
        changed = _discover(client, server)
        assert (
            changed["spec"]["schema_contract_hash"]
            != tool["spec"]["schema_contract_hash"]
        )
        original = AgentSource.from_dict(source)
        node = next(n for n in original.nodes if n.id == "lookup")
        decision = client.app.state.runtime.tools.authorize(
            source=original, node=node, values={}
        )
        assert decision.code == "tool_lock_invalid"
        # Unsupported contracts stay unavailable even after enable/approval attempts.
        mcp.tools[0]["outputSchema"] = {"$ref": "https://invalid.example/schema"}
        unsupported = _discover(client, server, approve=False)
        assert unsupported["runtime_status"] == "runtime_not_supported"
        denied = client.post(
            f"/api/v1/mcp/servers/{server}/tools/{tool['resource_id']}"
            f"/versions/{tool['version']}/approve"
        )
        assert denied.status_code == 422
        client.patch(f"/api/v1/mcp/servers/{server}", json={"enabled": True})
        current = client.get(
            f"/api/v1/resources/{tool['resource_id']}/versions/{tool['version']}"
        ).json()
        assert (
            current["availability"] == "unavailable"
            and not current["factory_selectable"]
        )
