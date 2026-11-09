"""Durable WorkItem request identity and atomic Runtime creation binding."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import IdempotencyKey, new_uuid7
from veyra_agent_platform.local.projects.service import ProjectError
from veyra_agent_platform.local.runtime.service import RuntimeError

from .store import OrchestratorStore

if TYPE_CHECKING:
    from .service import OrchestratorService


def execute_work_item(
    host: OrchestratorService,
    work_item_id: str,
    action: str,
    key: str,
    expected_attempt: int,
) -> dict[str, Any]:
    from .service import (
        _MAX_GLOBAL_CONCURRENT,
        _MAX_PROJECT_CONCURRENT,
        OrchestratorError,
        _lease_expiry,
        _now,
    )

    IdempotencyKey("1.0", key)
    if type(expected_attempt) is not int or expected_attempt < 0:
        raise OrchestratorError(
            "work_item_command_stale", "The displayed attempt number is required"
        )
    original = host._row(work_item_id)
    current = OrchestratorStore.payload(original)
    scope = f"work-item-operation:{work_item_id}"
    digest = sha256_digest(
        {
            "action": action,
            "expected_attempt_number": expected_attempt,
            "agent_id": current["agent_id"],
            "agent_version_id": current["agent_version_id"],
            "agent_source_hash": current["agent_source_hash"],
            "inputs": current["inputs"],
        }
    )
    with host.store.transaction() as connection:
        receipt = host.runtime.repository.idempotent_response(
            connection, scope, key, digest
        )
    if receipt is not None:
        return _continue_attempt(host, work_item_id, receipt["attempt_id"])

    current = host._reconcile(original)
    host._require_binding(current)
    if current["attempt_number"] != expected_attempt:
        raise OrchestratorError(
            "work_item_command_stale",
            "Work item attempt changed; refresh before continuing",
        )
    if action == "dispatch":
        if current["status"] not in {"backlog", "ready"} or expected_attempt != 0:
            raise OrchestratorError(
                "work_item_not_dispatchable",
                "Only unattempted ready work can be dispatched",
            )
        if not host._dependencies_done(current["depends_on"]):
            raise OrchestratorError(
                "work_item_blocked", "Work item dependencies have not finished"
            )
        previous_run_id = None
    else:
        if current["status"] != "failed":
            raise OrchestratorError(
                "work_item_not_retryable", "Only failed WorkItems can be retried"
            )
        previous_run_id = _previous_run(host, current)
    attempt_id, token, now = new_uuid7(), new_uuid7(), _now()
    operation = "retry" if previous_run_id else "start"
    with host.store.transaction() as connection:
        receipt = host.runtime.repository.idempotent_response(
            connection, scope, key, digest
        )
        if receipt is None:
            row = connection.execute(
                "SELECT * FROM work_items WHERE work_item_id = ?", (work_item_id,)
            ).fetchone()
            if (
                row is None
                or row["attempt_number"] != expected_attempt
                or row["status"] != current["status"]
                or any(
                    row[field] != original[field]
                    for field in (
                        "agent_id",
                        "agent_version_id",
                        "agent_source_hash",
                        "inputs_json",
                        "depends_on_json",
                    )
                )
            ):
                raise OrchestratorError(
                    "work_item_command_stale",
                    "Work item changed; refresh before continuing",
                )
            if action == "dispatch":
                for dependency in current["depends_on"]:
                    state = connection.execute(
                        "SELECT status FROM work_items WHERE work_item_id = ?",
                        (dependency,),
                    ).fetchone()
                    if state is None or state["status"] != "done":
                        raise OrchestratorError(
                            "work_item_blocked",
                            "Work item dependencies have not finished",
                        )
            active, project_active = host.store.active_counts_in_connection(
                connection, current["project_id"]
            )
            if (
                active >= _MAX_GLOBAL_CONCURRENT
                or project_active >= _MAX_PROJECT_CONCURRENT
            ):
                raise OrchestratorError(
                    "orchestrator_concurrency_limit",
                    "Local Runtime concurrency limit has been reached",
                )
            if not host.store.claim(
                connection,
                work_item_id=work_item_id,
                attempt_number=expected_attempt + 1,
                lease_token=token,
                lease_expires_at=_lease_expiry(),
                updated_at=now,
                expected_attempt_number=expected_attempt,
                expected_status=current["status"],
            ):
                raise OrchestratorError(
                    "work_item_command_stale", "Another request claimed this work item"
                )
            host.store.create_attempt(
                connection,
                attempt_id=attempt_id,
                work_item_id=work_item_id,
                attempt_number=expected_attempt + 1,
                lease_token=token,
                claimed_at=now,
                created_at=now,
                operation=operation,
                previous_run_id=previous_run_id,
                request_key=key,
            )
            host.runtime.repository.remember_response(
                connection, scope, key, digest, {"attempt_id": attempt_id}
            )
        else:
            attempt_id = receipt["attempt_id"]
    return _continue_attempt(host, work_item_id, attempt_id)


def _previous_run(host: OrchestratorService, current: dict[str, Any]) -> str | None:
    from .service import OrchestratorError

    previous = current["run_id"]
    attempts = host.store.attempts(current["work_item_id"])
    if not previous:
        previous = next(
            (
                row["run_id"] or row["previous_run_id"]
                for row in attempts
                if row["run_id"] or row["previous_run_id"]
            ),
            None,
        )
    if previous is None:
        if not attempts or any(row["operation"] is None for row in attempts):
            raise OrchestratorError(
                "work_item_recovery_required",
                "Historical dispatch evidence is incomplete; "
                "inspect its effects before creating new work",
            )
        return None
    run = host.runtime.repository.run(previous)
    if (
        run is None
        or run["project_id"] != current["project_id"]
        or run["agent_id"] != current["agent_id"]
        or run["version_id"] != current["agent_version_id"]
    ):
        raise OrchestratorError(
            "work_item_recovery_required",
            "The previous Run does not match the pinned work item",
        )
    if run["status"] not in {"failed", "interrupted", "cancelled"}:
        raise OrchestratorError(
            "work_item_recovery_required",
            "The previous Run is not terminal; inspect or stop it before retrying",
        )
    return str(previous)


def _continue_attempt(
    host: OrchestratorService, work_item_id: str, attempt_id: str
) -> dict[str, Any]:
    from .service import OrchestratorError, _failure_class, _lease_expired, _now

    attempt = host.store.attempt(attempt_id)
    assert attempt is not None and attempt["work_item_id"] == work_item_id
    if attempt["run_id"]:
        return host.get_work_item(work_item_id)
    if attempt["status"] != "dispatching":
        raise OrchestratorError(
            attempt["error_code"] or "work_item_attempt_unavailable",
            "This recorded attempt did not create a Run; refresh and inspect "
            "its failure before an explicit new retry",
        )
    row = host._row(work_item_id)
    current = OrchestratorStore.payload(row)
    if (
        row["status"] != "running"
        or row["lease_token"] != attempt["lease_token"]
        or _lease_expired(row["lease_expires_at"])
    ):
        host._reconcile(row)
        raise OrchestratorError(
            "work_item_attempt_unavailable",
            "The recorded dispatch lease is no longer active",
        )

    def bind(connection: Any, started: dict[str, Any]) -> None:
        latest_attempt = connection.execute(
            "SELECT * FROM work_item_attempts WHERE attempt_id = ?", (attempt_id,)
        ).fetchone()
        owner = connection.execute(
            "SELECT * FROM work_items WHERE work_item_id = ?", (work_item_id,)
        ).fetchone()
        if (
            started["project_id"] != current["project_id"]
            or started["agent_id"] != current["agent_id"]
            or started["version_id"] != current["agent_version_id"]
        ):
            raise RuntimeError(
                "work_item_run_mismatch",
                "Runtime creation does not match the work item binding",
            )
        if latest_attempt["run_id"] == started["run_id"]:
            return
        if (
            owner["status"] != "running"
            or owner["lease_token"] != attempt["lease_token"]
            or _lease_expired(owner["lease_expires_at"])
            or latest_attempt["status"] != "dispatching"
        ):
            raise RuntimeError(
                "work_item_lease_changed",
                "Work item was cancelled or its lease expired before Runtime creation",
            )
        if not host.store.bind_run(
            connection,
            work_item_id=work_item_id,
            lease_token=attempt["lease_token"],
            run_id=started["run_id"],
            updated_at=_now(),
        ):
            raise RuntimeError(
                "work_item_lease_changed",
                "Work item binding changed before Runtime creation",
            )
        host.store.update_attempt(
            connection,
            attempt_id,
            status="running",
            run_id=started["run_id"],
            started_at=_now(),
            error_code=None,
        )

    try:
        host._require_binding(current)
        if attempt["operation"] == "retry":
            host.runtime.command(
                current["project_id"],
                current["agent_id"],
                attempt["previous_run_id"],
                "retry",
                attempt_id,
                _on_run_created=bind,
            )
        else:
            host.runtime.run_committed(
                current["project_id"],
                current["agent_id"],
                current["inputs"],
                attempt_id,
                version_id=current["agent_version_id"],
                _on_run_created=bind,
            )
    except (RuntimeError, ProjectError, OrchestratorError) as exc:
        code = exc.code
        with host.store.transaction() as connection:
            owner = connection.execute(
                "SELECT * FROM work_items WHERE work_item_id = ?", (work_item_id,)
            ).fetchone()
            latest = connection.execute(
                "SELECT * FROM work_item_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
            if latest["run_id"]:
                return host._with_attempts(OrchestratorStore.payload(owner))
            if (
                owner["status"] == "running"
                and owner["lease_token"] == attempt["lease_token"]
            ):
                host.store.update(
                    connection,
                    work_item_id,
                    status="failed",
                    run_id=attempt["previous_run_id"],
                    lease_token=None,
                    lease_expires_at=None,
                    failure_class=_failure_class(code),
                    updated_at=_now(),
                )
                host.store.update_attempt(
                    connection,
                    attempt_id,
                    status="failed",
                    failure_class=_failure_class(code),
                    error_code=code,
                    finished_at=_now(),
                )
        raise OrchestratorError(code, str(exc)) from exc
    return host.get_work_item(work_item_id)
