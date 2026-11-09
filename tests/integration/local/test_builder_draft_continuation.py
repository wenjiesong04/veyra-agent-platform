"""Failed Builder creations resume isolated Factory drafts with a fresh budget."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from tests.integration.local.test_builder_conversations import _turn
from tests.integration.local.test_builder_resolution import intent
from tests.integration.local.test_factory_routes import (
    _client,
    _project,
)
from tests.integration.local.test_factory_routes import (
    _completion as _plain_completion,
)
from tests.integration.local.test_factory_task_structure_planner import (
    PlanningTransport,
    _payload,
)
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.builder.harness import canonical_json_hash
from veyra_agent_platform.local.builder.task_structure_schema import (
    task_structure_schema,
)
from veyra_agent_platform.local.factory.client import FactoryProviderError
from veyra_agent_platform.local.factory.task_structure_planner import (
    FactoryTaskStructurePlanner,
)


def _completion(payload):
    return _plain_completion(json.dumps(payload))


@pytest.fixture(autouse=True)
def isolate_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("VEYRA_FACTORY_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("VEYRA_FACTORY_MODEL_ID", raising=False)


def _seed_failed(
    client: Any,
    project_id: str,
    *,
    session_id: str | None = None,
    requirement: str = "Create a translation agent.",
) -> tuple[str, str]:
    store = client.app.state.builder_conversations.store
    conversation_id, operation_id = new_uuid7(), new_uuid7()
    store.commit_user_turn(
        conversation_id=conversation_id,
        project_id=project_id,
        title="Translation draft",
        create_conversation=True,
        operation_id=operation_id,
        kind="create_agent",
        retry_of=None,
        input_payload={
            "content": requirement,
            "requirement_context": requirement,
            "locale": "en",
        },
        message_id=new_uuid7(),
        content=requirement,
        created_at="2026-10-13T00:00:00Z",
    )
    store.update_operation(
        operation_id,
        status="failed",
        updated_at="2026-10-13T00:00:01Z",
        error_code="factory_quota_exhausted",
        factory_session_id=session_id,
    )
    return conversation_id, operation_id


def _saved_session(
    client: Any,
    project_id: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    factory = client.app.state.factory
    requirement = "Create a translation agent."
    payload = deepcopy(payload) if payload is not None else _payload()
    session = factory.create_session(project_id, requirement, interview=False)
    draft = {
        "schema_version": "1.0",
        "requirement_hash": canonical_json_hash({"requirement": requirement}),
        "schema_hash": canonical_json_hash(task_structure_schema()),
        "first_schema_valid": payload,
        "latest_schema_valid": payload,
        "last_semantic_valid": payload,
        "resource_pins": {},
        "stage": "task_validated",
    }
    factory.store.save_semantic_draft(session["session_id"], draft)
    return session


def _operation_receipts(client, project, conversation, operation):
    return client.app.state.builder_conversations.store.receipts(
        project_id=project, conversation_id=conversation, operation_id=operation
    )


@pytest.mark.parametrize("invalid", [False, True])
def test_schema_drift_revalidates_retained_task_without_mutating_history(
    tmp_path, invalid
):
    transport = PlanningTransport([])
    with _client(tmp_path, transport) as client:
        project = _project(client)
        session = _saved_session(client, project)
        factory = client.app.state.factory
        row = factory.store.session(session["session_id"])
        draft = json.loads(row["specification_json"])["semantic_draft"]
        draft["schema_hash"] = canonical_json_hash(
            {"description": "previous annotations"}
        )
        if invalid:
            draft["latest_schema_valid"]["unknown_field"] = "not a compatible schema"
        factory.store.save_semantic_draft(session["session_id"], draft)
        before = dict(factory.store.session(session["session_id"]))
        cloned = factory.clone_generation_draft(project, session["session_id"])
        assert (cloned is None) is invalid
        assert dict(factory.store.session(session["session_id"])) == before
        assert transport.calls == []


def test_revalidated_schema_drift_continues_with_only_coverage(tmp_path):
    transport = PlanningTransport([_completion({"verdict": "covered", "gaps": []})])
    with _client(tmp_path, transport) as client:
        project = _project(client)
        session = _saved_session(client, project)
        factory = client.app.state.factory
        row = factory.store.session(session["session_id"])
        draft = json.loads(row["specification_json"])["semantic_draft"]
        draft["schema_hash"] = canonical_json_hash(
            {"description": "previous annotations"}
        )
        factory.store.save_semantic_draft(session["session_id"], draft)
        conversation, previous = _seed_failed(
            client, project, session_id=session["session_id"]
        )
        response = _turn(
            client,
            project,
            conversation_id=conversation,
            retry_of=previous,
            request_limit=1,
            resume_only=True,
        )
        assert response.status_code == 200, response.text
        operation = response.json()["operations"][-1]
        assert operation["status"] == "waiting", response.json()
        receipts = _operation_receipts(
            client, project, conversation, operation["operation_id"]
        )
        assert [row["output_contract"] for row in receipts] == ["TaskCoverageV1"]
        assert len(transport.calls) == 1


def test_failed_retry_skips_intent_and_initial_plan_but_runs_coverage(tmp_path: Path):
    transport = PlanningTransport(
        [
            _completion(intent(intent="create", create_kind="agent", instruction="")),
            _completion(_payload()),
            FactoryProviderError("factory_quota_exhausted", "Controlled quota failure"),
            _completion({"verdict": "covered", "gaps": []}),
        ]
    )
    with _client(tmp_path, transport) as client:
        project = _project(client)
        first = _turn(client, project, content="Create a translation agent.").json()
        conversation = first["conversation"]["conversation_id"]
        previous = first["operations"][0]
        assert previous["status"] == "failed"
        store = client.app.state.builder_conversations.store
        original_operation = deepcopy(store.operation(previous["operation_id"]))
        factory = client.app.state.factory
        original_session = dict(factory.store.session(previous["factory_session_id"]))
        assert len(transport.calls) == 3

        response = _turn(
            client,
            project,
            conversation_id=conversation,
            retry_of=previous["operation_id"],
            request_limit=1,
            resume_only=True,
        )
        assert response.status_code == 200, response.text
        continued = response.json()
        operation = continued["operations"][-1]
        assert operation["status"] == "waiting", continued
        assert operation["proposal_id"]
        assert operation["operation_id"] != previous["operation_id"]
        assert operation["factory_session_id"] != previous["factory_session_id"]
        assert store.operation(previous["operation_id"]) == original_operation
        assert (
            dict(factory.store.session(previous["factory_session_id"]))
            == original_session
        )
        assert len(transport.calls) == 4
        receipts = _operation_receipts(
            client, project, conversation, operation["operation_id"]
        )
        assert len(receipts) == 1
        assert receipts[0]["output_contract"] == "TaskCoverageV1"
        assert receipts[0]["status"] == "success"
        assert "builder.intent.started" not in {
            event["kind"] for event in operation["events"]
        }
        assert client.app.state.factory.client.settings.generation_max_requests == 8


def test_resume_only_without_draft_fails_without_provider(tmp_path: Path):
    transport = PlanningTransport([])
    with _client(tmp_path, transport) as client:
        project = _project(client)
        conversation, previous = _seed_failed(client, project)
        response = _turn(
            client,
            project,
            conversation_id=conversation,
            retry_of=previous,
            resume_only=True,
        )
        assert response.status_code == 200, response.text
        operation = response.json()["operations"][-1]
        assert operation["status"] == "failed"
        assert operation["error_code"] == "builder_draft_continuation_unavailable"
        assert not transport.calls
        assert not _operation_receipts(
            client, project, conversation, operation["operation_id"]
        )


def test_retry_cannot_clone_a_factory_session_from_another_project(tmp_path: Path):
    transport = PlanningTransport([])
    with _client(tmp_path, transport) as client:
        project, foreign_project = _project(client), _project(client)
        foreign = _saved_session(client, foreign_project)
        conversation, previous = _seed_failed(
            client, project, session_id=foreign["session_id"]
        )
        response = _turn(
            client,
            project,
            conversation_id=conversation,
            retry_of=previous,
            resume_only=True,
        )
        assert response.status_code == 200, response.text
        operation = response.json()["operations"][-1]
        assert operation["status"] == "failed"
        assert operation["error_code"] == "factory_session_not_found"
        assert not transport.calls
        assert operation["proposal_id"] is None


@pytest.mark.parametrize("request_limit", [1, 8])
def test_review_only_reports_gaps_without_attempting_a_repair(
    tmp_path: Path, request_limit: int, monkeypatch: pytest.MonkeyPatch
):
    def unexpected_repair(*args, **kwargs):
        pytest.fail("Review-only continuation must not attempt planning repair")

    monkeypatch.setattr(FactoryTaskStructurePlanner, "repair", unexpected_repair)
    transport = PlanningTransport(
        [
            _completion(
                {
                    "verdict": "incomplete",
                    "gaps": [{"requirement": "Check", "reason": "Missing"}],
                }
            ),
            _completion(_payload()),
        ]
    )
    with _client(tmp_path, transport) as client:
        project = _project(client)
        session = _saved_session(client, project)
        conversation, previous = _seed_failed(
            client, project, session_id=session["session_id"]
        )
        response = _turn(
            client,
            project,
            conversation_id=conversation,
            retry_of=previous,
            request_limit=request_limit,
            resume_only=True,
        )
        assert response.status_code == 200, response.text
        operation = response.json()["operations"][-1]
        assert operation["status"] == "failed"
        assert operation["proposal_id"] is None
        assert (
            operation["diagnostic"]["validation_code"] == "coverage_review_incomplete"
        )
        assert operation["diagnostic"]["stage"] == "coverage_review"
        assert operation["generation_feedback"] == ["Missing\nCheck"]
        assert "budget" not in operation["diagnostic"]["validation_summary"]
        assert len(transport.calls) == 1
        assert len(transport.responses) == 1
        assert (
            len(
                _operation_receipts(
                    client, project, conversation, operation["operation_id"]
                )
            )
            == 1
        )
        assert client.app.state.factory.client.settings.generation_max_requests == 8


@pytest.mark.parametrize(
    "provenance",
    ["verified", "missing", "failed", "wrong_contract", "multiple", "not_review_only"],
)
def test_legacy_coverage_projection_requires_provenance_and_preserves_history(
    tmp_path: Path, provenance: str
):
    transport = PlanningTransport(
        [
            _completion(
                {
                    "verdict": "incomplete",
                    "gaps": [{"requirement": "Check", "reason": "Missing"}],
                }
            )
        ]
    )
    with _client(tmp_path, transport) as client:
        project = _project(client)
        session = _saved_session(client, project)
        conversation, previous = _seed_failed(
            client, project, session_id=session["session_id"]
        )
        snapshot = _turn(
            client,
            project,
            conversation_id=conversation,
            retry_of=previous,
            request_limit=1,
            resume_only=True,
        ).json()
        operation = snapshot["operations"][-1]
        operation_id = operation["operation_id"]
        session_id = operation["factory_session_id"]
        store = client.app.state.builder_conversations.store
        factory = client.app.state.factory
        requirement = "Check every result " + "with evidence " * 20
        reason = "No executable revision path " + "must revise and recheck " * 12
        factory._set_state(
            session_id,
            "ready",
            diagnostics=[
                'planner_repair_budget_exhausted: {"limit":1}',
                f"{requirement}: {reason} sk-private-token",
            ],
        )
        store.update_operation(
            operation_id,
            status="failed",
            updated_at=operation["updated_at"],
            diagnostic={
                "validation_code": "planner_repair_budget_exhausted",
                "validation_summary": "Budget ended",
                "stage": "task_planning",
            },
        )
        receipts = _operation_receipts(client, project, conversation, operation_id)
        if provenance == "multiple":
            receipt = receipts[0]
            store.insert_receipt(
                {
                    **receipt,
                    "receipt_id": new_uuid7(),
                    "sequence": 1,
                    "included_categories": json.loads(
                        receipt["included_categories_json"]
                    ),
                    "excluded_categories": json.loads(
                        receipt["excluded_categories_json"]
                    ),
                }
            )
        elif provenance != "verified":
            payload = json.loads(store.operation(operation_id)["input_json"])
            with client.app.state.repository.transaction() as connection:
                if provenance == "missing":
                    connection.execute(
                        "DELETE FROM builder_harness_receipts WHERE operation_id = ?",
                        (operation_id,),
                    )
                elif provenance == "failed":
                    connection.execute(
                        "UPDATE builder_harness_receipts SET status = 'failed' "
                        "WHERE operation_id = ?",
                        (operation_id,),
                    )
                elif provenance == "wrong_contract":
                    connection.execute(
                        "UPDATE builder_harness_receipts "
                        "SET output_contract = 'TaskStructureV1' "
                        "WHERE operation_id = ?",
                        (operation_id,),
                    )
                else:
                    payload.pop("resume_only")
                    connection.execute(
                        "UPDATE builder_operations SET input_json = ? "
                        "WHERE operation_id = ?",
                        (json.dumps(payload), operation_id),
                    )
        original_operation = deepcopy(store.operation(operation_id))
        original_session = dict(factory.store.session(session_id))
        original_receipts = deepcopy(
            _operation_receipts(client, project, conversation, operation_id)
        )
        response = client.get(
            f"/api/v1/projects/{project}/builder/conversations/{conversation}"
        )
        assert response.status_code == 200, response.text
        projected = response.json()["operations"][-1]
        public_factory = client.get(
            f"/api/v1/projects/{project}/factory/sessions/{session_id}"
        )
        assert public_factory.status_code == 200, public_factory.text
        assert "sk-private-token" not in public_factory.text
        assert public_factory.json()["diagnostics"][1].endswith("<redacted>")
        assert "sk-private-token" not in response.text
        if provenance == "verified":
            assert (
                projected["diagnostic"]["validation_code"]
                == "coverage_review_incomplete"
            )
            assert projected["diagnostic"]["stage"] == "coverage_review"
            assert projected["generation_feedback"] == [
                f"{reason} <redacted>\n{requirement}"
            ]
            assert len(projected["generation_feedback"][0]) > 200
        else:
            assert "generation_feedback" not in projected
            assert (
                projected["diagnostic"]["validation_code"]
                == "planner_repair_budget_exhausted"
            )
        assert store.operation(operation_id) == original_operation
        assert dict(factory.store.session(session_id)) == original_session
        assert (
            _operation_receipts(client, project, conversation, operation_id)
            == original_receipts
        )
        assert len(transport.calls) == 1


def test_continuation_uses_current_shape_instead_of_an_old_pure_preview(tmp_path: Path):
    transport = PlanningTransport([_completion({"verdict": "covered", "gaps": []})])
    payload = _payload()
    payload["stages"].append(
        {
            "id": "verify",
            "summary": "Independently check the translation output",
            "actor": "",
            "source": "Check the completed translation before returning it",
            "input_sources": [],
        }
    )
    payload["execution_boundaries"] = [
        {
            "kind": "verification",
            "stage": "verify",
            "reason": "Check the translation output",
            "checks": ["output.not_empty"],
        }
    ]
    with _client(tmp_path, transport) as client:
        project = _project(client)
        session = _saved_session(client, project, payload=payload)
        client.app.state.factory._set_state(
            session["session_id"],
            "ready",
            specification={
                "status": "blocked",
                "proposal_preview": {"product_shape": {"shape": "PURE_AGENT"}},
            },
        )
        conversation, previous = _seed_failed(
            client, project, session_id=session["session_id"]
        )
        response = _turn(
            client,
            project,
            conversation_id=conversation,
            retry_of=previous,
            request_limit=1,
            resume_only=True,
        )
        assert response.status_code == 200, response.text
        snapshot = response.json()
        assert snapshot["resolution"]["create_kind"] == "workflow"
        assert snapshot["factory_session"]["target_kind"] == "workflow"
        assert snapshot["operations"][-1]["proposal_id"]
        assert len(transport.calls) == 1


def test_retry_without_a_draft_keeps_the_existing_intent_path(tmp_path: Path):
    transport = PlanningTransport(
        [_completion(intent(intent="discuss", instruction=""))]
    )
    with _client(tmp_path, transport) as client:
        project = _project(client)
        conversation, previous = _seed_failed(client, project)
        response = _turn(
            client, project, conversation_id=conversation, retry_of=previous
        )
        assert response.status_code == 200, response.text
        operation = response.json()["operations"][-1]
        assert operation["status"] == "succeeded"
        assert len(transport.calls) == 1
        receipts = _operation_receipts(
            client, project, conversation, operation["operation_id"]
        )
        assert receipts[0]["invocation_kind"] == "resolve_intent"
        stored = client.app.state.builder_conversations.store.operation(
            operation["operation_id"]
        )
        assert "request_limit" not in json.loads(stored["input_json"])
        assert "resume_only" not in json.loads(stored["input_json"])


def test_review_only_does_not_dispatch_a_semantic_repair(tmp_path: Path):
    payload = _payload()
    payload["lifecycle"].update(persistent=True, entity="SavedTask")
    transport = PlanningTransport([])
    with _client(tmp_path, transport) as client:
        project = _project(client)
        session = _saved_session(client, project, payload=payload)
        conversation, previous = _seed_failed(
            client, project, session_id=session["session_id"]
        )
        response = _turn(
            client,
            project,
            conversation_id=conversation,
            retry_of=previous,
            request_limit=1,
            resume_only=True,
        )
        assert response.status_code == 200, response.text
        operation = response.json()["operations"][-1]
        assert operation["status"] == "failed"
        assert not transport.calls
        assert not _operation_receipts(
            client, project, conversation, operation["operation_id"]
        )


def test_edit_retry_cannot_be_changed_into_creation_by_an_old_factory_link(
    tmp_path: Path,
):
    transport = PlanningTransport([])
    with _client(tmp_path, transport) as client:
        project = _project(client)
        session = _saved_session(client, project)
        conversation, previous = _seed_failed(
            client, project, session_id=session["session_id"]
        )
        client.app.state.builder_conversations.store.update_operation(
            previous, kind="edit", status="failed", updated_at="2026-10-13T00:00:02Z"
        )
        response = _turn(
            client,
            project,
            conversation_id=conversation,
            retry_of=previous,
            resume_only=True,
        )
        assert response.status_code == 200, response.text
        operation = response.json()["operations"][-1]
        assert operation["status"] == "failed"
        assert operation["error_code"] == "builder_draft_continuation_unavailable"
        assert not transport.calls


@pytest.mark.parametrize("request_limit", [True, "1", 0, -1, 1.5])
def test_request_limit_rejects_non_strict_positive_integers(tmp_path, request_limit):
    transport = PlanningTransport([])
    with _client(tmp_path, transport) as client:
        project = _project(client)
        response = _turn(
            client, project, content="Create an agent", request_limit=request_limit
        )
        assert response.status_code == 422
        assert not transport.calls


def test_request_limit_cannot_exceed_the_global_maximum(tmp_path: Path):
    transport = PlanningTransport([])
    with _client(tmp_path, transport) as client:
        project = _project(client)
        maximum = client.app.state.factory.client.settings.generation_max_requests
        response = _turn(
            client, project, content="Create an agent", request_limit=maximum + 1
        )
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "builder_request_limit_invalid"
        assert not transport.calls


@pytest.mark.parametrize("controls", [{"resume_only": True}, {"resume_only": 1}])
def test_resume_only_is_strict_and_requires_retry(tmp_path, controls):
    transport = PlanningTransport([])
    with _client(tmp_path, transport) as client:
        project = _project(client)
        response = _turn(client, project, content="Create an agent", **controls)
        assert response.status_code == 422
        assert not transport.calls
