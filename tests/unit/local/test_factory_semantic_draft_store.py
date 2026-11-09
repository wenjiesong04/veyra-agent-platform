"""Semantic draft persistence preserves independently updated Factory fields."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from veyra_agent_platform.local.factory.store import (
    FactorySessionRepository,
    _specification_record,
)


@pytest.fixture
def store(tmp_path):
    repository = FactorySessionRepository(tmp_path / "factory.sqlite3")
    with repository.transaction() as connection:
        connection.execute(
            """CREATE TABLE factory_sessions(
                session_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                state TEXT NOT NULL, ready INTEGER NOT NULL, next_prompt TEXT NOT NULL,
                resource_plan_json TEXT NOT NULL, blueprint_json TEXT,
                diagnostics_json TEXT NOT NULL, missing_capabilities_json TEXT NOT NULL,
                identity_json TEXT NOT NULL, revision INTEGER NOT NULL,
                semantic_plan_json TEXT, specification_json TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )"""
        )
        repository.create_session(
            connection,
            session_id="session-1",
            project_id="project-1",
            state="generating",
            ready=False,
            next_prompt="Planning",
            resource_plan=[],
            created_at="2026-10-13T00:00:00Z",
        )
        connection.execute(
            "UPDATE factory_sessions SET specification_json = ?, "
            "semantic_plan_json = ? WHERE session_id = ?",
            (
                json.dumps({"status": "blocked", "task_structure": {"goal": "Task"}}),
                json.dumps({"legacy": "AgentSemanticPlanV1"}),
                "session-1",
            ),
        )
    return repository


def test_save_semantic_draft_merges_without_changing_other_fields(store):
    before = dict(store.session("session-1"))
    draft = {"validation": "schema_valid", "payload": {"goal": "Task"}}

    store.save_semantic_draft("session-1", draft)

    after = dict(store.session("session-1"))
    assert json.loads(after["specification_json"]) == {
        "status": "blocked",
        "task_structure": {"goal": "Task"},
        "semantic_draft": draft,
    }
    assert after["revision"] == before["revision"] + 1
    assert after["updated_at"] != before["updated_at"]
    for name in before:
        if name not in {"specification_json", "revision", "updated_at"}:
            assert after[name] == before[name]


def test_repeated_saves_replace_only_the_draft_and_increment_revision(store):
    store.save_semantic_draft("session-1", {"attempt": 1})
    store.save_semantic_draft("session-1", {"attempt": 2})

    saved = store.session("session-1")
    assert saved["revision"] == 2
    specification = json.loads(saved["specification_json"])
    assert specification["semantic_draft"] == {"attempt": 2}
    assert specification["task_structure"] == {"goal": "Task"}


def test_first_draft_initializes_an_empty_specification(store):
    with store.transaction() as connection:
        connection.execute(
            "UPDATE factory_sessions SET specification_json = NULL "
            "WHERE session_id = ?",
            ("session-1",),
        )

    store.save_semantic_draft("session-1", {"validation": "schema_valid"})

    saved = store.session("session-1")
    assert saved["revision"] == 1
    assert json.loads(saved["specification_json"]) == {
        "semantic_draft": {"validation": "schema_valid"}
    }


def test_save_semantic_draft_rejects_missing_session(store):
    with pytest.raises(ValueError, match="unknown Factory session"):
        store.save_semantic_draft("missing", {"validation": "schema_valid"})

    assert store.session("session-1")["revision"] == 0


def test_concurrent_draft_and_specification_update_preserve_both_fields(store):
    start = Barrier(2)
    draft = {"validation": "schema_valid", "payload": {"goal": "Task"}}

    def save_draft():
        start.wait(timeout=5)
        store.save_semantic_draft("session-1", draft)

    def update_other_field():
        start.wait(timeout=5)
        with store.transaction() as connection:
            saved = connection.execute(
                "SELECT specification_json FROM factory_sessions WHERE session_id = ?",
                ("session-1",),
            ).fetchone()
            specification = json.loads(saved["specification_json"])
            specification["factory_wrappers"] = {"writer": "wrapper-1"}
            store.update_session(
                connection,
                "session-1",
                specification=specification,
                updated_at="2026-10-13T00:00:01Z",
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = [executor.submit(save_draft), executor.submit(update_other_field)]
        for task in pending:
            task.result(timeout=10)

    saved = store.session("session-1")
    specification = json.loads(saved["specification_json"])
    assert saved["revision"] == 2
    assert specification["semantic_draft"] == draft
    assert specification["factory_wrappers"] == {"writer": "wrapper-1"}
    assert specification["task_structure"] == {"goal": "Task"}


def test_invalid_draft_does_not_change_the_session(store):
    before = dict(store.session("session-1"))

    with pytest.raises(TypeError):
        store.save_semantic_draft("session-1", {"invalid": object()})

    assert dict(store.session("session-1")) == before


def test_invalid_specification_is_not_overwritten(store):
    with store.transaction() as connection:
        connection.execute(
            "UPDATE factory_sessions SET specification_json = '[]' "
            "WHERE session_id = ?",
            ("session-1",),
        )
    before = dict(store.session("session-1"))

    with pytest.raises(ValueError, match="Factory specification must be an object"):
        store.save_semantic_draft("session-1", {"validation": "schema_valid"})

    assert dict(store.session("session-1")) == before


def test_semantic_draft_is_read_internally_without_public_exposure(store):
    draft = {"latest_schema_valid": {"goal": "Task"}, "stage": "schema_validated"}
    store.save_semantic_draft("session-1", draft)

    saved = store.session("session-1")
    assert _specification_record(saved)["semantic_draft"] == draft
    assert "semantic_draft" not in store.payload(saved, [])


def test_invalid_stored_draft_is_not_returned_as_an_internal_checkpoint(store):
    with store.transaction() as connection:
        connection.execute(
            "UPDATE factory_sessions SET specification_json = ? WHERE session_id = ?",
            (
                json.dumps({"status": "blocked", "semantic_draft": ["invalid"]}),
                "session-1",
            ),
        )

    record = _specification_record(store.session("session-1"))
    assert record["status"] == "blocked"
    assert record["semantic_draft"] is None
