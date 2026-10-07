from __future__ import annotations

import json
from pathlib import Path

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.builder.agent_loop_compiler import compile_loop_agent
from veyra_agent_platform.local.builder.specification import infer_agent_specification
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.resources import ResourceCatalog

from .test_runtime_routes import ScriptedRuntimeTransport, _await_run
from .verified_runtime_model import verified_client


def test_agent_asks_and_resumes_same_committed_run_without_approval_bypass(
    tmp_path: Path,
) -> None:
    transport = ScriptedRuntimeTransport(
        [
            json.dumps(
                {
                    "action": "ask_user",
                    "question": "Choose A, B, or C",
                    "context": {"options": ["A", "B", "C"]},
                }
            ),
            json.dumps({"action": "final", "outputs": {"result": {"chosen": "B"}}}),
        ]
    )
    source = compile_loop_agent(
        infer_agent_specification("Create a design assistant"), ResourceCatalog()
    ).to_dict()
    source["inputs"] = {"request": "string"}
    source["outputs"] = {"result": "object"}
    source["nodes"][-1]["output_name"] = "result"
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'db.sqlite3'}",
        project_storage_root=tmp_path / "projects",
    )
    with verified_client(settings, transport) as client:
        created = client.post("/api/v1/projects", json={"agents": [source]}).json()
        pid, aid = created["project_id"], created["agents"][0]["agent_id"]
        url = f"/api/v1/projects/{pid}/agents/{aid}"
        draft = client.get(f"{url}/draft").json()
        committed = client.post(
            f"{url}/commit",
            json={"expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert committed.status_code == 200, committed.text
        version = committed.json()["version_id"]
        started = client.post(
            f"{url}/run",
            json={
                "inputs": {"request": "Create three options and wait for my selection"},
                "source": "committed",
                "version_id": version,
            },
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert started.status_code == 200, started.text
        rid = started.json()["run_id"]
        waiting = _await_run(client, f"{url}/run", rid)
        assert waiting["status"] == "waiting"
        assert waiting["result"] is None
        assert len(transport.calls) == 1
        commands = f"{url}/runs/{rid}/commands"
        for payload in [
            {"command": "approve"},
            {"command": "reply", "inputs": {"reply": ""}},
            {"command": "reply", "inputs": {"reply": 3}},
            {"command": "reply", "inputs": {"reply": "B", "permission": "all"}},
        ]:
            rejected = client.post(
                commands, json=payload, headers={"Idempotency-Key": new_uuid7()}
            )
            assert rejected.status_code >= 400, rejected.text
            assert client.get(f"{url}/runs/{rid}").json()["status"] == "waiting"
        key = new_uuid7()
        accepted = client.post(
            commands,
            json={"command": "reply", "inputs": {"reply": "B"}},
            headers={"Idempotency-Key": key},
        )
        assert accepted.status_code == 200, accepted.text
        finished = _await_run(client, f"{url}/run", rid)
        assert finished["status"] == "unverified", finished
        assert finished["run_id"] == rid and finished["version_id"] == version
        assert finished["result"] == {"result": {"chosen": "B"}}
        assert len(transport.calls) == 2
        messages = transport.calls[-1]
        assert any(message.get("content") == "B" for message in messages)
        repeated = client.post(
            commands,
            json={"command": "reply", "inputs": {"reply": "B"}},
            headers={"Idempotency-Key": key},
        )
        assert repeated.status_code == 200
        assert len(transport.calls) == 2
