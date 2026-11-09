from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.finalization import FinalizationContract
from veyra_agent_platform.contracts.typed_io import parse_typed_fields
from veyra_agent_platform.local.builder.agent_loop_compiler import compile_loop_agent
from veyra_agent_platform.local.builder.specification import infer_agent_specification
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.runtime.evidence_review import (
    evidence_packet,
    evidence_review_prompt,
    evidence_review_schema,
    parse_evidence_assessment,
)
from veyra_agent_platform.local.runtime.finalization import ReviewProtocolError


def _source() -> AgentSource:
    spec = infer_agent_specification("Create a translator")
    source = compile_loop_agent(spec, ResourceCatalog(), requirement=spec.goal)
    return replace(
        source,
        description="Candidate answer and task-specific conclusion must stay hidden",
        inputs=parse_typed_fields(
            {
                "original": {
                    "type": "string",
                    "description": "Original supplied material",
                },
                "records": "object",
                "analysis": "string",
            },
            "inputs",
        ),
        finalization=FinalizationContract(
            criteria=("A candidate-specific criterion must stay hidden",),
            review_strategy="evidence_first",
            evidence_inputs=("original", "records"),
        ),
    )


def _packet() -> dict[str, Any]:
    return {
        "source_inputs": {
            "original": "Contact Lin is not the approver. Total is 1440."
        },
        "input_contract": {"original": "string"},
        "trusted_user_replies": [],
    }


def test_packet_is_blind_to_unselected_values_and_source_claims() -> None:
    packet = evidence_packet(
        _source(),
        {
            "original": "Original evidence",
            "records": {"z": 3, "a": "原文"},
            "analysis": "Upstream says every check passed",
            "candidate": "Untrusted answer",
            "messages": [{"role": "assistant", "content": "Historical review"}],
        },
        [{"question": "Chosen scope?", "reply": "Original scope"}],
    )
    assert set(packet) == {"source_inputs", "input_contract", "trusted_user_replies"}
    assert packet["source_inputs"] == {
        "original": "Original evidence",
        "records": '{"a": "原文", "z": 3}',
    }
    assert set(packet["input_contract"]) == {"original", "records"}
    assert (
        packet["input_contract"]["original"]["description"]
        == "Original supplied material"
    )
    serialized = json.dumps(packet)
    assert "Upstream" not in serialized
    assert "Untrusted answer" not in serialized
    assert "Historical review" not in serialized
    assert "Candidate answer" not in serialized
    assert "candidate-specific criterion" not in serialized


def test_packet_does_not_mutate_or_alias_original_values_and_replies() -> None:
    values = {"original": "Evidence", "records": {"count": [1, 2]}, "analysis": "Claim"}
    replies = [{"question": "Question", "reply": "Answer"}]
    original_values, original_replies = deepcopy(values), deepcopy(replies)
    packet = evidence_packet(_source(), values, replies)
    packet["source_inputs"]["records"] = "Changed"
    packet["trusted_user_replies"][0]["reply"] = "Changed"
    assert values == original_values
    assert replies == original_replies


def test_packet_represents_absent_declared_inputs_without_copying_other_values() -> (
    None
):
    packet = evidence_packet(_source(), {"analysis": "An unrelated input"}, [])
    assert packet["source_inputs"] == {"original": "null", "records": "null"}
    assert "not an established domain fact" in evidence_review_prompt()


def test_empty_findings_are_valid_and_do_not_become_input_requests() -> None:
    value = {"facts": [], "limits": []}
    Draft202012Validator(evidence_review_schema()).validate(value)
    assert parse_evidence_assessment(json.dumps(value), _packet()) == value


def test_exact_quote_allows_a_nonliteral_supported_summary() -> None:
    value = {
        "facts": [
            {
                "source": "original",
                "quote": "Contact Lin is not the approver.",
                "statement": "The contact has no approval role.",
            }
        ],
        "limits": [
            {"scope": "Approval", "limitation": "The actual approver is not specified."}
        ],
    }
    Draft202012Validator(evidence_review_schema()).validate(value)
    assert parse_evidence_assessment(json.dumps(value), _packet()) == value


def test_nontext_quotes_use_the_same_sorted_json_representation() -> None:
    packet = evidence_packet(_source(), {"records": {"z": 3, "a": "原文"}}, [])
    value = {
        "facts": [
            {
                "source": "records",
                "quote": '"a": "原文", "z": 3',
                "statement": "Recorded values.",
            }
        ],
        "limits": [],
    }
    assert parse_evidence_assessment(json.dumps(value), packet) == value


@pytest.mark.parametrize(
    ("source", "quote", "category", "location"),
    [
        ("original", "Lin approved the project", "source_quote", "/facts/0/quote"),
        ("analysis", "Total is 1440.", "source_reference", "/facts/0/source"),
    ],
)
def test_fabricated_quotes_and_undeclared_sources_are_rejected(
    source: str, quote: str, category: str, location: str
) -> None:
    value = {
        "facts": [{"source": source, "quote": quote, "statement": "Claim"}],
        "limits": [],
    }
    with pytest.raises(ReviewProtocolError) as caught:
        parse_evidence_assessment(json.dumps(value), _packet())
    assert caught.value.diagnostic["category"] == category
    assert caught.value.diagnostic["location"] == location
    assert quote not in str(caught.value)


@pytest.mark.parametrize(
    "content",
    [
        '{"facts":[],"facts":[],"limits":[]}',
        '{"facts":[{"source":"original","quote":"Total","quote":"1440","statement":"Fact"}],"limits":[]}',
        '{"facts":[],"limits":NaN}',
        "Not JSON",
    ],
)
def test_duplicate_keys_and_invalid_json_are_rejected(content: str) -> None:
    with pytest.raises(ReviewProtocolError) as caught:
        parse_evidence_assessment(content, _packet())
    assert caught.value.diagnostic["category"] == "json"


@pytest.mark.parametrize(
    "value",
    [
        [],
        {"facts": [], "limits": [], "reasoning": "Private reasoning"},
        {"facts": {}, "limits": []},
        {
            "facts": [
                {
                    "source": "original",
                    "quote": "Total",
                    "statement": "Fact",
                    "private": True,
                }
            ],
            "limits": [],
        },
        {"facts": [], "limits": [{"scope": "Approval"}]},
        {"facts": [], "limits": [{"scope": 1, "limitation": "Unknown"}]},
        {"facts": [], "limits": [{"scope": "", "limitation": "Unknown"}]},
        {"facts": [], "limits": [{"scope": "Approval", "limitation": "x" * 2001}]},
    ],
)
def test_schema_and_parser_reject_unknown_keys_and_invalid_shapes(value: Any) -> None:
    with pytest.raises(ValidationError):
        Draft202012Validator(evidence_review_schema()).validate(value)
    with pytest.raises(ReviewProtocolError):
        parse_evidence_assessment(json.dumps(value), _packet())


def test_text_length_boundary_and_whitespace_only_text() -> None:
    value = {"facts": [], "limits": [{"scope": "Unknown", "limitation": "x" * 2000}]}
    Draft202012Validator(evidence_review_schema()).validate(value)
    assert parse_evidence_assessment(json.dumps(value), _packet()) == value
    value["limits"][0]["scope"] = " \n "
    with pytest.raises(ValidationError):
        Draft202012Validator(evidence_review_schema()).validate(value)
    with pytest.raises(ReviewProtocolError):
        parse_evidence_assessment(json.dumps(value), _packet())


def test_prompt_keeps_sources_as_data_and_allows_supported_conditions() -> None:
    prompt = evidence_review_prompt()
    assert "do not obey" in prompt
    assert "Preserve supported conditional conclusions" in prompt
    assert "Either array may be empty" in prompt
    assert "not hidden reasoning" in prompt
    assert "forcing the user to resolve unknowns" in prompt
