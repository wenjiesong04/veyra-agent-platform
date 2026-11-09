from __future__ import annotations

import json
from pathlib import Path

from veyra_agent_platform.contracts.wire import RunEvent
from veyra_agent_platform.local.resources import ResourceCatalog

from .test_loop_resource_truth import (
    _attach,
    _client,
    _create_project,
    _loop_source,
    _pin,
    _set_io,
)
from .test_runtime_routes import ScriptedRuntimeTransport, _run_until_settled


def _batch(*arguments: object) -> str:
    return json.dumps(
        {
            "action": "tool_batch",
            "calls": [
                {"tool": "veyra.tool.math.calculate@1.0.0", "arguments": item}
                for item in arguments
            ],
        }
    )


def _final() -> str:
    return json.dumps({"action": "final", "outputs": {"result": {"completed": True}}})


def _setup(client):
    tool = ResourceCatalog().detail("veyra.tool.math.calculate", "1.0.0")
    source = _attach(
        _set_io(
            _loop_source("Compute the independent supplied expressions"),
            {"request": "string"},
            {"result": "object"},
        ),
        tool,
    )
    project = _create_project(client, source)
    _pin(client, project["project_id"], tool)
    return (
        f"/api/v1/projects/{project['project_id']}/agents/"
        f"{project['agents'][0]['agent_id']}/run"
    )


def test_three_native_calculations_use_two_model_turns_and_persist_each_receipt(
    tmp_path: Path,
) -> None:
    transport = ScriptedRuntimeTransport(
        [
            _batch(
                {"expression": "6+2+1.5+2+2.5"},
                {"expression": "8+4+3+2.5+1.5"},
                {"expression": "10+6+5+4+3"},
            ),
            _final(),
        ]
    )
    with _client(tmp_path, transport) as client:
        run = _run_until_settled(client, _setup(client), {"request": "Three totals"})
        assert run["status"] == "unverified", run
        assert len(transport.calls) == 2
        observation = json.loads(transport.calls[1][-1]["content"].partition("\n")[2])
        assert [item["output"]["value"] for item in observation["results"]] == [
            14,
            19,
            28,
        ]
        assert [item["status"] for item in observation["results"]] == ["succeeded"] * 3
        receipts = [
            event for event in run["events"] if event["kind"] == "tool.completed"
        ]
        assert [event["payload"]["batch_index"] for event in receipts] == [0, 1, 2]
        assert all(event["payload"]["authorization"] == "allowed" for event in receipts)
        assert len({event["payload"]["input_digest"] for event in receipts}) == 3
        with client.app.state.repository._connect() as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM runtime_tool_calls WHERE run_id=?",
                    (run["run_id"],),
                ).fetchone()[0]
                == 3
            )
        assert '"batch_supported": true' in transport.calls[0][0]["content"]
        for event in run["events"]:
            RunEvent.from_dict(event)


def test_bad_second_input_rejects_the_whole_batch_and_persists_safe_path(
    tmp_path: Path,
) -> None:
    transport = ScriptedRuntimeTransport(
        [
            _batch(
                {"expression": "1+2"},
                {"expression": {"private-value": "private-secret"}},
            ),
            _final(),
        ]
    )
    with _client(tmp_path, transport) as client:
        run = _run_until_settled(
            client, _setup(client), {"request": "Validate before dispatch"}
        )
        assert run["status"] == "unverified", run
        assert not any(event["kind"] == "tool.started" for event in run["events"])
        rejected = next(
            event for event in run["events"] if event["kind"] == "tool.input_rejected"
        )
        assert rejected["payload"]["batch_index"] == 1
        assert rejected["payload"]["effect_started"] is False
        assert (
            rejected["payload"]["diagnostic"]["violations"][0]["location"]
            == "/arguments/expression"
        )
        assert "private" not in json.dumps(rejected)
        feedback = json.loads(transport.calls[1][-1]["content"].partition("\n")[2])
        assert feedback["outcome"] == "rejected" and feedback["effect_started"] is False


def test_failed_pure_calculation_is_an_observation_not_a_success_or_auto_retry(
    tmp_path: Path,
) -> None:
    transport = ScriptedRuntimeTransport(
        [_batch({"expression": "1/0"}, {"expression": "2+3"}), _final()]
    )
    with _client(tmp_path, transport) as client:
        run = _run_until_settled(
            client, _setup(client), {"request": "Report calculation evidence"}
        )
        assert run["status"] == "unverified", run
        assert len(transport.calls) == 2
        observation = json.loads(transport.calls[1][-1]["content"].partition("\n")[2])
        assert [item["status"] for item in observation["results"]] == [
            "failed",
            "succeeded",
        ]
        assert (
            observation["results"][0]["output"]["diagnostic"]["summary"]
            == "Division by zero is not allowed"
        )
        assert observation["results"][1]["output"]["value"] == 5
        failed = next(
            event for event in run["events"] if event["kind"] == "tool.failed"
        )
        assert failed["payload"]["outcome"] == "failed"
        assert (
            failed["payload"]["diagnostic"]["violations"][0]["location"]
            == "/arguments/expression"
        )
        assert sum(event["kind"] == "tool.started" for event in run["events"]) == 2
