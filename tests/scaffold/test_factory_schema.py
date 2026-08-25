import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

FIXTURES = Path(__file__).parents[1] / "fixtures" / "factory"


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_factory_schema_executes_draft_2020_12_validation() -> None:
    schema = _load_fixture("agent_blueprint.schema.json")
    valid_fixture = _load_fixture("agent_blueprint.valid.json")
    invalid_fixture = _load_fixture("agent_blueprint.invalid.json")
    validator = Draft202012Validator(schema)

    validator.check_schema(schema)
    assert list(validator.iter_errors(valid_fixture)) == []
    errors = list(validator.iter_errors(invalid_fixture))

    assert errors
    assert any(error.validator == "additionalProperties" for error in errors)
    assert any(error.validator == "enum" for error in errors)
