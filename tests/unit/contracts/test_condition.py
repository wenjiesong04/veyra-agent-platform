from __future__ import annotations

import pytest

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.condition import (
    ConditionValidationError,
    condition_expression_schema,
    parse_condition_expression,
    parse_condition_predicate,
    parse_value_path,
    resolve_value_path,
)


@pytest.mark.parametrize(
    ("path", "operator", "literal", "actual", "expected"),
    [
        ("confirmation.approved", "==", True, True, True),
        ("assessment.score", ">=", 0.00001, 0.00002, True),
        ("assessment.amount", "<", 1e20, 1e21, False),
        ("inspection.tags", "contains", "需复核", ["需复核"], True),
        ("inspection.summary", "not contains", "失败", "完成", True),
        ("route.category", "!=", 'review "A"\\B', 'review "A"\\B', False),
    ],
)
def test_typed_predicates_compile_to_the_existing_executable_grammar(
    path: str,
    operator: str,
    literal: str | bool | float,
    actual: object,
    expected: bool,
) -> None:
    predicate = {"path": path, "operator": operator, "literal": literal}
    parsed = parse_condition_predicate(predicate)
    legacy = parse_condition_expression(parsed.to_text())
    root, field = path.split(".", 1)
    values = {root: {field: actual}}
    assert parsed.to_predicate() == predicate
    assert legacy.to_predicate() == predicate
    assert legacy.evaluate(values) is expected


def test_predicate_schema_is_closed_and_keeps_legacy_empty_placeholders() -> None:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(condition_expression_schema())
    assert validator.is_valid("")
    assert validator.is_valid('status == "approved"')
    assert validator.is_valid(
        {"path": "choice.approved", "operator": "==", "literal": True}
    )
    assert not validator.is_valid(
        {"path": "choice.approved", "operator": "==", "literal": True, "eval": "code"}
    )
    assert not validator.is_valid(
        {"path": "choice.approved", "operator": "matches", "literal": True}
    )
    assert not validator.is_valid({"path": "choice.approved", "operator": "=="})


@pytest.mark.parametrize(
    ("predicate", "code", "literal_type"),
    [
        (
            {"path": "review[0]", "operator": "==", "literal": "private"},
            "predicate_path_invalid",
            None,
        ),
        (
            {"path": "review.score", "operator": ">", "literal": "private"},
            "ordering_requires_number",
            "string",
        ),
        (
            {"path": "review.score", "operator": "==", "literal": ["private"]},
            "predicate_literal_invalid",
            "array",
        ),
        (
            {"path": "review.score", "operator": "==", "literal": float("inf")},
            "predicate_literal_invalid",
            "number",
        ),
    ],
)
def test_condition_diagnostics_keep_location_and_types_without_literal_values(
    predicate: dict, code: str, literal_type: str | None
) -> None:
    with pytest.raises(ConditionValidationError) as caught:
        parse_condition_predicate(
            predicate, field_name="execution_boundaries[2].expression"
        )
    assert caught.value.details["code"] == code
    assert caught.value.details["location"].startswith(
        "execution_boundaries[2].expression"
    )
    if literal_type:
        assert caught.value.details["literal_type"] == literal_type
    assert "private" not in str(caught.value)
    assert "grammar" in caught.value.details


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
