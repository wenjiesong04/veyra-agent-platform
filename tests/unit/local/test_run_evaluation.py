from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from veyra_agent_platform.contracts.common import ContractValidationError, new_uuid7
from veyra_agent_platform.contracts.evaluation import EvaluationSpec
from veyra_agent_platform.local.runtime.evaluation import _equal, _same_set


def _spec() -> dict:
    return {
        "version": "1",
        "version_id": new_uuid7(),
        "checks": [
            {
                "id": "total",
                "label": "Exact total",
                "required": True,
                "path": ["result", "amount"],
                "method": "number_equals",
                "expected": "14.50",
                "baseline": {
                    "kind": "fixture",
                    "reference": "independent-answer",
                    "revision": "1",
                },
            }
        ],
    }


@pytest.mark.parametrize(
    "actual,expected,passed",
    [
        (True, 1, False),
        ({"x": True}, {"x": 1}, False),
        (1, 1.0, True),
        ([1, 2], [2, 1], False),
        ("14.50", 14.5, False),
        (None, None, True),
        ({"a": [1, None]}, {"a": [1.0, None]}, True),
    ],
)
def test_exact_json_equality_keeps_boolean_and_string_types(actual, expected, passed):
    assert _equal(actual, expected) is passed


def test_set_comparison_ignores_order_and_duplicates_not_types():
    assert _same_set([{"a": 1}, 2, 2], [2.0, {"a": 1.0}])
    assert not _same_set([True], [1])
    assert not _same_set([1], [1, 2])


@pytest.mark.parametrize(
    "change",
    [
        {"expected": 14.5},
        {"expected": "NaN"},
        {"expected": "Infinity"},
        {"required": 1},
        {"path": []},
        {"path": ["$agent_loop"]},
        {"baseline": {"kind": "trusted", "reference": "x", "revision": "1"}},
        {"method": "python_eval"},
        {"id": " "},
    ],
)
def test_evaluation_contract_rejects_ambiguous_or_nonportable_specs(change):
    value = _spec()
    value["checks"][0].update(change)
    with pytest.raises(ContractValidationError):
        EvaluationSpec.from_dict(value)


def test_evaluation_spec_freezes_baseline_and_keeps_literal_path_segments():
    value = _spec()
    value["checks"][0]["path"] = ["result", "a.b", "$schema", ""]
    original = deepcopy(value)
    parsed = EvaluationSpec.from_dict(value)
    value["checks"][0]["baseline"]["reference"] = "changed"
    assert parsed.to_dict() == original
    with pytest.raises(ContractValidationError):
        EvaluationSpec.from_dict({**original, "checks": original["checks"] * 2})


def test_published_evaluation_schema_matches_all_supported_method_shapes():
    schema = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "contracts/schemas/evaluation-spec.schema.json"
        ).read_text()
    )
    validator = Draft202012Validator(schema)
    for method in (
        "equals",
        "number_equals",
        "set_equals",
        "artifact_integrity",
        "human_review",
    ):
        value = _spec()
        check = value["checks"][0]
        check["method"] = method
        if method == "set_equals":
            check["expected"] = [1, 3]
        elif method in {"artifact_integrity", "human_review"}:
            check.pop("expected")
            check.pop("baseline")
        check["path"] = ["result", "含.点", "$schema", ""]
        assert not list(validator.iter_errors(value))
        assert EvaluationSpec.from_dict(value).to_dict() == value
    value["checks"][0]["expected"] = "not allowed for human review"
    assert list(validator.iter_errors(value))
