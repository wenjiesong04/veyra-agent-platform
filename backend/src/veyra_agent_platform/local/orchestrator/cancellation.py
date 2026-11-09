"""Claim cancellation durably before stopping a bound Runtime process."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.projects.service import ProjectError
from veyra_agent_platform.local.runtime.service import RuntimeError

from .store import OrchestratorStore

if TYPE_CHECKING:
    from .service import OrchestratorService


def cancel_work_item(host: OrchestratorService, work_item_id: str) -> dict[str, Any]:
    from .service import _DONE, OrchestratorError

    with host.store.transaction() as connection:
        owner = connection.execute(
            "SELECT * FROM work_items WHERE work_item_id = ?", (work_item_id,)
        ).fetchone()
        if owner is None:
            raise OrchestratorError("work_item_not_found", "Work item was not found")
        if owner["status"] == "cancelled":
            return OrchestratorStore.payload(owner)
        if owner["status"] in _DONE:
            raise OrchestratorError(
                "work_item_not_cancellable", "A finished work item cannot be cancelled"
            )
        if owner["status"] != "cancelling":
            _claim(host, connection, owner, "cancelled")
    return host._with_attempts(finish_cancellation(host, work_item_id))


def expire_lease(
    host: OrchestratorService, payload: dict[str, Any], token: str | None
) -> None:
    from .service import _lease_expired, _lease_expiry

    if not token:
        return
    with host.store.transaction() as connection:
        owner = connection.execute(
            "SELECT * FROM work_items WHERE work_item_id = ?",
            (payload["work_item_id"],),
        ).fetchone()
        if owner is None:
            return
        if (
            owner["status"] != "running"
            or owner["lease_token"] != token
            or owner["lease_expires_at"] != payload["lease_expires_at"]
            or owner["updated_at"] != payload["updated_at"]
            or not _lease_expired(owner["lease_expires_at"])
        ):
            payload.update(OrchestratorStore.payload(owner))
            return
        progress = (
            connection.execute(
                "SELECT MAX(created_at) FROM runtime_run_events WHERE run_id = ?",
                (owner["run_id"],),
            ).fetchone()[0]
            if owner["run_id"]
            else None
        )
        if progress and progress > owner["updated_at"]:
            host.store.update(
                connection,
                payload["work_item_id"],
                updated_at=progress,
                lease_expires_at=_lease_expiry(),
            )
            fresh = connection.execute(
                "SELECT * FROM work_items WHERE work_item_id = ?",
                (payload["work_item_id"],),
            ).fetchone()
            payload.update(OrchestratorStore.payload(fresh))
            return
        _claim(host, connection, owner, "lease_expired")
    payload.update(finish_cancellation(host, payload["work_item_id"]))


def recover_stalled(host: OrchestratorService, work_item_id: str) -> dict[str, Any]:
    from .service import _STALL_SECONDS, OrchestratorError, _stale_for_seconds

    with host.store.transaction() as connection:
        owner = connection.execute(
            "SELECT * FROM work_items WHERE work_item_id = ?", (work_item_id,)
        ).fetchone()
        if owner is None:
            raise OrchestratorError("work_item_not_found", "Work item was not found")
        progress = (
            connection.execute(
                "SELECT MAX(created_at) FROM runtime_run_events WHERE run_id = ?",
                (owner["run_id"],),
            ).fetchone()[0]
            if owner["run_id"]
            else None
        )
        observed = max(owner["updated_at"], progress or owner["updated_at"])
        if (
            owner["status"] != "running"
            or _stale_for_seconds("running", observed) < _STALL_SECONDS
        ):
            raise OrchestratorError(
                "work_item_not_stalled",
                "Only a stale running WorkItem can be recovered",
            )
        _claim(host, connection, owner, "stall_recovered")
    return host._with_attempts(finish_cancellation(host, work_item_id))


def _claim(host: OrchestratorService, connection: Any, owner: Any, reason: str) -> None:
    from .service import _now

    host.store.update(
        connection,
        owner["work_item_id"],
        status="cancelling",
        failure_class=reason,
        updated_at=_now(),
    )
    attempt = host.store.latest_attempt_in_connection(connection, owner["work_item_id"])
    if attempt and attempt["status"] in {"dispatching", "running", "waiting"}:
        host.store.update_attempt(
            connection, attempt["attempt_id"], status="cancelling", failure_class=reason
        )


def finish_cancellation(host: OrchestratorService, work_item_id: str) -> dict[str, Any]:
    from .service import _failure_class, _now

    owner = host._row(work_item_id)
    if owner["status"] != "cancelling":
        return OrchestratorStore.payload(owner)
    run_id = owner["run_id"]
    run = host.runtime.repository.run(run_id) if run_id else None
    if run is not None and run["status"] in {"running", "waiting"}:
        with contextlib.suppress(RuntimeError, ProjectError):
            host.runtime.command(
                owner["project_id"],
                owner["agent_id"],
                run_id,
                "stop",
                owner["lease_token"] or new_uuid7(),
            )
        run = host.runtime.repository.run(run_id)
        if run is not None and run["status"] in {"running", "waiting"}:
            return OrchestratorStore.payload(owner)
    reason = owner["failure_class"] or "cancelled"
    status = "failed" if reason in {"lease_expired", "stall_recovered"} else "cancelled"
    if run is not None and run["status"] in {"verified", "unverified"}:
        status, reason = "done", None
    elif run is not None and run["status"] in {"failed", "interrupted"}:
        status = "failed"
        reason = _failure_class(run["error_code"] or run["status"])
    now = _now()
    with host.store.transaction() as connection:
        fresh = connection.execute(
            "SELECT * FROM work_items WHERE work_item_id = ?", (work_item_id,)
        ).fetchone()
        if (
            fresh["status"] == "cancelling"
            and fresh["run_id"] == run_id
            and fresh["lease_token"] == owner["lease_token"]
        ):
            attempt = host.store.latest_attempt_in_connection(connection, work_item_id)
            retained_run = run_id or (attempt["previous_run_id"] if attempt else None)
            host.store.update(
                connection,
                work_item_id,
                status=status,
                run_id=retained_run,
                lease_token=None,
                lease_expires_at=None,
                failure_class=reason,
                updated_at=now,
            )
            if attempt and attempt["status"] == "cancelling":
                host.store.update_attempt(
                    connection,
                    attempt["attempt_id"],
                    status=status,
                    failure_class=reason,
                    error_code=reason,
                    finished_at=now,
                )
            fresh = connection.execute(
                "SELECT * FROM work_items WHERE work_item_id = ?", (work_item_id,)
            ).fetchone()
        return OrchestratorStore.payload(fresh)
