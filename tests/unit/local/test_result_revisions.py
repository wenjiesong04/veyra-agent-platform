import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from veyra_agent_platform.local.runtime.result_revisions import (
    ResultRevisionError,
    revision_base_outputs,
)


def _repository(**base_changes):
    base = {
        "run_id": "base",
        "project_id": "project",
        "agent_id": "agent",
        "version_id": "version",
        "conversation_id": "conversation",
        "status": "unverified",
        "result_json": json.dumps({"result": {"price": 15}}),
    }
    base.update(base_changes)
    current = {**base, "run_id": "current", "status": "running", "result_json": None}
    current.update(
        project_id="project",
        agent_id="agent",
        version_id="version",
        conversation_id="conversation",
    )
    rows = {"base": base, "current": current}
    messages = [
        {"role": "assistant", "run_id": "base", "sequence": 1},
        {"role": "user", "run_id": "current", "sequence": 2},
    ]
    return (
        SimpleNamespace(
            run=rows.get,
            version=lambda _: {"committed": 1},
            run_events=lambda _: [],
            agent_conversation_messages=lambda _: messages,
        ),
        rows,
        messages,
    )


def test_explicit_revision_returns_a_copy_without_mutating_the_previous_run():
    repository, rows, _ = _repository()
    before = deepcopy(rows)
    outputs = revision_base_outputs(repository, "project", "agent", "current", "base")
    outputs["result"]["price"] = 10
    assert rows == before


@pytest.mark.parametrize(
    "changes",
    [
        {"project_id": "foreign"},
        {"agent_id": "foreign"},
        {"version_id": "different-version"},
        {"version_id": None},
        {"conversation_id": "other-conversation"},
        {"status": "failed"},
        {"status": "waiting"},
        {"result_json": None},
    ],
)
def test_revision_never_crosses_identity_or_incomplete_results(changes):
    repository, _, _ = _repository(**changes)
    with pytest.raises(ResultRevisionError):
        revision_base_outputs(repository, "project", "agent", "current", "base")


def test_revision_rejects_stale_base_and_missing_current_user_boundary():
    repository, _, messages = _repository()
    messages.insert(1, {"role": "assistant", "run_id": "newer", "sequence": 1.5})
    with pytest.raises(ResultRevisionError, match="preceding"):
        revision_base_outputs(repository, "project", "agent", "current", "base")
    messages.clear()
    with pytest.raises(ResultRevisionError, match="preceding"):
        revision_base_outputs(repository, "project", "agent", "current", "base")


@pytest.mark.parametrize("identity", [None, "", 1, "missing"])
def test_revision_rejects_missing_or_unavailable_base(identity):
    repository, _, _ = _repository()
    with pytest.raises(ResultRevisionError):
        revision_base_outputs(repository, "project", "agent", "current", identity)


@pytest.mark.parametrize("parent_key", ["resume_of_run_id", "retry_of_run_id"])
def test_recovery_uses_its_original_user_boundary_not_a_later_result(parent_key):
    repository, rows, messages = _repository()
    rows["recovery"] = {**rows["current"], "run_id": "recovery"}
    messages.append({"role": "assistant", "run_id": "later", "sequence": 3})
    messages.append({"role": "user", "run_id": "recovery", "sequence": 4})
    repository.run_events = lambda run_id: (
        [{"kind": "run.created", "payload": {parent_key: "current"}}]
        if run_id == "recovery"
        else []
    )
    assert revision_base_outputs(
        repository, "project", "agent", "recovery", "base"
    ) == {"result": {"price": 15}}
    rows["current"]["version_id"] = "foreign"
    with pytest.raises(ResultRevisionError):
        revision_base_outputs(repository, "project", "agent", "recovery", "base")


def test_draft_and_missing_versions_cannot_be_revision_bases():
    repository, _, _ = _repository()
    for version in (None, {"committed": 0}):
        repository.version = lambda _, value=version: value
        with pytest.raises(ResultRevisionError, match="committed"):
            revision_base_outputs(repository, "project", "agent", "current", "base")
