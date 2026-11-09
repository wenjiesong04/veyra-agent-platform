"""Local lifecycle evidence with real SQLite and files, no real Provider."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.runtime.service import RuntimeError
from veyra_agent_platform.local.runtime.tools import ToolRuntimeError
from veyra_agent_platform.local.storage.bootstrap import migrate_local_database

from .test_loop_resource_truth import _client as _runtime_client
from .test_runtime_routes import (
    ScriptedRuntimeTransport,
    _await_run,
    _bind_write_resource,
    _write_source,
)
from .test_workflow_version_boundary import agent_source


def _client(tmp_path, **kwargs):
    return _runtime_client(
        tmp_path / "database", ScriptedRuntimeTransport([]), **kwargs
    )


def _commit(client, prefix):
    draft = client.get(f"{prefix}/draft").json()
    response = client.post(
        f"{prefix}/commit",
        json={"expected_revision": draft["revision"]},
        headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _setup(client, source=None, inputs=None):
    project = client.post(
        "/api/v1/projects", json={"agents": [source or agent_source()]}
    ).json()
    p, a = project["project_id"], project["agents"][0]["agent_id"]
    prefix = f"/api/v1/projects/{p}/agents/{a}"
    version = _commit(client, prefix)
    created = client.post(
        f"/api/v1/projects/{p}/work-items",
        json={
            "title": "Pinned work",
            "agent_id": a,
            "inputs": inputs or {"request": "facts"},
        },
    )
    assert created.status_code == 201, created.text
    return project, prefix, version, created.json()


def _action(client, item, command="dispatch", key=None):
    return client.post(
        f"/api/v1/work-items/{item['work_item_id']}/{command}",
        json={"expected_attempt_number": item["attempt_number"]},
        headers={"Idempotency-Key": key or new_uuid7()},
    )


def _item(client, item):
    return client.get(f"/api/v1/work-items/{item['work_item_id']}").json()


def _settled(client, item):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        current = _item(client, item)
        if current["status"] not in {"running", "waiting", "cancelling"}:
            return current
        time.sleep(0.02)
    raise AssertionError(current)


def test_work_item_uses_creation_version_after_draft_and_new_commit_changes(tmp_path):
    with _client(tmp_path) as client:
        project, prefix, version, item = _setup(client)
        assert item["agent_version_id"] == version["version_id"]
        draft = client.get(f"{prefix}/draft").json()
        source = draft["source"]
        source["nodes"][1]["mapping"]["result"] = "Version B: {{request}}"
        saved = client.patch(
            f"{prefix}/draft",
            json={"source": source, "expected_revision": draft["revision"]},
            headers={"If-Match": draft["etag"], "Idempotency-Key": new_uuid7()},
        )
        assert saved.status_code == 200, saved.text
        later = _commit(client, prefix)
        assert later["version_id"] != item["agent_version_id"]
        started = _action(client, item)
        assert started.status_code == 200, started.text
        done = _settled(client, item)
        run = client.get(f"{prefix}/runs/{done['run_id']}").json()
        assert done["status"] == "done" and run["result"] == {
            "result": "Version A: facts"
        }
        assert run["version_id"] == item["agent_version_id"]
        assert done["agent_source_hash"] == version["source_hash"]
        assert done["attempts"][0]["operation"] == "start"
        assert project["project_id"] == done["project_id"]


def test_work_item_creation_needs_committed_version_and_rejects_foreign_pin(tmp_path):
    with _client(tmp_path) as client:
        project = client.post(
            "/api/v1/projects", json={"agents": [agent_source()]}
        ).json()
        p, a = project["project_id"], project["agents"][0]["agent_id"]
        payload = {"title": "Work", "agent_id": a, "inputs": {"request": "facts"}}
        response = client.post(f"/api/v1/projects/{p}/work-items", json=payload)
        assert (
            response.status_code == 422
            and response.json()["code"] == "agent_has_no_committed_version"
        )
        _, _, other, _ = _setup(client)
        response = client.post(
            f"/api/v1/projects/{p}/work-items",
            json={**payload, "agent_version_id": other["version_id"]},
        )
        assert (
            response.status_code == 422
            and response.json()["code"] == "agent_version_not_found"
        )


def test_legacy_unbound_work_needs_explicit_version_and_attempted_work_cannot_rebind(
    tmp_path,
):
    with _client(tmp_path) as client:
        _, _, version, item = _setup(client)
        service = client.app.state.orchestrator
        with service.store.transaction() as connection:
            connection.execute(
                "UPDATE work_items SET agent_version_id=NULL, "
                "agent_source_hash=NULL WHERE work_item_id=?",
                (item["work_item_id"],),
            )
        old = _item(client, item)
        assert old["binding_required"]
        assert _action(client, old).json()["code"] == "work_item_version_required"
        assert (
            client.patch(
                f"/api/v1/work-items/{item['work_item_id']}",
                json={"agent_id": item["agent_id"]},
            ).status_code
            == 422
        )
        bound = client.patch(
            f"/api/v1/work-items/{item['work_item_id']}",
            json={"agent_version_id": version["version_id"]},
        )
        assert bound.status_code == 200, bound.text
        assert _action(client, bound.json()).status_code == 200
        done = _settled(client, item)
        assert (
            client.patch(
                f"/api/v1/work-items/{item['work_item_id']}",
                json={"agent_version_id": version["version_id"]},
            ).status_code
            == 422
        )
        assert done["agent_version_id"] == version["version_id"]


def test_same_dispatch_key_concurrently_creates_one_attempt_and_one_run(
    tmp_path, monkeypatch
):
    with _client(tmp_path) as client:
        _, prefix, _, item = _setup(client)
        runtime = client.app.state.runtime
        original = runtime.run_committed
        barrier = threading.Barrier(2)

        def delayed(*args, **kwargs):
            barrier.wait(5)
            return original(*args, **kwargs)

        monkeypatch.setattr(runtime, "run_committed", delayed)
        key = new_uuid7()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(lambda _: _action(client, item, key=key), range(2))
            )
        assert all(response.status_code == 200 for response in responses), [
            response.text for response in responses
        ]
        done = _settled(client, item)
        assert done["attempt_number"] == 1 and len(done["attempts"]) == 1
        assert len(client.get(f"{prefix}/runs").json()["runs"]) == 1
        assert _action(client, item, key=key).json()["run_id"] == done["run_id"]
        assert _action(client, item, key=new_uuid7()).status_code == 409


@pytest.mark.parametrize("after_creation", [False, True])
def test_restart_replays_dispatch_receipt_without_creating_another_attempt(
    tmp_path, monkeypatch, after_creation
):
    with _client(tmp_path) as client:
        _, prefix, version, item = _setup(client)
        key = new_uuid7()
        runtime = client.app.state.runtime
        with monkeypatch.context() as patch:
            if after_creation:

                def crash(*args):
                    raise AssertionError("Synthetic process loss after Run commit")

                patch.setattr(runtime, "_schedule_execution", crash)
            else:
                from veyra_agent_platform.local.orchestrator import execution

                def crash(*args):
                    raise AssertionError("Synthetic process loss after claim")

                patch.setattr(execution, "_continue_attempt", crash)
            with pytest.raises(AssertionError, match="Synthetic process loss"):
                _action(client, item, key=key)
        attempts = client.app.state.orchestrator.store.attempts(item["work_item_id"])
        assert len(attempts) == 1
        prior_run = attempts[0]["run_id"]
        assert bool(prior_run) == after_creation
    with _client(tmp_path) as client:
        response = _action(client, item, key=key)
        assert response.status_code == 200, response.text
        current = _settled(client, item)
        assert current["attempt_number"] == 1 and len(current["attempts"]) == 1
        assert current["agent_version_id"] == version["version_id"]
        runs = client.get(f"{prefix}/runs").json()["runs"]
        assert len(runs) == 1
        if after_creation:
            assert current["run_id"] == prior_run
            assert runs[0]["status"] == "interrupted" and runs[0]["result"] is None
        else:
            assert current["status"] == "done"


def test_work_item_owned_run_cannot_create_untracked_retry_or_resume(
    tmp_path, monkeypatch
):
    with _client(tmp_path) as client:
        _, prefix, _, item = _setup(client)
        runtime = client.app.state.runtime
        monkeypatch.setattr(runtime, "_schedule_execution", lambda *args: None)
        started = _action(client, item).json()
        with runtime.repository.transaction() as connection:
            connection.execute(
                "UPDATE runtime_runs SET status='failed', error_code='runtime_timeout' "
                "WHERE run_id=?",
                (started["run_id"],),
            )
        for command in ("retry", "resume"):
            rejected = client.post(
                f"{prefix}/runs/{started['run_id']}/commands",
                json={
                    "command": command,
                    **({"checkpoint_id": new_uuid7()} if command == "resume" else {}),
                },
                headers={"Idempotency-Key": new_uuid7()},
            )
            assert rejected.status_code == 422, rejected.text
            assert rejected.json()["code"] == "work_item_command_required"
        assert len(client.get(f"{prefix}/runs").json()["runs"]) == 1
        retried = _action(client, _item(client, item), "retry")
        assert retried.status_code == 200, retried.text
        assert len(client.get(f"{prefix}/runs").json()["runs"]) == 2
        assert retried.json()["attempts"][0]["previous_run_id"] == started["run_id"]


def test_cancel_before_runtime_binding_rolls_back_creation(tmp_path, monkeypatch):
    with _client(tmp_path) as client:
        _, prefix, _, item = _setup(client)
        runtime = client.app.state.runtime
        original = runtime.run_committed
        entered, release = threading.Event(), threading.Event()

        def delayed(*args, **kwargs):
            entered.set()
            assert release.wait(5)
            return original(*args, **kwargs)

        monkeypatch.setattr(runtime, "run_committed", delayed)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_action, client, item)
            try:
                assert entered.wait(5)
                cancelled = client.post(
                    f"/api/v1/work-items/{item['work_item_id']}/cancel"
                )
                assert cancelled.json()["status"] == "cancelled"
            finally:
                release.set()
            assert future.result().status_code == 422
        assert client.get(f"{prefix}/runs").json()["runs"] == []
        assert _item(client, item)["status"] == "cancelled"


def test_cancel_after_binding_before_worker_start_stops_the_created_run(
    tmp_path, monkeypatch
):
    with _client(tmp_path) as client:
        _, prefix, _, item = _setup(client)
        runtime = client.app.state.runtime
        schedule = runtime._schedule_execution
        entered, release = threading.Event(), threading.Event()

        def delayed(*args, **kwargs):
            entered.set()
            assert release.wait(5)
            return schedule(*args, **kwargs)

        monkeypatch.setattr(runtime, "_schedule_execution", delayed)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_action, client, item)
            try:
                assert entered.wait(5)
                cancelled = client.post(
                    f"/api/v1/work-items/{item['work_item_id']}/cancel"
                ).json()
                assert cancelled["status"] == "cancelled" and cancelled["run_id"]
            finally:
                release.set()
            assert future.result().status_code == 200
        run = client.get(f"{prefix}/runs/{cancelled['run_id']}").json()
        assert run["status"] == "cancelled" and run["result"] is None


def test_failed_stop_remains_cancelling_and_keeps_concurrency_until_confirmed(
    tmp_path, monkeypatch
):
    with _client(tmp_path) as client:
        _, prefix, _, item = _setup(client)
        runtime = client.app.state.runtime
        monkeypatch.setattr(runtime, "_schedule_execution", lambda *args: None)
        assert _action(client, item).status_code == 200
        command = runtime.command

        def unavailable(*args, **kwargs):
            raise RuntimeError("runtime_unavailable", "Synthetic stop failure")

        monkeypatch.setattr(runtime, "command", unavailable)
        pending = client.post(
            f"/api/v1/work-items/{item['work_item_id']}/cancel"
        ).json()
        assert pending["status"] == "cancelling"
        store = client.app.state.orchestrator.store
        with store.transaction() as connection:
            assert (
                store.active_counts_in_connection(connection, item["project_id"])[0]
                == 1
            )
        monkeypatch.setattr(runtime, "command", command)
        stopped = _item(client, item)
        assert stopped["status"] == "cancelled"
        assert (
            client.get(f"{prefix}/runs/{stopped['run_id']}").json()["status"]
            == "cancelled"
        )


def test_retry_after_successful_write_or_unknown_image_does_not_replay_effects(
    tmp_path,
):
    effects = []

    def write(**kwargs):
        effects.append("write")
        (tmp_path / "effect.txt").write_text("one")
        raise ToolRuntimeError("tool_timeout", "Synthetic unknown write outcome")

    with _client(
        tmp_path, tool_adapters={"veyra.runtime.filesystem.write": write}
    ) as client:
        source = _write_source(client)
        project = client.post("/api/v1/projects", json={"agents": [source]}).json()
        _bind_write_resource(client, project)
        p, a = project["project_id"], project["agents"][0]["agent_id"]
        prefix = f"/api/v1/projects/{p}/agents/{a}"
        _commit(client, prefix)
        item = client.post(
            f"/api/v1/projects/{p}/work-items",
            json={
                "title": "Write",
                "agent_id": a,
                "inputs": {"path": "out.txt", "content": "one"},
            },
        ).json()
        started = _action(client, item)
        assert started.status_code == 200, started.text
        run_id = started.json()["run_id"]
        waiting = _await_run(client, f"{prefix}/run", run_id)
        assert waiting["status"] == "waiting"
        approved = client.post(
            f"{prefix}/runs/{run_id}/commands",
            json={"command": "approve"},
            headers={"Idempotency-Key": new_uuid7()},
        )
        assert approved.status_code == 200, approved.text
        assert _await_run(client, f"{prefix}/run", run_id)["status"] == "failed"
        failed = _settled(client, item)
        retry = _action(client, failed, "retry")
        assert (
            retry.status_code == 422 and retry.json()["code"] == "retry_effect_unsafe"
        )
        assert _item(client, item)["run_id"] == run_id
        assert len(client.get(f"{prefix}/runs").json()["runs"]) == 1
        assert effects == ["write"] and (tmp_path / "effect.txt").read_text() == "one"


def test_safe_retry_keeps_version_inputs_lineage_and_replays_same_key(
    tmp_path, monkeypatch
):
    with _client(tmp_path) as client:
        _, prefix, version, item = _setup(client)
        runtime = client.app.state.runtime
        monkeypatch.setattr(runtime, "_schedule_execution", lambda *args: None)
        started = _action(client, item).json()
        original_run = started["run_id"]
        with runtime.repository.transaction() as connection:
            connection.execute(
                "UPDATE runtime_runs SET status='failed', "
                "error_code='runtime_timeout' WHERE run_id=?",
                (original_run,),
            )
        failed = _item(client, item)
        key = new_uuid7()
        retry = _action(client, failed, "retry", key)
        assert retry.status_code == 200, retry.text
        child = retry.json()
        assert child["run_id"] != original_run and child["attempt_number"] == 2
        run = client.get(f"{prefix}/runs/{child['run_id']}").json()
        assert run["version_id"] == version["version_id"]
        assert run["events"][0]["payload"]["retry_of_run_id"] == original_run
        assert runtime.repository.run_inputs(child["run_id"]) == item["inputs"]
        assert child["attempts"][0]["previous_run_id"] == original_run
        assert _action(client, failed, "retry", key).json()["run_id"] == child["run_id"]
        assert len(client.get(f"{prefix}/runs").json()["runs"]) == 2


def test_late_expiry_snapshot_cannot_cancel_a_renewed_lease(tmp_path, monkeypatch):
    with _client(tmp_path) as client:
        _, prefix, _, item = _setup(client)
        runtime = client.app.state.runtime
        monkeypatch.setattr(runtime, "_schedule_execution", lambda *args: None)
        started = _action(client, item).json()
        service = client.app.state.orchestrator
        progress = runtime.repository.latest_run_event_at(started["run_id"])
        with service.store.transaction() as connection:
            service.store.update(
                connection,
                item["work_item_id"],
                lease_expires_at="2000-01-01T00:00:00Z",
                updated_at=progress,
            )
        old = service.store.get(item["work_item_id"])
        expire = service._expire_lease
        entered, release = threading.Event(), threading.Event()

        def delayed(*args):
            entered.set()
            assert release.wait(5)
            return expire(*args)

        monkeypatch.setattr(service, "_expire_lease", delayed)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(service._reconcile, old)
            try:
                assert entered.wait(5)
                with runtime.repository.transaction() as connection:
                    runtime.repository.add_run_events(
                        connection,
                        started["run_id"],
                        [("compose", "node.started", {"component_type": "Transform"})],
                    )
                refreshed = _item(client, item)
                assert (
                    refreshed["status"] == "running"
                    and refreshed["lease_expires_at"] != old["lease_expires_at"]
                )
            finally:
                release.set()
            assert future.result()["status"] == "running"
        assert (
            client.get(f"{prefix}/runs/{started['run_id']}").json()["status"]
            == "running"
        )


def test_upgrade_keeps_legacy_work_item_data_and_does_not_guess_latest_pin(tmp_path):
    with _client(tmp_path) as client:
        _, _, _, item = _setup(client)
        repository = client.app.state.runtime.repository
        database_path = repository.database_path
        with repository.transaction() as connection:
            for field in ("agent_version_id", "agent_source_hash"):
                connection.execute(f"ALTER TABLE work_items DROP COLUMN {field}")
            for field in ("operation", "previous_run_id", "request_key", "error_code"):
                connection.execute(
                    f"ALTER TABLE work_item_attempts DROP COLUMN {field}"
                )
            connection.execute(
                "UPDATE alembic_version "
                "SET version_num='local_0037_entity_revision_history'"
            )
            before = dict(
                connection.execute(
                    "SELECT * FROM work_items WHERE work_item_id=?",
                    (item["work_item_id"],),
                ).fetchone()
            )
    migrate_local_database(Path(database_path))
    import sqlite3

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        after = dict(
            connection.execute(
                "SELECT * FROM work_items WHERE work_item_id=?", (item["work_item_id"],)
            ).fetchone()
        )
    assert after["agent_version_id"] is None and after["agent_source_hash"] is None
    assert {field: after[field] for field in before} == before
