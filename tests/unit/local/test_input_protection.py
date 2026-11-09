"""Run-owned input protection survives aliases, concurrency, and process loss."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, Literal

import pytest

from veyra_agent_platform.local.runtime.input_protection import (
    InputProtectionError,
    InputProtectionScope,
    InputProtectionStore,
)
from veyra_agent_platform.local.runtime.workflow_store import WorkflowRunStore
from veyra_agent_platform.local.storage import LocalRepository, migrate_local_database

STAMP = "2026-10-12T00:00:00Z"


@pytest.fixture
def repository(tmp_path: Path) -> LocalRepository:
    database = tmp_path / "local.sqlite3"
    migrate_local_database(database)
    repository = LocalRepository(database)
    with repository.transaction() as connection:
        for project_id in ("project-a", "project-b"):
            repository.upsert_project(
                connection,
                project_id=project_id,
                root_path=str(tmp_path / project_id),
                name=project_id,
                description="",
                manifest_hash="project-hash",
                indexed_at=STAMP,
            )
            repository.upsert_agent(
                connection,
                agent_id=f"{project_id}-agent",
                project_id=project_id,
                slug="agent",
                source_path="agents/agent.vagent.yaml",
                source_file_hash="source-hash",
                indexed_at=STAMP,
            )
            repository.upsert_workflow(
                connection,
                workflow_id=f"{project_id}-workflow",
                project_id=project_id,
                slug="workflow",
                source_path="workflows/workflow.vworkflow.yaml",
                source_file_hash="source-hash",
                indexed_at=STAMP,
            )
            version: dict[str, Any] = {
                "version_id": f"{project_id}-agent-version",
                "agent_id": f"{project_id}-agent",
                "workflow_id": f"{project_id}-workflow",
                "source_hash": "source-hash",
                "behavior_hash": "behavior-hash",
                "lock_hash": "lock-hash",
                "file_hash": "file-hash",
                "source": {},
                "source_text": "{}",
                "created_at": STAMP,
            }
            repository.insert_version(connection, version)
            version["version_id"] = f"{project_id}-workflow-version"
            repository.insert_workflow_version(connection, version)
    return repository


def _run(
    repository: LocalRepository,
    kind: Literal["agent", "workflow"],
    run_id: str = "owner-run",
    project_id: str = "project-a",
    protection: dict[str, str] | None = None,
) -> InputProtectionScope:
    scope = InputProtectionScope(project_id, kind, run_id)
    payload = {"input_protection": protection or scope.to_dict()}
    with repository.transaction() as connection:
        if kind == "agent":
            repository.create_run(
                connection,
                run_id=run_id,
                project_id=project_id,
                agent_id=f"{project_id}-agent",
                version_id=f"{project_id}-agent-version",
                created_at=STAMP,
            )
            repository.add_run_events(
                connection, run_id, [(None, "run.created", payload)]
            )
        else:
            connection.execute(
                "INSERT INTO workflow_runs(run_id, project_id, workflow_id, "
                "version_id, status, context_json, created_at) "
                "VALUES (?, ?, ?, ?, 'running', '{}', ?)",
                (
                    run_id,
                    project_id,
                    f"{project_id}-workflow",
                    f"{project_id}-workflow-version",
                    STAMP,
                ),
            )
            WorkflowRunStore(repository).event(
                connection, run_id, None, "run.created", payload
            )
    return scope


def _events(
    repository: LocalRepository, scope: InputProtectionScope, kind: str
) -> list[dict[str, Any]]:
    if scope.owner_kind == "agent":
        events = repository.run_events(scope.owner_run_id)
    else:
        events = WorkflowRunStore(repository).events(scope.owner_run_id)
    return [event for event in events if event["kind"] == kind]


def _input(root: Path, relative: str = "reports/input.csv") -> tuple[Path, bytes]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    contents = b'\xef\xbb\xbfitem,amount,note\r\nA,0.10,"two\r\nlines"\r\n'
    path.write_bytes(contents)
    return path, contents


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_exact_bytes_are_fingerprinted_once_without_content_or_host_path(
    repository: LocalRepository, tmp_path: Path, kind: Literal["agent", "workflow"]
) -> None:
    scope = _run(repository, kind)
    store = InputProtectionStore(repository)
    path, contents = _input(tmp_path)
    metadata = path.stat()

    store.protect_project_file(scope, tmp_path, path, metadata, contents)
    store.protect_project_file(scope, tmp_path, path, metadata, contents)

    events = _events(repository, scope, "input.protected")
    assert len(events) == 1
    assert events[0]["sequence"] == 2
    assert events[0]["payload"] == {
        "relative_path": "reports/input.csv",
        "st_dev": metadata.st_dev,
        "st_ino": metadata.st_ino,
        "sha256": hashlib.sha256(contents).hexdigest(),
        "byte_count": len(contents),
    }
    assert str(tmp_path) not in json.dumps(events)
    assert "two" not in json.dumps(events)
    assert store.scope_for_run("project-a", kind, "owner-run") == scope
    if kind == "workflow":
        assert WorkflowRunStore(repository).row("owner-run")["context_json"] == "{}"


def test_scope_is_frozen_and_serializes_only_owner_reference() -> None:
    scope = InputProtectionScope("project-a", "agent", "run-a")
    assert scope.to_dict() == {"scope_kind": "agent", "scope_run_id": "run-a"}
    with pytest.raises(FrozenInstanceError):
        scope.owner_run_id = "other"  # type: ignore[misc]


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_protected_path_inode_and_case_aliases_are_rejected(
    repository: LocalRepository, tmp_path: Path, kind: Literal["agent", "workflow"]
) -> None:
    scope = _run(repository, kind)
    store = InputProtectionStore(repository)
    path, contents = _input(tmp_path)
    store.protect_project_file(scope, tmp_path, path, path.stat(), contents)
    hardlink = tmp_path / "report.csv"
    os.link(path, hardlink)
    case_alias = path.with_name("INPUT.csv")
    if not case_alias.exists():
        os.link(path, case_alias)

    for target in (path, hardlink, case_alias, path.parent / "." / path.name):
        with pytest.raises(InputProtectionError) as error:
            store.assert_writable(scope, tmp_path, target)
        assert error.value.code == "input_file_protected"
        assert str(tmp_path) not in str(error.value)
    path.unlink()
    with pytest.raises(InputProtectionError, match="protected input"):
        store.assert_writable(scope, tmp_path, path)
    path.write_bytes(b"external replacement")
    with pytest.raises(InputProtectionError, match="protected input"):
        store.assert_writable(scope, tmp_path, path)


def test_equal_hash_is_not_file_identity_and_scopes_are_isolated(
    repository: LocalRepository, tmp_path: Path
) -> None:
    scope = _run(repository, "agent")
    other_run = _run(repository, "agent", "other-run")
    other_project = _run(repository, "workflow", "other-project", "project-b")
    store = InputProtectionStore(repository)
    path, contents = _input(tmp_path)
    store.protect_project_file(scope, tmp_path, path, path.stat(), contents)
    same_contents = tmp_path / "same.csv"
    same_contents.write_bytes(contents)

    store.assert_writable(scope, tmp_path, same_contents)
    store.assert_writable(other_run, tmp_path, path)
    store.assert_writable(other_project, tmp_path, path)
    assert _events(repository, other_run, "input.protected") == []
    assert _events(repository, other_project, "input.protected") == []


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_reopened_store_and_separate_process_retain_protection(
    repository: LocalRepository, tmp_path: Path, kind: Literal["agent", "workflow"]
) -> None:
    scope = _run(repository, kind)
    path, contents = _input(tmp_path)
    InputProtectionStore(repository).protect_project_file(
        scope, tmp_path, path, path.stat(), contents
    )
    reopened = InputProtectionStore(LocalRepository(repository.database_path))
    recovered = reopened.scope_for_run("project-a", kind, "owner-run")
    with pytest.raises(InputProtectionError):
        reopened.assert_writable(recovered, tmp_path, path)

    script = """
import sys
from pathlib import Path
from veyra_agent_platform.local.storage import LocalRepository
from veyra_agent_platform.local.runtime.input_protection import (
    InputProtectionStore, InputProtectionError,
)
store = InputProtectionStore(LocalRepository(sys.argv[1]))
scope = store.scope_for_run('project-a', sys.argv[2], 'owner-run')
try:
    store.assert_writable(scope, Path(sys.argv[3]), Path(sys.argv[4]))
except InputProtectionError as error:
    assert error.code == 'input_file_protected'
else:
    raise AssertionError('protection was lost after process restart')
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            repository.database_path,
            kind,
            str(tmp_path),
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "backend/src"),
        },
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_concurrent_reads_deduplicate_under_the_write_transaction(
    repository: LocalRepository, tmp_path: Path, kind: Literal["agent", "workflow"]
) -> None:
    scope = _run(repository, kind)
    store = InputProtectionStore(repository)
    path, contents = _input(tmp_path)

    def protect(_: int) -> None:
        InputProtectionStore(repository).protect_project_file(
            scope, tmp_path, path, path.stat(), contents
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(protect, range(8)))
    assert len(_events(repository, scope, "input.protected")) == 1
    with pytest.raises(InputProtectionError):
        store.assert_writable(scope, tmp_path, path)


def test_changed_content_and_new_hardlink_path_append_evidence(
    repository: LocalRepository, tmp_path: Path
) -> None:
    scope = _run(repository, "agent")
    store = InputProtectionStore(repository)
    path, contents = _input(tmp_path)
    store.protect_project_file(scope, tmp_path, path, path.stat(), contents)
    changed = b"updated outside Runtime"
    path.write_bytes(changed)
    store.protect_project_file(scope, tmp_path, path, path.stat(), changed)
    alias = tmp_path / "alias.csv"
    os.link(path, alias)
    store.protect_project_file(scope, tmp_path, alias, alias.stat(), changed)
    assert len(_events(repository, scope, "input.protected")) == 3
    alias.unlink()
    with pytest.raises(InputProtectionError):
        store.assert_writable(scope, tmp_path, alias)


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_own_report_can_be_read_back_and_written_again(
    repository: LocalRepository, tmp_path: Path, kind: Literal["agent", "workflow"]
) -> None:
    scope = _run(repository, kind)
    store = InputProtectionStore(repository)
    path, contents = _input(tmp_path, "reports/result.csv")
    store.record_output_file(scope, tmp_path, path, path.stat())
    store.record_output_file(scope, tmp_path, path, path.stat())
    reopened = InputProtectionStore(LocalRepository(repository.database_path))
    reopened.protect_project_file(scope, tmp_path, path, path.stat(), contents)
    reopened.assert_writable(scope, tmp_path, path)
    path.write_bytes(b"final report")
    reopened.record_output_file(scope, tmp_path, path, path.stat())
    reopened.protect_project_file(scope, tmp_path, path, path.stat(), path.read_bytes())
    reopened.assert_writable(scope, tmp_path, path)
    assert _events(repository, scope, "input.protected") == []
    assert len(_events(repository, scope, "input.output_created")) == 1
    assert _events(repository, scope, "input.output_created")[0]["payload"] == {
        "relative_path": "reports/result.csv",
        "st_dev": path.stat().st_dev,
        "st_ino": path.stat().st_ino,
    }


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_output_marker_cannot_unlock_input_path_or_identity(
    repository: LocalRepository, tmp_path: Path, kind: Literal["agent", "workflow"]
) -> None:
    scope = _run(repository, kind)
    store = InputProtectionStore(repository)
    path, contents = _input(tmp_path)
    store.protect_project_file(scope, tmp_path, path, path.stat(), contents)
    alias = tmp_path / "result.csv"
    os.link(path, alias)
    for target in (path, alias):
        store.record_output_file(scope, tmp_path, target, target.stat())
        store.protect_project_file(scope, tmp_path, target, target.stat(), contents)
        with pytest.raises(InputProtectionError) as error:
            store.assert_writable(scope, tmp_path, target)
        assert error.value.code == "input_file_protected"
    assert len(_events(repository, scope, "input.protected")) == 2


def test_output_exemption_requires_same_path_identity_and_scope(
    repository: LocalRepository, tmp_path: Path
) -> None:
    scope = _run(repository, "agent")
    other = _run(repository, "agent", "other")
    store = InputProtectionStore(repository)
    path, contents = _input(tmp_path, "reports/result.csv")
    store.record_output_file(scope, tmp_path, path, path.stat())
    store.protect_project_file(other, tmp_path, path, path.stat(), contents)
    with pytest.raises(InputProtectionError):
        store.assert_writable(other, tmp_path, path)
    alias = tmp_path / "copied-result.csv"
    os.link(path, alias)
    store.protect_project_file(scope, tmp_path, alias, alias.stat(), contents)
    with pytest.raises(InputProtectionError):
        store.assert_writable(scope, tmp_path, path)


def test_replaced_output_file_does_not_inherit_the_output_exemption(
    repository: LocalRepository, tmp_path: Path
) -> None:
    scope = _run(repository, "agent")
    store = InputProtectionStore(repository)
    path, contents = _input(tmp_path, "reports/result.csv")
    store.record_output_file(scope, tmp_path, path, path.stat())
    path.rename(tmp_path / "original-result.csv")
    path.write_bytes(contents)
    store.protect_project_file(scope, tmp_path, path, path.stat(), contents)
    with pytest.raises(InputProtectionError):
        store.assert_writable(scope, tmp_path, path)


def test_disabled_scope_does_not_access_files_or_database(
    repository: LocalRepository, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = InputProtectionStore(repository)

    def reject_connection() -> None:
        raise AssertionError("disabled protection must not use the database")

    monkeypatch.setattr(repository, "_connect", reject_connection)
    nonexistent_root = tmp_path / "missing"
    metadata = tmp_path.stat()
    store.validate_scope(None)
    store.protect_project_file(None, nonexistent_root, Path("/outside"), metadata, b"")
    store.record_output_file(None, nonexistent_root, Path("/outside"), metadata)
    store.assert_writable(None, nonexistent_root, Path("/outside"))


def test_scope_recovery_uses_first_creation_and_shared_workflow_owner(
    repository: LocalRepository,
) -> None:
    workflow = _run(repository, "workflow", "parent")
    _run(repository, "agent", "child", protection=workflow.to_dict())
    _run(repository, "agent", "sibling", protection=workflow.to_dict())
    with repository.transaction() as connection:
        repository.add_run_events(
            connection,
            "child",
            [(None, "run.created", {"input_protection": None})],
        )
    store = InputProtectionStore(repository)
    assert store.scope_for_run("project-a", "agent", "child") == workflow
    assert store.scope_for_run("project-a", "agent", "sibling") == workflow


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_scope_reads_inside_existing_write_transaction_do_not_self_lock(
    repository: LocalRepository, kind: Literal["agent", "workflow"]
) -> None:
    scope = _run(repository, kind)
    store = InputProtectionStore(repository)
    with repository.transaction():
        assert store.scope_for_run("project-a", kind, "owner-run") == scope
        store.validate_scope(scope)


def test_inherited_scope_owner_must_be_in_same_project(
    repository: LocalRepository,
) -> None:
    owner = _run(repository, "workflow", "foreign-parent", "project-b")
    _run(repository, "agent", "child", protection=owner.to_dict())
    with pytest.raises(InputProtectionError) as error:
        InputProtectionStore(repository).scope_for_run("project-a", "agent", "child")
    assert error.value.code == "input_protection_scope_unavailable"


@pytest.mark.parametrize("kind", ["agent", "workflow"])
def test_absent_creation_metadata_disables_protection(
    repository: LocalRepository, kind: Literal["agent", "workflow"]
) -> None:
    _run(repository, kind)
    table = "runtime_run_events" if kind == "agent" else "workflow_run_events"
    with repository.transaction() as connection:
        connection.execute(f"UPDATE {table} SET payload_json = '{{}}'")
    assert (
        InputProtectionStore(repository).scope_for_run("project-a", kind, "owner-run")
        is None
    )


@pytest.mark.parametrize(
    ("kind", "run_id", "project_id", "code"),
    [
        ("unsupported", "owner-run", "project-a", "input_protection_scope_invalid"),
        ("agent", "missing", "project-a", "input_protection_scope_unavailable"),
        ("agent", "owner-run", "project-b", "input_protection_scope_unavailable"),
    ],
)
def test_missing_foreign_or_unsupported_owner_fails_closed(
    repository: LocalRepository, kind: str, run_id: str, project_id: str, code: str
) -> None:
    _run(repository, "agent")
    store = InputProtectionStore(repository)
    with pytest.raises(InputProtectionError) as error:
        store.scope_for_run(project_id, kind, run_id)
    assert error.value.code == code
    with pytest.raises(InputProtectionError) as error:
        store.validate_scope(InputProtectionScope(project_id, kind, run_id))  # type: ignore[arg-type]
    assert error.value.code == code


@pytest.mark.parametrize(
    "protection",
    [
        False,
        {},
        {"scope_kind": "agent"},
        {"scope_kind": "tool", "scope_run_id": "owner-run"},
    ],
)
def test_malformed_protection_metadata_fails_closed(
    repository: LocalRepository, protection: Any
) -> None:
    _run(repository, "agent")
    with repository.transaction() as connection:
        connection.execute(
            "UPDATE runtime_run_events SET payload_json = ?",
            (json.dumps({"input_protection": protection}),),
        )
    with pytest.raises(InputProtectionError) as error:
        InputProtectionStore(repository).scope_for_run(
            "project-a", "agent", "owner-run"
        )
    assert error.value.code == "input_protection_scope_invalid"


def test_project_escape_and_invalid_durable_evidence_fail_closed(
    repository: LocalRepository, tmp_path: Path
) -> None:
    scope = _run(repository, "agent")
    store = InputProtectionStore(repository)
    with pytest.raises(InputProtectionError) as error:
        store.assert_writable(scope, tmp_path, tmp_path.parent / "outside.csv")
    assert error.value.code == "input_protection_path_invalid"
    with repository.transaction() as connection:
        repository.add_run_events(
            connection,
            "owner-run",
            [(None, "input.protected", {"relative_path": "input.csv"})],
        )
    with pytest.raises(InputProtectionError) as error:
        store.assert_writable(scope, tmp_path, tmp_path / "report.csv")
    assert error.value.code == "input_protection_record_invalid"
