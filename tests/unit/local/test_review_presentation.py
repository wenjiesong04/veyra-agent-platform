import json

import pytest

from veyra_agent_platform.local.runtime.finalization import (
    ReviewProtocolError,
    parse_candidate_review,
)

from .test_agent_finalization import _final, _Host, _review, _ScriptedLoopModel, _source


@pytest.mark.parametrize("question", [None, "", " ", {"invalid": "presentation"}])
def test_missing_question_uses_actual_public_findings_without_changing_outcome(
    question,
):
    value = _review("needs_input")
    value["question"] = question
    review = parse_candidate_review(json.dumps(value), _source().finalization, [])
    assert review.status == "needs_input"
    assert review.findings == tuple(value["findings"])
    assert value["findings"][0]["reason"] in review.question
    assert value["findings"][0]["evidence"] in review.question
    assert review.question_source == "findings"
    assert review.observation()["independent_verification"] is False


def test_missing_question_pauses_same_run_without_a_format_retry(tmp_path):
    value = _review("needs_input")
    value.pop("question")
    host = _Host(tmp_path)
    model = _ScriptedLoopModel(_final({"design": "candidate"}), value)
    outcome = host._execute_loop("project", "run", _source(), {}, model)
    assert outcome.pause is not None and outcome.result is None
    assert len(model.calls) == 2 and host.rendered == []
    assert value["findings"][0]["reason"] in outcome.pause.prompt
    assert outcome.pause.details["context"]["question_source"] == "findings"


def test_semantic_contradiction_remains_blocked_with_durable_public_diagnostics():
    value = _review("pass")
    value["status"] = "revise"
    with pytest.raises(ReviewProtocolError) as caught:
        parse_candidate_review(json.dumps(value), _source().finalization, [])
    assert caught.value.diagnostic["category"] == "aggregate_status"
    assert caught.value.diagnostic["location"] == "/status"
    assert caught.value.diagnostic["valid_findings"] == value["findings"]


def test_unknown_metadata_is_discarded_without_granting_effects_or_leaking_text(
    tmp_path,
):
    value = {**_review("pass"), "analysis": "PRIVATE HIDDEN TEXT", "tool": "write_file"}
    value["findings"][0]["analysis"] = "PRIVATE NESTED TEXT"
    review = parse_candidate_review(json.dumps(value), _source().finalization, [])
    assert "PRIVATE" not in json.dumps(review.observation())
    assert "tool" not in review.observation()
    host = _Host(tmp_path)
    model = _ScriptedLoopModel(_final({"design": "candidate"}), value)
    outcome = host._execute_loop("project", "run", _source(), {}, model)
    assert outcome.result == {"result": {"design": "candidate"}}
    assert not outcome.tool_calls and not host.rendered and len(model.calls) == 2


def test_ignored_metadata_does_not_hide_a_semantic_failure_or_enter_diagnostics():
    value = {**_review("pass"), "analysis": "PRIVATE HIDDEN TEXT", "tool": "write_file"}
    value["findings"][0].update(status="revise", analysis="PRIVATE NESTED TEXT")
    with pytest.raises(ReviewProtocolError) as caught:
        parse_candidate_review(json.dumps(value), _source().finalization, [])
    assert caught.value.diagnostic["category"] == "aggregate_status"
    assert "PRIVATE" not in json.dumps(caught.value.diagnostic)


def test_incomplete_coverage_identifies_missing_checks_without_a_false_pass():
    value = _review("pass")
    value["findings"] = []
    with pytest.raises(ReviewProtocolError) as caught:
        parse_candidate_review(json.dumps(value), _source().finalization, [])
    assert caught.value.diagnostic["missing_criteria"] == [0]
    assert caught.value.diagnostic["expected_count"] == 1
    assert caught.value.diagnostic["received_count"] == 0
