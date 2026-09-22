from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from typing import Any

from veyra_agent_platform.contracts.agent import AgentBlueprint
from veyra_agent_platform.contracts.common import ContractValidationError

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "contracts" / "schemas" / "agent-blueprint.schema.json"
FIXTURES = ROOT / "contracts" / "fixtures" / "schema_parity"


def _references(value: Any) -> list[str]:
    if isinstance(value, dict):
        nested = [
            reference for item in value.values() for reference in _references(item)
        ]
        return ([value["$ref"]] if "$ref" in value else []) + nested
    if isinstance(value, list):
        return [reference for item in value for reference in _references(item)]
    return []


class BlueprintSchemaParityTests(unittest.TestCase):
    def test_parity_fixtures_match_python_acceptance_boundary(self) -> None:
        valid = json.loads((FIXTURES / "valid-agent-blueprint.json").read_text())
        invalid = json.loads(
            (FIXTURES / "invalid-empty-transform-agent-blueprint.json").read_text()
        )
        self.assertEqual(
            AgentBlueprint.from_dict(valid).goal, "Return the supplied value."
        )
        with self.assertRaises(ContractValidationError):
            AgentBlueprint.from_dict(invalid)

    def test_schema_is_self_contained_and_encodes_required_verification(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text())
        self.assertTrue(
            all(reference.startswith("#/$defs/") for reference in _references(schema))
        )
        self.assertIn("required_capabilities", schema["required"])
        self.assertIn("ui_suggestions", schema["required"])
        verification_condition = schema["$defs"]["verification"]["allOf"][0]
        self.assertEqual(
            verification_condition["then"]["properties"]["checks"]["minItems"], 1
        )

    def test_default_note_manual_position_is_supported_by_python_and_schema(
        self,
    ) -> None:
        payload = json.loads((FIXTURES / "valid-agent-blueprint.json").read_text())
        payload["ui_suggestions"]["notes"] = {
            "note_intro": {
                "x": 0,
                "y": -220,
                "text": "Blueprint note",
                "width": 420,
                "manual_position": False,
            }
        }
        parsed = AgentBlueprint.from_dict(payload)
        self.assertIs(
            parsed.ui_suggestions["notes"]["note_intro"]["manual_position"], False
        )
        schema = json.loads(SCHEMA_PATH.read_text())
        note_schema = schema["$defs"]["ui_suggestions"]["properties"]["notes"]
        self.assertEqual(
            note_schema["additionalProperties"]["properties"]["manual_position"][
                "type"
            ],
            "boolean",
        )

    @unittest.skipUnless(
        importlib.util.find_spec("jsonschema"),
        "jsonschema is installed by the runtime integration",
    )
    def test_jsonschema_runtime_matches_parity_fixtures(self) -> None:
        import jsonschema

        schema = json.loads(SCHEMA_PATH.read_text())
        valid = json.loads((FIXTURES / "valid-agent-blueprint.json").read_text())
        invalid = json.loads(
            (FIXTURES / "invalid-empty-transform-agent-blueprint.json").read_text()
        )
        noted = {
            **valid,
            "ui_suggestions": {
                **valid["ui_suggestions"],
                "notes": {
                    "note_intro": {
                        "x": 0,
                        "y": -220,
                        "text": "Blueprint note",
                        "width": 420,
                        "manual_position": False,
                    }
                },
            },
        }
        jsonschema.Draft202012Validator(schema).validate(valid)
        jsonschema.Draft202012Validator(schema).validate(noted)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(invalid)
