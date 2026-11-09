"""Intermediate verification inspects explicit, already-produced subjects."""

from copy import deepcopy

import pytest

from veyra_agent_platform.contracts.execution_plan import PlanStep
from veyra_agent_platform.local.builder.workflow_bindings import bind_verifier


def _step(*checks: str, input_sources: dict[str, str] | None = None) -> PlanStep:
    return PlanStep.from_dict(
        {
            "id": "verify",
            "kind": "verifier",
            "why": "Check the declared report before permitting the next effect",
            "checks": list(checks),
            "input_sources": input_sources or {},
        },
        "steps[2]",
    )


def test_named_checks_bind_prior_outputs_without_importing_task_inputs() -> None:
    step = _step("required_fields:report_text", "artifact_exists:source-file")
    semantic = {
        "review.report_text": "review_report_text",
        "review.source_file": "review_source_file",
    }
    produced = {
        "report-text": "review_report_text",
        "source-file": "review_source_file",
    }
    task_inputs = {"request": "request", "material": "material"}
    before = deepcopy((semantic, produced, task_inputs))

    mapping, checks = bind_verifier(step, semantic, produced, task_inputs)

    assert mapping == produced
    assert checks == ["required_fields:report-text", "artifact_exists:source-file"]
    assert "request" not in mapping.values()
    assert "material" not in mapping.values()
    assert (semantic, produced, task_inputs) == before


def test_explicit_earlier_stage_and_task_input_bindings_keep_their_roles() -> None:
    step = _step(
        "schema_valid",
        "required_fields:requested-label",
        input_sources={
            "result": "inspect.outcome",
            "requested_label": "inputs.label",
        },
    )

    mapping, checks = bind_verifier(
        step,
        {"inspect.outcome": "inspect_outcome"},
        {"report-text": "review_report_text"},
        {"request": "request", "label": "user_label"},
    )

    assert mapping["result"] == "inspect_outcome"
    assert mapping["requested-label"] == "user_label"
    assert mapping["report-text"] == "review_report_text"
    assert "request" not in mapping.values()
    assert checks == ["schema_valid", "required_fields:requested-label"]


def test_qualified_check_resolves_an_earlier_declared_producer_port() -> None:
    mapping, checks = bind_verifier(
        _step("required_fields:inspect.report_text"),
        {"inspect.report_text": "inspect_report_text"},
        {"summary": "review_summary"},
        {"request": "request"},
    )

    assert mapping["report-text"] == "inspect_report_text"
    assert checks == ["required_fields:report-text"]
    assert "request" not in mapping.values()


def test_default_nonempty_check_requires_a_producer_instead_of_a_request() -> None:
    with pytest.raises(ValueError, match="declared producer outputs"):
        bind_verifier(_step(), {}, {}, {"request": "request"})

    mapping, checks = bind_verifier(
        _step(),
        {"review.report_text": "review_report_text"},
        {"report-text": "review_report_text"},
        {"request": "request"},
    )
    assert mapping == {"report-text": "review_report_text"}
    assert checks == ["output.not_empty"]


@pytest.mark.parametrize(
    "reference",
    ["future.saved_report", "review.unannounced", "input.unannounced"],
)
def test_explicit_unknown_or_future_sources_are_rejected(reference: str) -> None:
    with pytest.raises(ValueError, match="unavailable verifier input source"):
        bind_verifier(
            _step(
                "required_fields:report-text", input_sources={"report_text": reference}
            ),
            {"review.report_text": "review_report_text"},
            {"report-text": "review_report_text"},
            {"request": "request"},
        )


@pytest.mark.parametrize(
    "check",
    [
        "required_fields:future.saved_report",
        "artifact_exists:review.unannounced",
        "required_fields:input.unannounced",
        "required_fields:request",
    ],
)
def test_checks_cannot_silently_target_unavailable_values(check: str) -> None:
    with pytest.raises(ValueError, match="unavailable|undeclared"):
        bind_verifier(
            _step(check),
            {"review.report_text": "review_report_text"},
            {"report-text": "review_report_text"},
            {"request": "request"},
        )


@pytest.mark.parametrize(
    "check", ["looks_good", "output.fake", "json_schema:report-text"]
)
def test_unknown_verifier_checks_fail_instead_of_becoming_noops(check: str) -> None:
    with pytest.raises(ValueError, match="unsupported verifier check"):
        bind_verifier(
            _step(check),
            {"review.report_text": "review_report_text"},
            {"report-text": "review_report_text"},
            {"request": "request"},
        )


def test_schema_check_requires_a_declared_result_subject() -> None:
    with pytest.raises(ValueError, match="declared verifier result input"):
        bind_verifier(
            _step("schema_valid"),
            {"review.outcome": "review_outcome"},
            {"outcome": "review_outcome"},
            {"request": "request", "result": "user_result"},
        )


def test_same_named_producers_need_explicit_disambiguation() -> None:
    semantic = {
        "inspect.report_text": "inspect_report_text",
        "review.report_text": "review_report_text",
    }
    previous = {"report-text": "review_report_text"}
    with pytest.raises(ValueError, match="ambiguous verifier check"):
        bind_verifier(
            _step("required_fields:inspect.report_text"), semantic, previous, {}
        )

    mapping, checks = bind_verifier(
        _step(
            "required_fields:inspect.report_text",
            input_sources={"report_text": "inspect.report_text"},
        ),
        semantic,
        previous,
        {},
    )
    assert mapping == {"report-text": "inspect_report_text"}
    assert checks == ["required_fields:report-text"]


def test_nested_predicate_uses_the_same_value_path_contract_as_runtime() -> None:
    mapping, checks = bind_verifier(
        _step("constraint_match:outcome.checked == true"),
        {"review.outcome": "review_outcome"},
        {"outcome": "review_outcome"},
        {},
    )
    assert mapping == {"outcome": "review_outcome"}
    assert checks == ["constraint_match:outcome.checked == true"]
    with pytest.raises(ValueError, match="undeclared verifier condition field"):
        bind_verifier(_step("constraint_match:future.checked == true"), {}, mapping, {})
