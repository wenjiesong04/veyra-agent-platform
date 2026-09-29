from __future__ import annotations

import pytest

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.condition import (
    parse_condition_expression,
    parse_value_path,
    resolve_value_path,
)


def test_condition_contract_parses_supported_literals_and_evaluates() -> None:
    assert parse_condition_expression('status == "approved"').evaluate(
        {"status": "approved"}
    )
    assert parse_condition_expression("approved == true").evaluate({"approved": True})
    assert parse_condition_expression("amount != 100").evaluate({"amount": 99})
    assert parse_condition_expression("amount >= 100").evaluate({"amount": 100})
    assert parse_condition_expression("score < 0.5").evaluate({"score": 0.25})


def test_condition_reads_step_results_by_dotted_path() -> None:
    values = {
        "classify": {"category": "fragile", "tags": ["glass", "gift"]},
        "item-kind": "cup",
    }
    assert parse_condition_expression('classify.category == "fragile"').evaluate(values)
    assert parse_condition_expression('classify.tags contains "glass"').evaluate(values)
    assert parse_condition_expression('item-kind not contains "box"').evaluate(values)
    assert parse_condition_expression('classify.tags.1 == "gift"').evaluate(values)


@pytest.mark.parametrize(
    "expression",
    [
        'contains(message, "good")',
        "status == true or approved == true",
        '__import__("os").system("touch /tmp/bad")',
        'amount > "ten"',
        "Status == 1",
    ],
)
def test_condition_contract_rejects_unbounded_or_unsupported_syntax(
    expression: str,
) -> None:
    with pytest.raises(ContractValidationError):
        parse_condition_expression(expression)


def test_condition_contract_does_not_hide_missing_runtime_fields() -> None:
    with pytest.raises(KeyError):
        parse_condition_expression('status == "approved"').evaluate({})
    with pytest.raises(KeyError):
        parse_condition_expression('draft.kind == "a"').evaluate({"draft": {}})


def test_ordering_on_text_is_an_error_not_a_silent_false() -> None:
    with pytest.raises(ValueError):
        parse_condition_expression("amount > 1").evaluate({"amount": "2"})


def test_value_paths_are_parsed_and_resolved_without_eval() -> None:
    assert parse_value_path("draft.options.0") == ("draft", "options", "0")
    assert (
        resolve_value_path({"draft": {"options": ["a"]}}, ("draft", "options", "0"))
        == "a"
    )
    with pytest.raises(ContractValidationError):
        parse_value_path("draft[0]")
