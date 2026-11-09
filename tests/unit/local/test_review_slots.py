"""The delivery reviewer assesses every declared slot, never inferred passes."""

import json

import pytest
from jsonschema import Draft202012Validator, ValidationError

from veyra_agent_platform.contracts.finalization import FinalizationContract
from veyra_agent_platform.local.runtime.finalization import (
    ReviewProtocolError,
    candidate_review_schema,
    parse_candidate_review,
)


def _policy(required=13, advisory=0):
    return FinalizationContract(
        criteria=tuple(f"Required criterion {index}" for index in range(required)),
        advisory_criteria=tuple(
            f"Advisory criterion {index}" for index in range(advisory)
        ),
    )


def _finding(status="pass"):
    return {
        "status": status,
        "reason": "Public assessment",
        "evidence": "Supplied facts",
    }


def _keyed(policy):
    return {
        "findings": {
            str(index): _finding() for index in range(len(policy.review_criteria))
        },
        "question": "",
        "invalidate_images": [],
    }


@pytest.mark.parametrize("count", [0, 1, 13])
def test_schema_requires_every_dynamic_slot_and_closed_finding_fields(count):
    policy = _policy(count)
    schema = candidate_review_schema(policy, [])
    Draft202012Validator.check_schema(schema)
    slots = schema["properties"]["findings"]
    expected = [str(index) for index in range(count)]
    assert slots["required"] == expected
    assert list(slots["properties"]) == expected
    assert slots["additionalProperties"] is False
    assert "status" not in schema["properties"]
    value = _keyed(policy)
    validator = Draft202012Validator(schema)
    validator.validate(value)
    assert parse_candidate_review(json.dumps(value), policy, []).status == "pass"
    value["findings"][str(count)] = _finding()
    with pytest.raises(ValidationError):
        validator.validate(value)
    if count:
        value = _keyed(policy)
        value["findings"].pop(str(count - 1))
        with pytest.raises(ValidationError):
            validator.validate(value)
        value = _keyed(policy)
        value["findings"]["0"].pop("evidence")
        with pytest.raises(ValidationError):
            validator.validate(value)
        assert slots["properties"]["0"]["additionalProperties"] is False


@pytest.mark.parametrize("keyed", [True, False])
def test_nine_of_thirteen_is_rejected_with_exact_missing_slots_and_no_fabrication(
    keyed,
):
    policy = _policy()
    complete = _keyed(policy)
    value = {**complete, "findings": dict(list(complete["findings"].items())[:9])}
    if not keyed:
        value["findings"] = [
            {"criterion": int(key), **finding}
            for key, finding in value["findings"].items()
        ]
        value["status"] = "pass"
    with pytest.raises(ReviewProtocolError) as caught:
        parse_candidate_review(json.dumps(value), policy, [])
    diagnostic = caught.value.diagnostic
    assert diagnostic["category"] == "coverage"
    assert diagnostic["expected_count"] == 13
    assert diagnostic["received_count"] == 9
    assert diagnostic["missing_criteria"] == [9, 10, 11, 12]
    assert [finding["criterion"] for finding in diagnostic["valid_findings"]] == list(
        range(9)
    )
    assert len(diagnostic["valid_findings"]) == 9


def test_keyed_slots_are_normalized_without_relying_on_json_member_order():
    policy = _policy()
    value = _keyed(policy)
    value["findings"] = dict(reversed(list(value["findings"].items())))
    value["findings"]["12"]["status"] = "revise"
    review = parse_candidate_review(json.dumps(value), policy, [])
    assert review.status == "revise"
    assert sorted(finding["criterion"] for finding in review.findings) == list(
        range(13)
    )
    assert (
        next(row for row in review.findings if row["criterion"] == 12)["status"]
        == "revise"
    )
    assert review.observation()["independent_verification"] is False


def test_server_aggregates_required_findings_without_promoting_advisory_findings():
    policy = _policy(1, 2)
    value = _keyed(policy)
    value["findings"]["1"]["status"] = "needs_input"
    value["findings"]["2"]["status"] = "uncertain"
    review = parse_candidate_review(json.dumps(value), policy, [])
    assert review.status == "pass"
    assert [row["status"] for row in review.findings] == [
        "pass",
        "needs_input",
        "uncertain",
    ]
    value["findings"]["0"]["status"] = "revise"
    value["status"] = "pass"
    assert parse_candidate_review(json.dumps(value), policy, []).status == "revise"


def test_needs_input_has_priority_and_missing_question_uses_only_required_feedback():
    policy = _policy(3, 1)
    value = _keyed(policy)
    for key, status in enumerate(("revise", "uncertain", "needs_input", "needs_input")):
        value["findings"][str(key)]["status"] = status
    value["findings"]["2"].update(
        reason="Owner is absent", evidence="No owner was supplied"
    )
    value["findings"]["3"]["reason"] = "OPTIONAL_FEEDBACK"
    value.pop("question")
    review = parse_candidate_review(json.dumps(value), policy, [])
    assert review.status == "needs_input"
    assert review.question_source == "findings"
    assert "Owner is absent" in review.question
    assert "No owner was supplied" in review.question
    assert "OPTIONAL_FEEDBACK" not in review.question


@pytest.mark.parametrize("slot", ["13", "01"])
def test_unknown_and_noncanonical_slot_names_are_not_treated_as_known_indexes(slot):
    policy = _policy()
    value = _keyed(policy)
    value["findings"][slot] = _finding()
    with pytest.raises(ReviewProtocolError):
        parse_candidate_review(json.dumps(value), policy, [])


@pytest.mark.parametrize("duplicate", ["slot", "field"])
def test_duplicate_json_members_are_rejected_before_normalization(duplicate):
    finding = json.dumps(_finding())
    if duplicate == "slot":
        content = '{"findings":{"0":' + finding + ',"0":' + finding + "}}"
    else:
        content = (
            '{"findings":{"0":{"status":"pass","status":"revise",'
            '"reason":"R","evidence":"E"}}}'
        )
    with pytest.raises(ReviewProtocolError) as caught:
        parse_candidate_review(content, _policy(1), [])
    assert caught.value.diagnostic["category"] == "json"


@pytest.mark.parametrize("slot,index", [("0", 1), ("1", True)])
def test_redundant_criterion_indexes_cannot_conflict_or_coerce_types(slot, index):
    policy = _policy(2)
    value = _keyed(policy)
    value["findings"][slot]["criterion"] = index
    with pytest.raises(ReviewProtocolError):
        parse_candidate_review(json.dumps(value), policy, [])


def test_legacy_arrays_keep_their_required_aggregate_consistency_check():
    policy = _policy(1)
    value = {
        "status": "pass",
        "findings": [{"criterion": 0, **_finding()}],
        "question": "",
        "invalidate_images": [],
    }
    assert parse_candidate_review(json.dumps(value), policy, []).status == "pass"
    value["status"] = "revise"
    with pytest.raises(ReviewProtocolError) as caught:
        parse_candidate_review(json.dumps(value), policy, [])
    assert caught.value.diagnostic["category"] == "aggregate_status"


def test_image_schema_and_parser_allow_only_the_declared_outputs():
    policy = _policy(1)
    value = _keyed(policy)
    value["findings"]["0"]["status"] = "revise"
    value["invalidate_images"] = ["unknown-view"]
    schema = candidate_review_schema(policy, ["front", "side"])
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(value)
    with pytest.raises(ReviewProtocolError) as caught:
        parse_candidate_review(json.dumps(value), policy, ["front", "side"])
    assert caught.value.diagnostic["category"] == "image_scope"
    assert caught.value.diagnostic["declared_image_outputs"] == ["front", "side"]


@pytest.mark.parametrize("phase", ["pre_render", "candidate", "images"])
def test_a_pass_can_invalidate_old_images_only_during_readiness(phase):
    policy = _policy(1)
    value = _keyed(policy)
    value["invalidate_images"] = ["front"]
    if phase == "pre_render":
        review = parse_candidate_review(
            json.dumps(value), policy, ["front"], phase=phase
        )
        assert review.status == "pass"
        assert review.invalidate_images == ("front",)
    else:
        with pytest.raises(ReviewProtocolError) as caught:
            parse_candidate_review(json.dumps(value), policy, ["front"], phase=phase)
        assert caught.value.diagnostic["category"] == "image_scope"


def test_a_text_only_schema_cannot_request_an_image_invalidation():
    policy = _policy(1)
    value = _keyed(policy)
    value["findings"]["0"]["status"] = "revise"
    value["invalidate_images"] = ["invented-image"]
    with pytest.raises(ReviewProtocolError):
        parse_candidate_review(json.dumps(value), policy, [])
    with pytest.raises(ValidationError):
        Draft202012Validator(candidate_review_schema(policy, [])).validate(value)
