"""Dispatch local WorkItems to committed Agent runs. No cloud Agent execution."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.common import SCHEMA_VERSION, new_uuid7
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.runtime.service import RuntimeError, RuntimeService

from .store import OrchestratorStore

_STATUSES = {
    "backlog",
    "ready",
    "running",
    "waiting",
    "cancelling",
    "done",
    "failed",
    "cancelled",
}
_DONE = {"done", "failed", "cancelled"}
_RUN_DONE = {"verified", "unverified"}
_RUN_FAILED = {"failed", "interrupted"}
_LEASE_SECONDS = 900
_MAX_GLOBAL_CONCURRENT = 4
_MAX_PROJECT_CONCURRENT = 2
_STALL_SECONDS = 300


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
        items = [
            self._with_attempts(self._reconcile(row)) for row in self.store.list_all()
        ]
        counts = {name: 0 for name in _STATUSES}
        for item in items:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        active = [
            item
            for item in items
            if item["status"] in {"ready", "running", "waiting", "cancelling"}
        ]
        stale_count = sum(1 for item in items if item.get("stale", False))
        return {
            "schema_version": SCHEMA_VERSION,
            "execution_plane": "local",
            "cloud_execution": False,
            "counts": counts,
            "active": active[:50],
            "stale_count": stale_count,
            "limits": {
                "global_concurrency": _MAX_GLOBAL_CONCURRENT,
                "per_project_concurrency": _MAX_PROJECT_CONCURRENT,
            },
        }

    def list_work_items(self, project_id: str) -> dict[str, Any]:
        self._require_project(project_id)
        items = [
            self._with_attempts(self._reconcile(row))
            for row in self.store.list_project(project_id)
        ]
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
        agent_version_id: str | None = None,
        description: str = "",
        depends_on: list[str] | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_project(project_id)
        self._require_agent(project_id, agent_id)
        version, source = self._version(project_id, agent_id, agent_version_id)
        try:
            prepared_inputs = self.runtime._prepare_inputs(
                project_id, source, dict(inputs or {})
            )
        except RuntimeError as exc:
            raise OrchestratorError(exc.code, str(exc)) from exc
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
                agent_version_id=version["version_id"],
                agent_source_hash=version["source_hash"],
                depends_on=dependencies,
                inputs=prepared_inputs,
                status=status,
                created_at=now,
            )
        return self.get_work_item(work_item_id)

    def get_work_item(self, work_item_id: str) -> dict[str, Any]:
        row = self.store.get(work_item_id)
        if row is None:
            raise OrchestratorError("work_item_not_found", "Work item was not found")
        return self._with_attempts(self._reconcile(row))

    def _with_attempts(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload["attempts"] = [
            OrchestratorStore.attempt_payload(row)
            for row in self.store.attempts(payload["work_item_id"])
        ]
        return payload

    def update_work_item(
        self,
        work_item_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        agent_id: str | None = None,
        agent_version_id: str | None = None,
        depends_on: list[str] | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = self._row(work_item_id)
        if row["status"] in _DONE | {"running", "waiting", "cancelling"}:
            raise OrchestratorError(
                "work_item_not_editable",
                "A dispatched or finished work item cannot be edited",
            )
        fields: dict[str, Any] = {"updated_at": _now()}
        if any(value is not None for value in (agent_id, agent_version_id, inputs)):
            if int(row["attempt_number"]) != 0:
                raise OrchestratorError(
                    "work_item_not_editable",
                    "Attempted work cannot change its Agent, version or inputs",
                )
            target_agent = agent_id or row["agent_id"]
            self._require_agent(row["project_id"], target_agent)
            selected = agent_version_id or (
                row["agent_version_id"] if target_agent == row["agent_id"] else None
            )
            if row["agent_version_id"] is None and agent_version_id is None:
                raise OrchestratorError(
                    "work_item_version_required",
                    "Select a committed Agent version before binding this legacy item",
                )
            version, source = self._version(row["project_id"], target_agent, selected)
            fields.update(
                agent_id=target_agent,
                agent_version_id=version["version_id"],
                agent_source_hash=version["source_hash"],
            )
            try:
                fields["inputs"] = self.runtime._prepare_inputs(
                    row["project_id"],
                    source,
                    inputs
                    if inputs is not None
                    else OrchestratorStore.payload(row)["inputs"],
                )
            except RuntimeError as exc:
                raise OrchestratorError(exc.code, str(exc)) from exc
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
        with self.store.transaction() as connection:
            current = connection.execute(
                "SELECT * FROM work_items WHERE work_item_id = ?", (work_item_id,)
            ).fetchone()
            if current is None or dict(current) != dict(row):
                raise OrchestratorError(
                    "work_item_command_stale",
                    "Work item changed; refresh before editing",
                )
            self.store.update(connection, work_item_id, **fields)
        return self.get_work_item(work_item_id)

    def dispatch(
        self, work_item_id: str, idempotency_key: str, *, expected_attempt_number: int
    ) -> dict[str, Any]:
        from .execution import execute_work_item

        return execute_work_item(
            self, work_item_id, "dispatch", idempotency_key, expected_attempt_number
        )

    def retry(
        self, work_item_id: str, idempotency_key: str, *, expected_attempt_number: int
    ) -> dict[str, Any]:
        from .execution import execute_work_item

        return execute_work_item(
            self, work_item_id, "retry", idempotency_key, expected_attempt_number
        )

    def cancel(self, work_item_id: str) -> dict[str, Any]:
        from .cancellation import cancel_work_item

        return cancel_work_item(self, work_item_id)

    def recover_stalled(self, work_item_id: str) -> dict[str, Any]:
        from .cancellation import recover_stalled

        return recover_stalled(self, work_item_id)

    def _reconcile(self, row: Any) -> dict[str, Any]:
        payload = OrchestratorStore.payload(row)
        if payload["status"] == "cancelling":
            from .cancellation import finish_cancellation

            return _with_attention(finish_cancellation(self, payload["work_item_id"]))
        run_id = payload["run_id"]
        if payload["status"] in _DONE:
            return _with_attention(payload)
        if not run_id:
            if _lease_expired(payload["lease_expires_at"]):
                self._expire_lease(payload, row["lease_token"])
            return _with_attention(payload)
        run = self.runtime.repository.run(run_id)
        if run is None:
            if _lease_expired(payload["lease_expires_at"]):
                self._expire_lease(payload, row["lease_token"])
            return _with_attention(payload)
        mapped = _map_run_status(run["status"])
        if mapped is not None:
            progress_at = self.runtime.repository.latest_run_event_at(run_id)
            progressed = bool(
                progress_at is not None and progress_at > payload["updated_at"]
            )
            status_changed = mapped != payload["status"]
            finished = mapped in _DONE
            if (
                payload["status"] == "running"
                and mapped == "running"
                and _lease_expired(payload["lease_expires_at"])
                and not progressed
            ):
                self._expire_lease(payload, row["lease_token"])
                return _with_attention(payload)
            if not (status_changed or finished or progressed):
                return _with_attention(payload)
            now = _now()
            activity_at = progress_at if progressed and progress_at else now
            lease_token = row["lease_token"]
            with self.store.transaction() as connection:
                owner = connection.execute(
                    "SELECT * FROM work_items WHERE work_item_id = ?",
                    (payload["work_item_id"],),
                ).fetchone()
                if (
                    owner is None
                    or owner["lease_token"] != lease_token
                    or owner["run_id"] != run_id
                    or owner["status"] in _DONE | {"cancelling"}
                ):
                    return (
                        _with_attention(OrchestratorStore.payload(owner))
                        if owner
                        else _with_attention(payload)
                    )
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
                    updated_at=activity_at,
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
                        error_code=run["error_code"] if mapped == "failed" else None,
                    )
            payload["status"] = mapped
            payload["lease_expires_at"] = None if finished else _lease_expiry()
            payload["failure_class"] = (
                _failure_class(run["error_code"] or mapped)
                if mapped == "failed"
                else None
            )
            payload["updated_at"] = activity_at
        return _with_attention(payload)

    def _expire_lease(self, payload: dict[str, Any], lease_token: str | None) -> None:
        from .cancellation import expire_lease

        expire_lease(self, payload, lease_token)

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

    def _version(
        self, project_id: str, agent_id: str, version_id: str | None
    ) -> tuple[Any, AgentSource]:
        import json

        try:
            version = self.runtime._resolve_committed_version(
                project_id, agent_id, version_id, None
            )
            source = AgentSource.from_dict(json.loads(version["source_json"]))
            if source.agent_id != agent_id or any(
                getattr(source, field) != version[field]
                for field in ("source_hash", "behavior_hash", "lock_hash")
            ):
                raise RuntimeError(
                    "agent_version_invalid",
                    "Committed Agent version integrity check failed",
                )
        except RuntimeError as exc:
            raise OrchestratorError(exc.code, str(exc)) from exc
        return version, source

    def _require_binding(self, current: dict[str, Any]) -> None:
        if not current.get("agent_version_id") or not current.get("agent_source_hash"):
            raise OrchestratorError(
                "work_item_version_required",
                "This legacy item has no committed version binding; "
                "bind an unattempted item or create a new item "
                "after checking its history",
            )
        version, _ = self._version(
            current["project_id"], current["agent_id"], current["agent_version_id"]
        )
        if version["source_hash"] != current["agent_source_hash"]:
            raise OrchestratorError(
                "agent_version_invalid",
                "Work item version digest does not match its binding",
            )

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


def _with_attention(payload: dict[str, Any]) -> dict[str, Any]:
    stale_for_seconds = _stale_for_seconds(payload["status"], payload["updated_at"])
    payload["stale"] = stale_for_seconds >= _STALL_SECONDS
    payload["stale_for_seconds"] = stale_for_seconds
    return payload


def _stale_for_seconds(status: str, updated_at: str | None) -> int:
    if status != "running" or not updated_at:
        return 0
    try:
        updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return _STALL_SECONDS
    return max(0, int((datetime.now(UTC) - updated).total_seconds()))


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
