"""Intent, planning, and repair share durable admission before any Provider effect."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.integration.local.test_factory_routes import _client, _project
from tests.integration.local.test_factory_task_structure_planner import _receipts, _rows
from veyra_agent_platform.local.builder.generation_budget import (
    GenerationBudgetExceeded,
)
from veyra_agent_platform.local.builder.receipts import HarnessReceiptRecorder


def _reserve(recorder, kind="semantic_plan"):
    return recorder.begin(
        kind=kind,
        harness_mode="plan_task",
        structured_mode="json_object",
        output_contract="TaskStructureV1",
        schema=None,
        messages=recorder.harness.messages(recorder.project_id, "plan_task"),
        history_message_count=0,
    )


def test_two_recorders_share_an_operation_budget_across_invocation_kinds(tmp_path):
    with _client(tmp_path) as client:
        first = _receipts(client, _project(client))
        first.request_limit = 1
        second = HarnessReceiptRecorder(
            first.store,
            first.harness,
            project_id=first.project_id,
            conversation_id=first.conversation_id,
            operation_id=first.operation_id,
            profile=first.profile,
            request_limit=1,
        )
        _reserve(first, "resolve_intent")
        with pytest.raises(GenerationBudgetExceeded):
            _reserve(second, "semantic_plan_repair")
        assert len(_rows(first)) == 1
        assert _rows(first)[0]["invocation_kind"] == "resolve_intent"


def test_parallel_reservations_cannot_exceed_the_single_shared_limit(tmp_path):
    with _client(tmp_path) as client:
        recorder = _receipts(client, _project(client))
        recorder.request_limit = 1

        def reserve(_):
            try:
                return bool(_reserve(recorder))
            except GenerationBudgetExceeded:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sum(pool.map(reserve, range(2))) == 1
        assert len(_rows(recorder)) == 1


def test_elapsed_operation_budget_rejects_before_reserving_a_request(tmp_path):
    with _client(tmp_path) as client:
        recorder = _receipts(client, _project(client))
        recorder.timeout_seconds = 0
        with pytest.raises(GenerationBudgetExceeded):
            _reserve(recorder)
        assert _rows(recorder) == []


def test_initial_planning_context_is_smaller_without_losing_selected_tool_truth(
    tmp_path,
):
    import json

    with _client(tmp_path) as client:
        recorder = _receipts(client, _project(client))
        messages = recorder.harness.messages(recorder.project_id, "plan_task")
        detailed = recorder.harness.context_document(recorder.project_id, "plan_task")
        assert len(messages[1]["content"].encode()) < len(
            json.dumps(detailed, ensure_ascii=False).encode()
        )
        native = next(
            item
            for item in detailed["resources"]
            if item["reference"] == "veyra.tool.tabular.compare@1.2.0"
        )
        assert native["spec"]["output_json_schema"]
        _reserve(recorder)
        assert _rows(recorder)[0]["context_size_bytes"] == len(
            messages[1]["content"].encode()
        )
