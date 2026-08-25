from __future__ import annotations

import json
import importlib.util
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "contracts" / "schemas"

from veyra_agent_platform.contracts.wire import EVENT_NODE_ID_REQUIRED, NodeState, RunCommandKind, RunEventKind, RunState


def visit(schema: Any) -> None:
    """Dependency-free guard against accidentally weakening structural schemas."""
    if isinstance(schema, list):
        for item in schema:
            visit(item)
        return
    if not isinstance(schema, dict):
        return
    if schema.get("type") == "object":
        if "properties" in schema:
            assert schema.get("additionalProperties") is False
        elif "additionalProperties" in schema:
            assert schema["additionalProperties"] is not True
    if schema.get("type") == "array":
        assert "items" in schema
    for value in schema.values():
        visit(value)


class SchemaParityTests(unittest.TestCase):
    def test_all_schema_files_are_json_and_closed_at_fixed_object_boundaries(self) -> None:
        for path in sorted(SCHEMAS.glob("*.json")):
            with self.subTest(path=path.name):
                visit(json.loads(path.read_text(encoding="utf-8")))

    def test_agent_schema_mirrors_all_builtin_component_shapes(self) -> None:
        schema = json.loads((SCHEMAS / "agent-source.schema.json").read_text())
        definitions = schema["$defs"]
        self.assertEqual(
            len(definitions["node"]["oneOf"]),
            8,
        )
        self.assertEqual(
            schema["required"],
            ["schema_version", "agentspec_version", "component_type", "agent_id", "slug", "name", "description", "inputs", "outputs", "nodes", "transitions", "extensions", "ui", "lock"],
        )
        self.assertIn("pattern", definitions["uuid7"])
        self.assertEqual(definitions["transition"]["properties"]["port"]["enum"], ["next", "true", "false", "approved", "rejected", "passed", "failed"])
        self.assertEqual(definitions["verification"]["allOf"][0]["then"]["properties"]["checks"]["minItems"], 1)

    def test_handwritten_fixture_components_are_schema_declared(self) -> None:
        schema = json.loads((SCHEMAS / "agent-source.schema.json").read_text())
        declared = {
            reference["$ref"].rsplit("/", 1)[-1]
            for reference in schema["$defs"]["node"]["oneOf"]
        }
        fixture_components: set[str] = set()
        for path in sorted((ROOT / "contracts" / "fixtures" / "valid").glob("*.vagent.yaml")):
            fixture = json.loads(path.read_text(encoding="utf-8"))
            fixture_components.update(node["component_type"] for node in fixture["nodes"])
        expected_definition_names = {
            "start_node", "agent_node", "tool_node", "condition_node",
            "transform_node", "approval_node", "verifier_node", "output_node",
        }
        self.assertEqual(declared, expected_definition_names)
        self.assertEqual(fixture_components, {"Start", "Agent", "Tool", "Condition", "Transform", "HumanApproval", "Verifier", "Output"})

    def test_project_and_wire_schema_cover_identity_and_wire_kinds(self) -> None:
        project = json.loads((SCHEMAS / "project.vproject.schema.json").read_text())
        self.assertIn("default_agent_id", project["required"])
        self.assertIn("resource_policy", project["required"])
        agent = project["properties"]["agents"]["items"]
        self.assertEqual(agent["required"], ["agent_id", "slug", "path"])
        self.assertEqual(agent["properties"]["path"]["pattern"], "^agents/[a-z][a-z0-9-]{0,62}$")
        wire = json.loads((SCHEMAS / "runtime-wire.schema.json").read_text())
        event_kinds = wire["$defs"]["run_event"]["properties"]["kind"]["enum"]
        command_kinds = wire["$defs"]["run_command"]["properties"]["kind"]["enum"]
        self.assertEqual(event_kinds, [kind.value for kind in RunEventKind])
        self.assertEqual(command_kinds, [kind.value for kind in RunCommandKind])
        self.assertEqual(wire["$defs"]["run_state"]["enum"], [state.value for state in RunState])
        self.assertEqual(wire["$defs"]["node_state"]["enum"], [state.value for state in NodeState])
        self.assertEqual(len(wire["$defs"]["run_event"]["allOf"]), 4)
        self.assertEqual(len(wire["$defs"]["run_command"]["allOf"]), 2)
        self.assertIn("timestamp", wire["$defs"]["run_event"]["required"])
        self.assertEqual(wire["$defs"]["run_event"]["properties"]["timestamp"]["pattern"], "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d{1,6})?Z$")
        event_conditions = wire["$defs"]["run_event"]["allOf"]
        schema_run_events = set(event_conditions[0]["if"]["properties"]["kind"]["enum"])
        schema_node_events = set(event_conditions[1]["if"]["properties"]["kind"]["enum"])
        self.assertEqual(schema_run_events, {kind.value for kind, required in EVENT_NODE_ID_REQUIRED.items() if not required})
        self.assertEqual(schema_node_events, {kind.value for kind, required in EVENT_NODE_ID_REQUIRED.items() if required})
        self.assertEqual(wire["$defs"]["run_state_change_payload"]["additionalProperties"], False)
        self.assertEqual(wire["$defs"]["node_state_change_payload"]["additionalProperties"], False)
        self.assertEqual(project["properties"]["resource_policy"]["additionalProperties"], False)

    @unittest.skipUnless(importlib.util.find_spec("jsonschema"), "jsonschema is installed by the runtime integration")
    def test_jsonschema_rejects_unknown_or_extra_state_change_payload_fields(self) -> None:
        import jsonschema

        schema = json.loads((SCHEMAS / "runtime-wire.schema.json").read_text())
        valid = {
            "schema_version": "1.0", "event_id": "01a03795-a5b0-7b1c-bad0-e07ac7dda22b",
            "run_id": "01a03795-a5b0-72d3-8204-6f66a60073db", "timestamp": "2026-08-25T00:00:00Z", "sequence": 1,
            "kind": "run.state_changed", "node_id": None,
            "payload": {"previous_state": "created", "state": "running"},
        }
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(valid)
        for payload in ({"previous_state": "created", "state": "banana"}, {"previous_state": "created", "state": "running", "extra": "no"}):
            invalid = dict(valid)
            invalid["payload"] = payload
            with self.subTest(payload=payload), self.assertRaises(jsonschema.ValidationError):
                validator.validate(invalid)
