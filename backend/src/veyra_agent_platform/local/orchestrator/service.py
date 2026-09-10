"""Dispatch local WorkItems to committed Agent runs. No cloud Agent execution."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any

from veyra_agent_platform.contracts.common import SCHEMA_VERSION, new_uuid7
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.runtime.service import RuntimeError, RuntimeService

from .store import OrchestratorStore

_STATUSES = {
    "backlog",
    "ready",
    "running",
    "waiting",
    "done",
    "failed",
    "cancelled",
}
_DONE = {"done", "failed", "cancelled"}
_RUN_DONE = {"verified", "unverified"}
_RUN_FAILED = {"failed", "interrupted"}
_LEASE_SECONDS = 900


class OrchestratorError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class OrchestratorService:
    def __init__(
        self,
        store: OrchestratorStore,
        projects: ProjectService,
        runtime: RuntimeService,
    ) -> None:
        self.store = store
        self.projects = projects
        self.runtime = runtime

    def status(self) -> dict[str, Any]:
        items = [self._reconcile(row) for row in self.store.list_all()]
        counts = {name: 0 for name in _STATUSES}
        for item in items:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        active = [
            item for item in items if item["status"] in {"ready", "running", "waiting"}
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            "execution_plane": "local",
            "cloud_execution": False,
            "counts": counts,
            "active": active[:50],
        }

    def list_work_items(self, project_id: str) -> dict[str, Any]:
        self._require_project(project_id)
        items = [self._reconcile(row) for row in self.store.list_project(project_id)]
        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": project_id,
            "execution_plane": "local",
            "work_items": items,
        }

    def create_work_item(
        self,
        project_id: str,
        *,
        title: str,
        agent_id: str,
        description: str = "",
        depends_on: list[str] | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_project(project_id)
        self._require_agent(project_id, agent_id)
        clean_title = title.strip()
        if not clean_title:
            raise OrchestratorError(
                "work_item_title_invalid", "Work item title is required"
            )
        dependencies = list(depends_on or [])
        self._validate_dependencies(project_id, dependencies)
        work_item_id = new_uuid7()
        now = _now()
        status = "ready" if self._dependencies_done(dependencies) else "backlog"
        with self.store.transaction() as connection:
            self.store.create(
                connection,
                work_item_id=work_item_id,
                project_id=project_id,
                title=clean_title[:200],
                description=description.strip()[:4_000],
                agent_id=agent_id,
                depends_on=dependencies,
                inputs=dict(inputs or {}),
                status=status,
                created_at=now,
            )
        return self.get_work_item(work_item_id)

    def get_work_item(self, work_item_id: str) -> dict[str, Any]:
        row = self.store.get(work_item_id)
        if row is None:
            raise OrchestratorError("work_item_not_found", "Work item was not found")
        return self._reconcile(row)

    def update_work_item(
        self,
        work_item_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        agent_id: str | None = None,
        depends_on: list[str] | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = self._row(work_item_id)
        if row["status"] in _DONE | {"running", "waiting"}:
            raise OrchestratorError(
                "work_item_not_editable",
                "A dispatched or finished work item cannot be edited",
            )
        fields: dict[str, Any] = {"updated_at": _now()}
        if title is not None:
            clean = title.strip()
            if not clean:
                raise OrchestratorError(
                    "work_item_title_invalid", "Work item title is required"
                )
            fields["title"] = clean[:200]
        if description is not None:
            fields["description"] = description.strip()[:4_000]
        if agent_id is not None:
            self._require_agent(row["project_id"], agent_id)
            fields["agent_id"] = agent_id
        if depends_on is not None:
            self._validate_dependencies(
                row["project_id"], depends_on, skip=work_item_id
            )
            fields["depends_on"] = depends_on
            fields["status"] = (
                "ready" if self._dependencies_done(depends_on) else "backlog"
            )
        if inputs is not None:
            fields["inputs"] = dict(inputs)
        with self.store.transaction() as connection:
            self.store.update(connection, work_item_id, **fields)
        return self.get_work_item(work_item_id)

    def dispatch(self, work_item_id: str) -> dict[str, Any]:
        row = self._row(work_item_id)
        current = self._reconcile(row)
        if current["status"] not in {"backlog", "ready"}:
            raise OrchestratorError(
                "work_item_not_dispatchable",
                "Only backlog or ready work items can be dispatched",
            )
        depends_on = list(current["depends_on"])
        if not self._dependencies_done(depends_on):
            raise OrchestratorError(
                "work_item_blocked",
                "Work item dependencies have not finished",
            )
        attempt_number = int(current["attempt_number"]) + 1
        attempt_id = new_uuid7()
        lease_token = new_uuid7()
        claimed_at = _now()
        lease_expires_at = _lease_expiry()
        with self.store.transaction() as connection:
            if not self.store.claim(
                connection,
                work_item_id=work_item_id,
                attempt_number=attempt_number,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
                updated_at=claimed_at,
            ):
                raise OrchestratorError(
                    "work_item_not_dispatchable",
                    "Work item was claimed by another dispatch",
                )
            self.store.create_attempt(
                connection,
                attempt_id=attempt_id,
                work_item_id=work_item_id,
                attempt_number=attempt_number,
                lease_token=lease_token,
                claimed_at=claimed_at,
                created_at=claimed_at,
            )
        try:
            started = self.runtime.run(
                current["project_id"],
                current["agent_id"],
                dict(current["inputs"]),
                new_uuid7(),
            )
        except RuntimeError as exc:
            self._finish_dispatch_failure(
                work_item_id, attempt_id, _failure_class(exc.code)
            )
            raise OrchestratorError(exc.code, str(exc)) from exc
        except ProjectError as exc:
            self._finish_dispatch_failure(
                work_item_id, attempt_id, _failure_class("project_invalid")
            )
            raise OrchestratorError("work_item_dispatch_failed", str(exc)) from exc
        orphaned = False
        with self.store.transaction() as connection:
            orphaned = not self.store.bind_run(
                connection,
                work_item_id=work_item_id,
                lease_token=lease_token,
                run_id=started["run_id"],
                updated_at=_now(),
            )
            self.store.update_attempt(
                connection,
                attempt_id,
                status="cancelled" if orphaned else "running",
                run_id=started["run_id"] if not orphaned else None,
                failure_class="dispatch_cancelled" if orphaned else None,
                started_at=None if orphaned else _now(),
                finished_at=_now() if orphaned else None,
            )
        if orphaned:
            with contextlib.suppress(RuntimeError, ProjectError):
                self.runtime.command(
                    current["project_id"],
                    current["agent_id"],
                    started["run_id"],
                    "stop",
                    new_uuid7(),
                )
        return self.get_work_item(work_item_id)

    def retry(self, work_item_id: str) -> dict[str, Any]:
        current = self._reconcile(self._row(work_item_id))
        if current["status"] != "failed":
            raise OrchestratorError(
                "work_item_not_retryable",
                "Only failed WorkItems can be retried",
            )
        with self.store.transaction() as connection:
            self.store.update(
                connection,
                work_item_id,
                status="ready",
                run_id=None,
                lease_token=None,
                lease_expires_at=None,
                failure_class=None,
                updated_at=_now(),
            )
        return self.dispatch(work_item_id)

    def cancel(self, work_item_id: str) -> dict[str, Any]:
        row = self._row(work_item_id)
        current = self._reconcile(row)
        if current["status"] in _DONE:
            raise OrchestratorError(
                "work_item_not_cancellable",
                "A finished work item cannot be cancelled",
            )
        if current["run_id"] and current["status"] in {"running", "waiting"}:
            with contextlib.suppress(RuntimeError, ProjectError):
                self.runtime.command(
                    current["project_id"],
                    current["agent_id"],
                    current["run_id"],
                    "stop",
                    new_uuid7(),
                )
        with self.store.transaction() as connection:
            self.store.update(
                connection,
                work_item_id,
                status="cancelled",
                lease_token=None,
                lease_expires_at=None,
                updated_at=_now(),
            )
            attempt = self.store.latest_attempt_in_connection(connection, work_item_id)
            if attempt and attempt["status"] in {"dispatching", "running", "waiting"}:
                self.store.update_attempt(
                    connection,
                    attempt["attempt_id"],
                    status="cancelled",
                    failure_class="cancelled",
                    finished_at=_now(),
                )
        return self.get_work_item(work_item_id)

    def _reconcile(self, row: Any) -> dict[str, Any]:
        payload = OrchestratorStore.payload(row)
        run_id = payload["run_id"]
        if payload["status"] in _DONE:
            return payload
        if not run_id:
            if _lease_expired(payload["lease_expires_at"]):
                self._expire_lease(payload)
            return payload
        run = self.runtime.repository.run(run_id)
        if run is None:
            if _lease_expired(payload["lease_expires_at"]):
                self._expire_lease(payload)
            return payload
        mapped = _map_run_status(run["status"])
        if mapped:
            now = _now()
            finished = mapped in _DONE
            lease_token = row["lease_token"]
            with self.store.transaction() as connection:
                self.store.update(
                    connection,
                    payload["work_item_id"],
                    status=mapped,
                    lease_token=None if finished else lease_token,
                    lease_expires_at=None if finished else _lease_expiry(),
                    failure_class=(
                        _failure_class(run["error_code"] or mapped)
                        if mapped == "failed"
                        else None
                    ),
                    updated_at=now,
                )
                attempt = self.store.latest_attempt_in_connection(
                    connection, payload["work_item_id"]
                )
                if attempt and attempt["status"] in {
                    "dispatching",
                    "running",
                    "waiting",
                }:
                    self.store.update_attempt(
                        connection,
                        attempt["attempt_id"],
                        status=mapped,
                        failure_class=(
                            _failure_class(run["error_code"] or mapped)
                            if mapped == "failed"
                            else None
                        ),
                        finished_at=now if finished else None,
                    )
            payload["status"] = mapped
            payload["lease_expires_at"] = None if finished else _lease_expiry()
            payload["failure_class"] = (
                _failure_class(run["error_code"] or mapped)
                if mapped == "failed"
                else None
            )
            payload["updated_at"] = now
        return payload

    def _expire_lease(self, payload: dict[str, Any]) -> None:
        now = _now()
        with self.store.transaction() as connection:
            self.store.update(
                connection,
                payload["work_item_id"],
                status="failed",
                run_id=None,
                lease_token=None,
                lease_expires_at=None,
                failure_class="lease_expired",
                updated_at=now,
            )
            attempt = self.store.latest_attempt_in_connection(
                connection, payload["work_item_id"]
            )
            if attempt and attempt["status"] in {"dispatching", "running", "waiting"}:
                self.store.update_attempt(
                    connection,
                    attempt["attempt_id"],
                    status="failed",
                    failure_class="lease_expired",
                    finished_at=now,
                )
        payload.update(
            status="failed",
            run_id=None,
            lease_expires_at=None,
            failure_class="lease_expired",
            updated_at=now,
        )

    def _finish_dispatch_failure(
        self, work_item_id: str, attempt_id: str, failure_class: str
    ) -> None:
        now = _now()
        with self.store.transaction() as connection:
            self.store.update(
                connection,
                work_item_id,
                status="failed",
                run_id=None,
                lease_token=None,
                lease_expires_at=None,
                failure_class=failure_class,
                updated_at=now,
            )
            self.store.update_attempt(
                connection,
                attempt_id,
                status="failed",
                failure_class=failure_class,
                finished_at=now,
            )

    def _row(self, work_item_id: str) -> Any:
        row = self.store.get(work_item_id)
        if row is None:
            raise OrchestratorError("work_item_not_found", "Work item was not found")
        return row

    def _require_project(self, project_id: str) -> None:
        if self.projects.repository.project(project_id) is None:
            raise OrchestratorError(
                "orchestrator_project_not_found", "Project was not found"
            )

    def _require_agent(self, project_id: str, agent_id: str) -> None:
        try:
            self.runtime.library._agent_in_project(project_id, agent_id)
        except ProjectError as exc:
            raise OrchestratorError(
                "orchestrator_agent_not_found", "Agent was not found in this Project"
            ) from exc

    def _validate_dependencies(
        self, project_id: str, depends_on: list[str], *, skip: str | None = None
    ) -> None:
        seen: set[str] = set()
        for item_id in depends_on:
            if item_id == skip or item_id in seen:
                raise OrchestratorError(
                    "work_item_dependency_invalid",
                    "Work item dependencies must be unique and cannot include itself",
                )
            seen.add(item_id)
            dependency = self.store.get(item_id)
            if dependency is None or dependency["project_id"] != project_id:
                raise OrchestratorError(
                    "work_item_dependency_invalid",
                    "Work item dependencies must belong to the same Project",
                )

    def _dependencies_done(self, depends_on: list[str]) -> bool:
        for item_id in depends_on:
            row = self.store.get(item_id)
            if row is None:
                return False
            status = self._reconcile(row)["status"]
            if status != "done":
                return False
        return True


def _map_run_status(status: str) -> str | None:
    if status in _RUN_DONE:
        return "done"
    if status in _RUN_FAILED:
        return "failed"
    if status == "cancelled":
        return "cancelled"
    if status == "waiting":
        return "waiting"
    if status == "running":
        return "running"
    return None


def _lease_expiry() -> str:
    return (
        (datetime.now(UTC) + timedelta(seconds=_LEASE_SECONDS))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _lease_expired(value: str | None) -> bool:
    if not value:
        return False
    try:
        expires = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return True
    return expires <= datetime.now(UTC)


def _failure_class(code: str) -> str:
    if code in {
        "runtime_timeout",
        "tool_timeout",
        "mcp_timeout",
        "runtime_unavailable",
    }:
        return "transient"
    if code in {"runtime_not_configured", "secret_not_configured", "mcp_env_missing"}:
        return "configuration"
    if code in {"run_cancelled", "cancelled"}:
        return "cancelled"
    return code


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
