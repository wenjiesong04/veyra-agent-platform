"""Use cases for durable, device-local Project Sync state."""

from __future__ import annotations

from typing import Any, Literal

from veyra_agent_platform.local.storage.project_sync import (
    PendingOperation,
    ProjectSyncState,
    now_text,
)
from veyra_agent_platform.local.storage.repositories import LocalRepository


class ProjectSyncError(ValueError):
    """A sync state operation targeted an unknown or invalid local Project."""


class ProjectSyncService:
    def __init__(self, repository: LocalRepository) -> None:
        self._repository = repository

    def get(self, project_id: str) -> dict[str, Any]:
        state = self._ensure_state(project_id)
        return self._response(state)

    def mark_pending(
        self, project_id: str, *, operation: PendingOperation
    ) -> dict[str, Any]:
        state = self._ensure_state(project_id)
        next_state: Literal["pending_upload", "pending_push"] = (
            "pending_upload" if operation == "ensure" else "pending_push"
        )
        updated = self._repository.update_project_sync_state(
            project_id=project_id,
            state=next_state,
            cloud_revision=state.cloud_revision,
            last_synced_hash=state.last_synced_hash,
            last_synced_at=state.last_synced_at,
            pending_operation=operation,
            remote_name=state.remote_name,
            remote_description=state.remote_description,
            error_code=None,
        )
        if updated is None:
            raise ProjectSyncError("unknown Project")
        return self._response(updated)

    def record(
        self,
        project_id: str,
        *,
        state: Literal[
            "local_only",
            "pending_upload",
            "synced",
            "pending_push",
            "pending_pull",
            "conflict",
            "error",
        ],
        cloud_revision: int | None,
        last_synced_hash: str | None,
        pending_operation: PendingOperation | None,
        remote_name: str | None = None,
        remote_description: str | None = None,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_state(project_id)
        if state == "synced" and (cloud_revision is None or last_synced_hash is None):
            raise ProjectSyncError("synced state requires revision and hash")
        updated = self._repository.update_project_sync_state(
            project_id=project_id,
            state=state,
            cloud_revision=cloud_revision,
            last_synced_hash=last_synced_hash,
            last_synced_at=(now_text() if state == "synced" else None),
            pending_operation=pending_operation,
            remote_name=remote_name,
            remote_description=remote_description,
            error_code=error_code,
        )
        if updated is None:
            raise ProjectSyncError("unknown Project")
        return self._response(updated)

    def _ensure_state(self, project_id: str) -> ProjectSyncState:
        project = self._repository.project_row(project_id)
        if project is None:
            raise ProjectSyncError("unknown Project")
        state = self._repository.project_sync_state(project_id)
        if state is not None:
            return state
        with self._repository.transaction() as connection:
            self._repository.ensure_project_sync_state(
                connection,
                project_id=project_id,
                local_metadata_hash=project["manifest_hash"],
            )
        state = self._repository.project_sync_state(project_id)
        if state is None:
            raise ProjectSyncError("Project sync state could not be initialized")
        return state

    @staticmethod
    def _response(state: ProjectSyncState) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "project_id": state.project_id,
            "sync_enabled": state.sync_enabled,
            "state": state.state,
            "cloud_revision": state.cloud_revision,
            "local_metadata_hash": state.local_metadata_hash,
            "last_synced_hash": state.last_synced_hash,
            "last_synced_at": state.last_synced_at,
            "pending_operation": state.pending_operation,
            "remote_name": state.remote_name,
            "remote_description": state.remote_description,
            "error_code": state.error_code,
        }
