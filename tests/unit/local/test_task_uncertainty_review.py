from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.local.builder.task_uncertainty_review import (
    resolved_uncertainty_indices,
    task_uncertainty_review_schema,
)


@pytest.mark.parametrize("count", [0, 1, 3])
def test_uncertainty_review_schema_is_closed_and_bounded_to_original_items(count):
    schema = task_uncertainty_review_schema(count)
    validator = Draft202012Validator(schema)
    assert schema["required"] == ["resolved"]
    assert schema["additionalProperties"] is False
    items = schema["properties"]["resolved"]["items"]
    assert items["required"] == ["index", "reason"]
    assert items["additionalProperties"] is False
    assert validator.is_valid({"resolved": []})
    assert resolved_uncertainty_indices({"resolved": []}, count) == frozenset()
    assert not validator.is_valid({"resolved": [], "plan": {}})
    assert not validator.is_valid(
        {"resolved": [{"index": count, "reason": "Not an original item"}]}
    )


def test_uncertainty_review_accepts_a_subset_without_mutating_the_response():
    value = {
        "resolved": [
            {"index": 2, "reason": "Third is supported"},
            {"index": 0, "reason": "First is supported"},
        ]
    }
    before = deepcopy(value)
    assert resolved_uncertainty_indices(value, 4) == frozenset({0, 2})
    assert value == before


@pytest.mark.parametrize("index", [-1, 2, True, False, 1.0, "1", None])
def test_uncertainty_review_rejects_non_exact_or_out_of_range_indices(index):
    with pytest.raises(ContractValidationError, match="Task uncertainty review"):
        resolved_uncertainty_indices(
            {"resolved": [{"index": index, "reason": "Claimed support"}]}, 2
        )


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"resolved": {}},
        {"resolved": [], "inputs": []},
        {"resolved": [{"index": 0, "reason": "Supported", "plan": {}}]},
        {"resolved": [{"index": 0}]},
        {"resolved": [{"index": 0, "reason": ""}]},
        {"resolved": [{"index": 0, "reason": " \n"}]},
        {"resolved": [{"index": 0, "reason": 1}]},
        {"resolved": [{"index": 0, "reason": "x" * 401}]},
        {
            "resolved": [
                {"index": 0, "reason": "First claim"},
                {"index": 0, "reason": "Different duplicate claim"},
            ]
        },
        {
            "resolved": [
                {"index": 0, "reason": "Supported"},
                {"index": True, "reason": "Invalid later item"},
            ]
        },
    ],
)
def test_uncertainty_review_rejects_the_entire_invalid_contract(value):
    before = deepcopy(value)
    with pytest.raises(ContractValidationError, match="Task uncertainty review"):
        resolved_uncertainty_indices(value, 2)
    assert value == before
