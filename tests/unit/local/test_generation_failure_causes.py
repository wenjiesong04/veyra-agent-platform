import pytest

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.local.builder.coverage_review import coverage_gaps
from veyra_agent_platform.local.builder.generation_diagnostics import (
    generation_failure_facts,
    generation_feedback,
)
from veyra_agent_platform.local.builder.product_validation import (
    TASK_UNCERTAINTY_PREFIX,
)


@pytest.mark.parametrize(
    "budget",
    ["planner_repair_budget_exhausted", 'planner_repair_budget_exhausted: {"limit":3}'],
)
def test_concrete_defect_is_visible_even_when_repair_budget_also_ended(budget) -> None:
    facts = generation_failure_facts(
        [
            budget,
            "persistent_state_not_represented",
        ],
        "product_fidelity_invalid",
        "zh",
    )
    assert facts["validation_code"] == "persistent_state_not_represented"
    assert "状态" in facts["validation_summary"]
    assert "budget" not in facts["validation_summary"]


def test_unknown_model_text_is_not_promoted_to_a_trusted_public_cause() -> None:
    assert (
        generation_failure_facts(
            ["secret model payload", "bearer private"], "product_fidelity_invalid", "en"
        )
        == {}
    )


@pytest.mark.parametrize(
    ("locale", "label"),
    [("zh", "方案待解决项："), ("en", "Unresolved plan item: ")],
)
def test_validator_uncertainty_exposes_plan_detail_without_coverage_stage(
    locale, label
) -> None:
    detail = "The plan assumes uploaded original filenames are unavailable."
    issues = [
        "task_requires_clarification",
        TASK_UNCERTAINTY_PREFIX + detail,
        "planner_repair_budget_exhausted",
    ]
    facts = generation_failure_facts(
        issues, "product_fidelity_invalid", locale, legacy_review_only=True
    )
    assert facts == {
        "validation_code": "task_requires_clarification",
        "validation_summary": label + detail,
        "blocked_reason": "product_fidelity_invalid",
    }
    assert generation_feedback(issues, legacy_review_only=True) == []


@pytest.mark.parametrize(
    "detail",
    [TASK_UNCERTAINTY_PREFIX, TASK_UNCERTAINTY_PREFIX + " \n", "Untrusted: detail"],
)
def test_missing_or_unprefixed_uncertainty_keeps_the_existing_summary(detail) -> None:
    facts = generation_failure_facts(
        ["task_requires_clarification", detail], "product_fidelity_invalid", "en"
    )
    assert facts["validation_summary"] == (
        "A requirement or capability gap needs clarification before execution."
    )
    assert "stage" not in facts


def test_orphan_validator_uncertainty_is_not_a_public_cause_or_legacy_gap() -> None:
    issues = [TASK_UNCERTAINTY_PREFIX + "An unresolved item"]
    assert (
        generation_failure_facts(
            issues, "product_fidelity_invalid", "en", legacy_review_only=True
        )
        == {}
    )


def test_validator_uncertainty_redacts_before_limiting_public_detail() -> None:
    detail = "x" * 980 + "Bearer " + "private" * 300 + " tail"
    facts = generation_failure_facts(
        ["task_requires_clarification", TASK_UNCERTAINTY_PREFIX + detail],
        "product_fidelity_invalid",
        "en",
    )
    assert facts["validation_summary"] == (
        "Unresolved plan item: " + "x" * 980 + "<redacted> tail"
    )
    assert "private" not in facts["validation_summary"]

    long_detail = "x" * 1_100 + " sk-private-token"
    facts = generation_failure_facts(
        ["task_requires_clarification", TASK_UNCERTAINTY_PREFIX + long_detail],
        "product_fidelity_invalid",
        "en",
    )
    assert facts["validation_summary"] == "Unresolved plan item: " + "x" * 1_000


def test_coverage_feedback_outranks_the_budget_and_keeps_the_actual_reason() -> None:
    gaps = coverage_gaps(
        {
            "verdict": "incomplete",
            "gaps": [
                {
                    "requirement": "Check and revise",
                    "reason": "No executable repair path",
                }
            ],
        }
    )
    facts = generation_failure_facts(
        ['planner_repair_budget_exhausted: {"limit":1}', *gaps],
        "product_fidelity_invalid",
        "zh",
    )
    assert facts["validation_code"] == "coverage_review_incomplete"
    assert facts["stage"] == "coverage_review"
    assert "No executable repair path" in facts["validation_summary"]
    assert "budget" not in facts["validation_summary"]
    assert generation_feedback(gaps) == ["No executable repair path\nCheck and revise"]


def test_legacy_review_feedback_requires_receipt_provenance_and_redacts_secrets() -> (
    None
):
    issues = [
        'planner_repair_budget_exhausted: {"limit":1}',
        "Requirement: Missing sk-private-token",
    ]
    assert generation_feedback(issues) == []
    assert generation_feedback(issues, legacy_review_only=True) == [
        "Missing <redacted>\nRequirement"
    ]
    assert (
        generation_failure_facts(
            issues, "product_fidelity_invalid", "en", legacy_review_only=True
        )["validation_code"]
        == "coverage_review_incomplete"
    )


@pytest.mark.parametrize(
    "issue",
    [
        "coverage_gap: not-json",
        'coverage_gap: {"requirement":"Check","reason":1}',
        'coverage_gap: {"requirement":"Check","reason":"Missing","raw":"secret"}',
        'coverage_gap: {"requirement":"","reason":"Missing"}',
        "Requirement: ",
        ": Missing",
    ],
)
def test_invalid_or_empty_feedback_is_not_exposed(issue) -> None:
    assert generation_feedback([issue], legacy_review_only=True) == []


@pytest.mark.parametrize("verdict", [[], {}, True, 1, None])
def test_invalid_coverage_verdict_has_a_contract_error_without_model_values(verdict):
    with pytest.raises(ContractValidationError, match="invalid contract"):
        coverage_gaps({"verdict": verdict, "gaps": []})
