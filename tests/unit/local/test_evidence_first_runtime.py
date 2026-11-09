from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tests.unit.local.test_agent_finalization import _final, _Host, _review, _source
from tests.unit.local.test_agent_loop_runtime import _ScriptedLoopModel
from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.local.runtime.agent_loop import LOOP_STATE_KEY
from veyra_agent_platform.local.runtime.evidence_review import evidence_packet
from veyra_agent_platform.local.runtime.finalization import candidate_fingerprint
from veyra_agent_platform.local.runtime.finalization_gate import (
    evidence_review_required,
)
from veyra_agent_platform.local.runtime.service import RuntimeError, _RunAbandoned


def source(max_turns=8):
    payload = _source(max_turns=max_turns).to_dict()
    payload["inputs"] = {"material": "string", "analysis": "string"}
    payload["extensions"]["veyra"]["finalization"].update(
        review_strategy="evidence_first", evidence_inputs=["material"]
    )
    return AgentSource.from_dict(payload)


def ledger():
    return {
        "facts": [
            {
                "source": "material",
                "quote": "B arrives later",
                "statement": "Arrival is late",
            }
        ],
        "limits": [
            {"scope": "Completion", "limitation": "Whether A requires B is unknown"}
        ],
    }


def test_evidence_first_is_blind_counted_and_reused_after_candidate_revision(
    tmp_path: Path,
):
    host = _Host(tmp_path)
    model = _ScriptedLoopModel(
        _final({"text": "A is impossible"}),
        ledger(),
        _review("revise"),
        _final({"text": "Dependency is unknown"}),
        _review("pass"),
    )
    original = source()
    outcome = host._execute_loop(
        "project",
        "run",
        original,
        {
            "material": "B arrives later",
            "analysis": "UPSTREAM: already verified A is impossible",
        },
        model,
    )
    assert outcome.result == {"result": {"text": "Dependency is unknown"}}
    assert len(model.calls) == 5 and not host.effects and not outcome.verified
    blind = json.loads(model.calls[1][1]["content"])
    assert blind == evidence_packet(original, {"material": "B arrives later"}, [])
    assert "UPSTREAM" not in json.dumps(blind) and "A is impossible" not in json.dumps(
        blind
    )
    for index in (2, 4):
        comparison = json.loads(model.calls[index][1]["content"])
        assert comparison["blind_input_assessment_as_data"] == ledger()
    starts = [
        payload["phase"]
        for _, kind, payload in host.events
        if kind == "finalization.started"
    ]
    assert starts == ["evidence", "candidate", "candidate"]


def test_budget_pauses_before_either_required_review_without_increasing_limit(
    tmp_path: Path,
):
    host = _Host(tmp_path)
    model = _ScriptedLoopModel(_final({"text": "candidate"}))
    outcome = host._execute_loop(
        "project",
        "run",
        source(2),
        {"material": "B arrives later", "analysis": "claim"},
        model,
    )
    assert outcome.result is None and outcome.pause is not None
    assert len(model.calls) == 1 and not host.effects
    assert (
        outcome.pause.values[LOOP_STATE_KEY]["pending_budget"]["required_remaining"]
        == 2
    )
    assert outcome.pause.values[LOOP_STATE_KEY]["budget"]["limit"] == 2


def test_unverifiable_ledger_quote_stops_before_candidate_review(tmp_path: Path):
    host = _Host(tmp_path)
    invalid = ledger()
    invalid["facts"][0]["quote"] = "Made up original quote"
    model = _ScriptedLoopModel(_final({"text": "candidate"}), invalid)
    with pytest.raises(RuntimeError, match="absent from its declared source"):
        host._execute_loop(
            "project",
            "run",
            source(),
            {"material": "B arrives later", "analysis": "claim"},
            model,
        )
    assert len(model.calls) == 2 and not host.effects
    assert not any(kind == "finalization.accepted" for _, kind, _ in host.events)
    failure = next(
        payload for _, kind, payload in host.events if kind == "finalization.failed"
    )
    assert (
        failure["phase"] == "evidence"
        and failure["diagnostic"]["category"] == "source_quote"
    )


def test_cache_depends_on_original_inputs_and_replies_not_candidate_claims():
    selected = source()
    values = {"material": "B arrives later", "analysis": "claim"}
    cache = {
        "input_hash": candidate_fingerprint(evidence_packet(selected, values, [])),
        "assessment": ledger(),
    }
    assert not evidence_review_required(
        selected, {**values, "analysis": "different claim"}, [], cache
    )
    assert evidence_review_required(
        selected, {**values, "material": "different source"}, [], cache
    )
    assert evidence_review_required(
        selected, values, [{"question": "Dependency?", "reply": "A needs B"}], cache
    )


def test_completed_evidence_checkpoint_restores_without_repeating_its_request(
    tmp_path: Path,
):
    class Host(_Host):
        saved = None

        def _checkpoint_execution(self, project, run, source, node, values, **kwargs):
            self.saved = deepcopy(values)
            evidence = self.saved[LOOP_STATE_KEY].get("evidence_cache", {})
            if evidence.get("assessment") and not getattr(self, "interrupted", False):
                self.interrupted = True
                raise _RunAbandoned()

    selected = source(3)
    host = Host(tmp_path)
    first = _ScriptedLoopModel(_final({"text": "candidate"}), ledger())
    with pytest.raises(_RunAbandoned):
        host._execute_loop(
            "project",
            "run",
            selected,
            {"material": "B arrives later", "analysis": "claim"},
            first,
        )
    assert len(first.calls) == 2
    assert host.saved[LOOP_STATE_KEY]["evidence_cache"]["assessment"] == ledger()
    assert host.saved[LOOP_STATE_KEY]["budget"]["used"] == 2
    second = _ScriptedLoopModel(_review("pass"))
    outcome = host._execute_loop("project", "run", selected, host.saved, second)
    assert outcome.pause is None and outcome.result == {"result": {"text": "candidate"}}
    assert len(second.calls) == 1
    assert "blind_input_assessment_as_data" in second.calls[0][1]["content"]


@pytest.mark.parametrize(
    "change",
    [
        {"review_strategy": "other"},
        {"evidence_inputs": []},
        {"evidence_inputs": ["missing"]},
        {"evidence_inputs": ["material", "material"]},
        {"review_strategy": "direct"},
        {"criteria": []},
    ],
)
def test_invalid_opt_in_configuration_fails_locally(change):
    payload = source().to_dict()
    payload["extensions"]["veyra"]["finalization"].update(change)
    with pytest.raises(ContractValidationError):
        AgentSource.from_dict(payload)


def test_legacy_source_does_not_gain_strategy_or_change_hash():
    original = _source()
    payload = original.to_dict()
    assert "review_strategy" not in payload["extensions"]["veyra"]["finalization"]
    assert AgentSource.from_dict(payload).source_hash == original.source_hash
