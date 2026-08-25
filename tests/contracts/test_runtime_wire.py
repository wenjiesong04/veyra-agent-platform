from __future__ import annotations

import json
import unittest
from pathlib import Path

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.wire import RunCommand, RunEvent

ROOT = Path(__file__).resolve().parents[2]


class RuntimeWireContractTests(unittest.TestCase):
    def test_run_level_event_allows_only_null_node_id(self) -> None:
        data = {
            "schema_version": "1.0", "event_id": "01a03795-a5b0-7b1c-bad0-e07ac7dda22b",
            "run_id": "01a03795-a5b0-72d3-8204-6f66a60073db", "timestamp": "2026-08-25T00:00:00Z", "sequence": 1,
            "kind": "run.started", "node_id": None, "payload": {},
        }
        self.assertEqual(RunEvent.from_dict(data).node_id, None)

    def test_node_level_event_rejects_null_node_id(self) -> None:
        data = json.loads((ROOT / "contracts" / "fixtures" / "invalid" / "node-event-without-node.json").read_text())
        with self.assertRaises(ContractValidationError):
            RunEvent.from_dict(data)

    def test_command_requires_uuidv7_idempotency_and_expected_revision(self) -> None:
        command = RunCommand.from_dict({
            "schema_version": "1.0", "command_id": "01a03795-a5b0-79ad-aa7d-37a55809ed9b",
            "run_id": "01a03795-a5b0-72d3-8204-6f66a60073db", "idempotency_key": "01a03795-a5b0-7769-804d-63d26e20a5fe",
            "kind": "run.cancel", "node_id": None, "expected_revision": 2, "payload": {},
        })
        self.assertEqual(command.expected_revision, 2)

    def test_node_wire_identifier_uses_the_source_node_pattern(self) -> None:
        data = {
            "schema_version": "1.0", "event_id": "01a03795-a5b0-7b1c-bad0-e07ac7dda22b",
            "run_id": "01a03795-a5b0-72d3-8204-6f66a60073db", "timestamp": "2026-08-25T00:00:00Z", "sequence": 1,
            "kind": "node.started", "node_id": "not-a-node-id!", "payload": {},
        }
        with self.assertRaises(ContractValidationError):
            RunEvent.from_dict(data)
        data["timestamp"] = "2026-08-25T00:00:00Z"
        data["payload"] = {"bad": float("nan")}
        with self.assertRaises(ContractValidationError):
            RunEvent.from_dict(data)

    def test_event_requires_utc_timestamp_and_finite_json_payload(self) -> None:
        data = {
            "schema_version": "1.0", "event_id": "01a03795-a5b0-7b1c-bad0-e07ac7dda22b",
            "run_id": "01a03795-a5b0-72d3-8204-6f66a60073db", "timestamp": "2026-08-25T08:00:00+08:00", "sequence": 1,
            "kind": "run.started", "node_id": None, "payload": {},
        }
        with self.assertRaises(ContractValidationError):
            RunEvent.from_dict(data)

    def test_event_payload_is_deeply_frozen_after_parse(self) -> None:
        payload = {"nested": {"items": ["original"]}}
        event = RunEvent.from_dict({
            "schema_version": "1.0", "event_id": "01a03795-a5b0-7b1c-bad0-e07ac7dda22b",
            "run_id": "01a03795-a5b0-72d3-8204-6f66a60073db", "timestamp": "2026-08-25T00:00:00Z", "sequence": 1,
            "kind": "run.started", "node_id": None, "payload": payload,
        })
        payload["nested"]["items"].append("mutated")
        self.assertEqual(event.to_dict()["payload"], {"nested": {"items": ["original"]}})
        with self.assertRaises(TypeError):
            event.payload["new"] = "value"  # type: ignore[index]
