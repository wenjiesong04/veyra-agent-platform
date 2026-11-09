"""Explicit continuation reassesses model uncertainty, not user obligations."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tests.integration.local.test_factory_routes import _client, _project
from tests.integration.local.test_factory_task_structure_planner import (
    PlanningTransport,
    _completion,
    _grounded_method_with_executor,
    _payload,
    _planner,
    _receipts,
    _rows,
)
from veyra_agent_platform.local.builder.generate_product import generate_builder_product
from veyra_agent_platform.local.builder.task_planner import plan_task_structure
from veyra_agent_platform.local.builder.task_structure_schema import (
    task_structure_schema,
)
from veyra_agent_platform.local.factory.client import FactoryProviderError


def _draft(payload):
    return {
        key: deepcopy(payload)
        for key in ("first_schema_valid", "latest_schema_valid", "last_semantic_valid")
    }


@pytest.mark.parametrize("drift_latest", [False, True])
def test_explicit_continuation_rechecks_uncertainty_with_current_runtime_contract(
    tmp_path: Path, drift_latest
):
    original = _payload()
    original["uncertainty"] = ["The uploaded file name may not be visible"]
    original["protect_input_files"] = True
    original["protected_input_fields"] = ["orders-csv", "payments-csv"]
    original["filesystem_write_roots"] = ["project/reports"]
    original["inputs"] = [
        {**deepcopy(original["inputs"][0]), "name": name}
        for name in ("orders-csv", "payments-csv")
    ]
    original["actors"][0]["inputs"] = deepcopy(original["inputs"])
    original["stages"][0]["input_sources"] = [
        {"input": name, "source": f"input.{name}"}
        for name in ("orders-csv", "payments-csv")
    ]
    draft = _draft(original)
    if drift_latest:
        latest = deepcopy(original)
        renamed = {"orders-csv": "order_csv", "payments-csv": "payment_csv"}
        for container in [latest, *latest["actors"]]:
            for field in container["inputs"]:
                field["name"] = renamed[field["name"]]
        latest["stages"][0]["input_sources"] = [
            {"input": name, "source": f"input.{name}"} for name in renamed.values()
        ]
        latest["protected_input_fields"] = list(renamed.values())
        latest["uncertainty"] = []
        draft["latest_schema_valid"] = latest
    before = deepcopy(draft)
    transport = PlanningTransport(
        [
            _completion(
                {"resolved": [{"index": 0, "reason": "Filename metadata is native"}]}
            )
        ]
    )
    saved = []
    requirement = "Use both original filenames.\nNever modify uploaded input files."
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        planner = _planner(
            client,
            receipts,
            initial_draft=draft,
            max_requests=1,
            max_repairs=0,
            on_draft=lambda payload, valid: saved.append((deepcopy(payload), valid)),
        )
        result = planner.complete_json(requirement, task_structure_schema())
        assert _rows(receipts)[0]["output_contract"] == "TaskUncertaintyReviewV1"
    assert result["uncertainty"] == []
    assert draft == before
    assert len(transport.calls) == 1
    messages = transport.calls[0][0]
    context = json.loads(messages[1]["content"])
    assert context["requirement"] == requirement
    assert (
        "filename"
        in context["runtime_and_resource_context"]["runtime_contract"]["file_inputs"][
            "metadata_fields"
        ]
    )
    assert result == {**context["retained_task"], "uncertainty": []}
    assert result["protected_input_fields"] == ["orders-csv", "payments-csv"]
    assert result["stages"] == original["stages"]
    assert "TaskUncertaintyReviewV1" in messages[0]["content"]
    assert "Return only TaskStructureV1" not in messages[0]["content"]
    assert "permission grants" in messages[0]["content"]
    assert len(messages) == 2
    assert saved[-2] == (context["retained_task"], True)
    assert saved[-1] == (result, True)


@pytest.mark.parametrize("resumed", [False, True])
def test_genuine_uncertainty_remains_without_an_automatic_second_reassessment(
    tmp_path: Path, resumed
):
    original = _payload()
    original["uncertainty"] = ["The user must choose the target language"]
    transport = PlanningTransport(
        [_completion({"resolved": []} if resumed else original)]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(
            client,
            _receipts(client, _project(client)),
            initial_draft=_draft(original) if resumed else None,
            max_requests=1,
        )
        result = planner.complete_json(
            "Translate the supplied text", task_structure_schema()
        )
    assert result["uncertainty"] == original["uncertainty"]
    assert len(transport.calls) == 1
    assert ("TaskUncertaintyReviewV1" in transport.calls[0][0][0]["content"]) is resumed


def test_continuation_removes_only_identified_items_in_original_order(tmp_path: Path):
    original = _payload()
    original["uncertainty"] = ["First", "Second", "Third", "Fourth"]
    transport = PlanningTransport(
        [
            _completion(
                {
                    "resolved": [
                        {"index": 2, "reason": "Third is supported"},
                        {"index": 0, "reason": "First is supported"},
                    ]
                }
            )
        ]
    )
    with _client(tmp_path, transport) as client:
        planner = _planner(
            client,
            _receipts(client, _project(client)),
            initial_draft=_draft(original),
            max_requests=1,
        )
        result = planner.complete_json(
            "Keep unresolved choices", task_structure_schema()
        )
    reviewed = json.loads(transport.calls[0][0][1]["content"])["retained_task"]
    assert result == {**reviewed, "uncertainty": ["Second", "Fourth"]}


def test_continuation_keeps_selected_skill_and_uses_its_actual_procedure(
    tmp_path: Path,
):
    original = _grounded_method_with_executor()
    original["uncertainty"] = ["Check the selected method"]
    transport = PlanningTransport(
        [
            _completion(
                {"resolved": [{"index": 0, "reason": "The bound method supports it"}]}
            )
        ]
    )
    with _client(tmp_path, transport) as client:
        draft = _draft(original)
        factory = client.app.state.factory
        draft["resource_pins"] = {
            choice["reference"]: factory.catalog.by_reference(choice["reference"])[
                "content_hash"
            ]
            for choice in original["skill_choices"]
        }
        planner = _planner(
            client,
            _receipts(client, _project(client)),
            initial_draft=draft,
            max_requests=1,
            max_repairs=0,
        )
        result = planner.complete_json(
            "Use the selected method", task_structure_schema()
        )
        actual = factory.catalog.by_reference(original["skill_choices"][0]["reference"])
    context = json.loads(transport.calls[0][0][1]["content"])
    assert (
        context["selected_skill_procedures"][0]["instruction"]
        == actual["spec"]["instruction"]
    )
    assert result == {**context["retained_task"], "uncertainty": []}
    assert result["skill_choices"] == original["skill_choices"]
    assert planner.method_groundings == 0
    assert len(transport.calls) == 1


def test_resolved_uncertainty_still_compiles_and_reviews_the_original_requirement(
    tmp_path: Path,
):
    original = _payload()
    original["uncertainty"] = ["Check support for translation"]
    requirement = "Translate supplied text without changing the meaning"
    transport = PlanningTransport(
        [
            _completion(
                {"resolved": [{"index": 0, "reason": "Native model supports text"}]}
            ),
            _completion({"verdict": "covered", "gaps": []}),
        ]
    )
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        planner = _planner(
            client,
            receipts,
            initial_draft=_draft(original),
            max_requests=2,
            max_repairs=0,
        )
        product = generate_builder_product(
            requirement,
            client.app.state.factory.catalog,
            planner_provider=planner,
            planner_repair=planner.repair,
            planner_review=planner.review_product,
        )
        assert product.status == "review", product.diagnostics
        assert product.plan is not None and product.source is not None
        assert requirement in product.source.instructions
        assert [row["output_contract"] for row in _rows(receipts)] == [
            "TaskUncertaintyReviewV1",
            "TaskCoverageV1",
        ]
    coverage_input = json.loads(transport.calls[1][0][1]["content"])
    assert coverage_input["requirement"] == requirement
    assert coverage_input["candidate"]["task_structure"]["uncertainty"] == []
    assert len(transport.calls) == 2


@pytest.mark.parametrize(
    "weaken", ["input_protection", "protected_fields", "write_scope"]
)
def test_uncertainty_reassessment_cannot_weaken_retained_safety(tmp_path: Path, weaken):
    original = _payload()
    original["uncertainty"] = ["Check whether the configured capability supports this"]
    original["protect_input_files"] = True
    original["protected_input_fields"] = ["request"]
    original["filesystem_write_roots"] = ["project/reports"]
    revised = deepcopy(original)
    revised["uncertainty"] = []
    if weaken == "input_protection":
        revised["protect_input_files"] = False
        revised["protected_input_fields"] = []
    elif weaken == "protected_fields":
        revised["protected_input_fields"] = []
    else:
        revised["filesystem_write_roots"] = ["project"]
    transport = PlanningTransport([_completion(revised)])
    with _client(tmp_path, transport) as client:
        planner = _planner(
            client,
            _receipts(client, _project(client)),
            initial_draft=_draft(original),
            max_requests=1,
            max_repairs=0,
        )
        result = plan_task_structure(
            "Translate the supplied text", provider=planner, repair=planner.repair
        )
    assert result.structure is None
    assert len(transport.calls) == 1
    assert planner.repairs == 0


@pytest.mark.parametrize(
    "response",
    [
        '{"resolved":[],"resolved":[{"index":0,"reason":"Supported"}]}',
        '{"resolved":[{"index":0,"index":1,"reason":"Supported"}]}',
        '{"resolved":[{"index":0,"reason":"Supported"},{"index":true,"reason":"Bad"}]}',
    ],
)
def test_invalid_uncertainty_review_never_partially_applies_or_retries(
    tmp_path: Path, response
):
    original = _payload()
    original["uncertainty"] = ["First", "Second"]
    draft = _draft(original)
    before = deepcopy(draft)
    saved = []
    transport = PlanningTransport([_completion(response), _completion(original)])
    with _client(tmp_path, transport) as client:
        planner = _planner(
            client,
            _receipts(client, _project(client)),
            initial_draft=draft,
            max_requests=8,
            max_repairs=3,
            on_draft=lambda payload, valid: saved.append((deepcopy(payload), valid)),
        )
        result = plan_task_structure(
            "Keep the original task", provider=planner, repair=planner.repair
        )
    assert result.structure is None
    assert result.diagnostics[0].startswith("Task uncertainty review")
    assert draft == before
    assert all(
        payload["uncertainty"] == original["uncertainty"] for payload, _ in saved
    )
    assert len(transport.calls) == 1 and len(transport.responses) == 1
    assert planner.repairs == 0


def test_uncertainty_review_provider_rejection_never_retries_another_protocol(
    tmp_path: Path,
):
    original = _payload()
    original["uncertainty"] = ["Check support"]
    rejection = FactoryProviderError(
        "factory_request_invalid",
        "response_format json_schema is not supported",
        details={"rejected_field": "response_format"},
    )
    transport = PlanningTransport([rejection, _completion({"resolved": []})])
    with _client(tmp_path, transport) as client:
        receipts = _receipts(client, _project(client))
        planner = _planner(client, receipts, initial_draft=_draft(original))
        with pytest.raises(FactoryProviderError) as failed:
            planner.complete_json("Retain the original task", task_structure_schema())
        assert failed.value is rejection
        assert len(_rows(receipts)) == 1 and _rows(receipts)[0]["status"] == "failed"
    assert len(transport.calls) == 1 and len(transport.responses) == 1
    assert planner.protocol_fallbacks == 0 and planner.requests == 1


@pytest.mark.parametrize(
    ("prior_issue", "safe_code"),
    [
        (
            "Repair removed the required input-file protection: sk-private-token",
            "input_protection_changed",
        ),
        (
            "Repair removed a protected input field: orders-csv",
            "input_protection_changed",
        ),
        (
            "Skill choice needs a declared actor capability: orders-csv",
            "skill_actor_binding_invalid",
        ),
        ("", "model_request_limit"),
    ],
)
def test_request_budget_keeps_only_the_safe_prior_validator_code(
    tmp_path: Path, prior_issue, safe_code
):
    transport = PlanningTransport([])
    with _client(tmp_path, transport) as client:
        planner = _planner(
            client,
            _receipts(client, _project(client)),
            max_requests=0,
            max_repairs=None,
        )
        planner._schema = task_structure_schema()
        if prior_issue:
            planner._consume_repair(prior_issue)
        with pytest.raises(ValueError) as exhausted:
            planner._request([], "semantic_plan")
    diagnostic = exhausted.value.safe_repair_diagnostic
    assert json.loads(diagnostic.split(": ", 1)[1])["issue"] == safe_code
    assert '"phase": "model_requests"' in diagnostic
    assert "private-token" not in diagnostic and "orders-csv" not in diagnostic
    assert not transport.calls
