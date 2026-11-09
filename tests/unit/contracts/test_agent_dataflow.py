from __future__ import annotations

from typing import Any

import pytest

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.contracts.typed_io import (
    parse_typed_field,
    value_matches_field,
)


def _source(
    nodes: list[dict[str, Any]],
    transitions: list[dict[str, str]],
    *,
    outputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "agentspec_version": "26.1",
        "component_type": "Flow",
        "agent_id": "01a03795-a5b0-79ad-aa7d-37a55809ed9b",
        "slug": "revise-loop",
        "name": "Revise loop",
        "description": "Draft, review, revise.",
        "inputs": {"brief": "string"},
        "outputs": outputs or {"design": "object"},
        "nodes": nodes,
        "transitions": transitions,
        "extensions": {
            "veyra": {
                "runtime_profile": "veyra-runtime-profile/1",
                "secret_refs": [],
                "permissions": {"network_hosts": [], "tools": []},
                "verification": {"required": False, "checks": []},
            }
        },
        "ui": {"positions": {}},
        "lock": {"veyra.human.approval@1.0.0": "c" * 64},
    }


def _revise_loop(max_revisions: int | None = 2) -> dict[str, Any]:
    approval: dict[str, Any] = {
        "id": "review",
        "component_type": "HumanApproval",
        "prompt": "Approve this design?",
        "review": "draft.design",
    }
    if max_revisions is not None:
        approval["max_revisions"] = max_revisions
    return _source(
        [
            {"id": "start", "component_type": "Start"},
            {
                "id": "draft",
                "component_type": "Model",
                "model_ref": "model.primary",
                "system_prompt": "Draft a design for {{brief}}.",
                "outputs": {"design": "object"},
            },
            approval,
            {
                "id": "revise",
                "component_type": "Model",
                "model_ref": "model.primary",
                "system_prompt": "Revise using {{review.comment}}.",
                "outputs": {"design": "object"},
            },
            {"id": "output", "component_type": "Output", "output_name": "design"},
        ],
        [
            {"from": "start", "port": "next", "to": "draft"},
            {"from": "draft", "port": "next", "to": "review"},
            {"from": "review", "port": "approved", "to": "output"},
            {"from": "review", "port": "rejected", "to": "revise"},
            {"from": "revise", "port": "next", "to": "review"},
        ],
    )


def test_bounded_revise_loop_through_approval_is_valid_and_roundtrips() -> None:
    source = AgentSource.from_dict(_revise_loop())
    review = next(node for node in source.nodes if node.id == "review")
    assert review.bounded_revisions == 2
    assert review.review == "draft.design"
    wire = source.to_dict()
    draft = next(node for node in wire["nodes"] if node["id"] == "draft")
    assert draft["outputs"] == {"design": "object"}
    assert AgentSource.from_dict(wire).to_dict() == wire


@pytest.mark.parametrize("max_revisions", [None, 0])
def test_unbounded_loop_is_rejected(max_revisions: int | None) -> None:
    with pytest.raises(ContractValidationError, match="max_revisions"):
        AgentSource.from_dict(_revise_loop(max_revisions))


def test_loop_that_skips_the_approval_is_rejected() -> None:
    data = _revise_loop()
    data["nodes"].insert(
        3,
        {
            "id": "polish",
            "component_type": "Model",
            "model_ref": "model.primary",
            "system_prompt": "Polish.",
        },
    )
    data["transitions"] = [
        {"from": "start", "port": "next", "to": "draft"},
        {"from": "draft", "port": "next", "to": "review"},
        {"from": "review", "port": "approved", "to": "output"},
        {"from": "review", "port": "rejected", "to": "revise"},
        {"from": "revise", "port": "next", "to": "polish"},
        {"from": "polish", "port": "next", "to": "revise"},
    ]
    with pytest.raises(ContractValidationError):
        AgentSource.from_dict(data)


def test_node_output_must_match_the_agent_output_type() -> None:
    data = _revise_loop()
    data["nodes"][1]["outputs"] = {"design": "string"}
    with pytest.raises(ContractValidationError, match="design"):
        AgentSource.from_dict(data)


def test_node_output_cannot_shadow_a_node_id() -> None:
    data = _revise_loop()
    data["nodes"][1]["outputs"] = {"design": "object", "review": "string"}
    with pytest.raises(ContractValidationError, match="collides"):
        AgentSource.from_dict(data)


def test_max_revisions_is_bounded() -> None:
    with pytest.raises(ContractValidationError):
        AgentSource.from_dict(_revise_loop(99))


def test_string_enum_constrains_values() -> None:
    field = parse_typed_field(
        {"type": "string", "enum": ["fragile", "standard"]}, "outputs.kind"
    )
    assert value_matches_field(field, "fragile")
    assert not value_matches_field(field, "other")
    assert field.to_wire() == {"type": "string", "enum": ["fragile", "standard"]}
    with pytest.raises(ContractValidationError):
        parse_typed_field({"type": "integer", "enum": ["1"]}, "outputs.count")
