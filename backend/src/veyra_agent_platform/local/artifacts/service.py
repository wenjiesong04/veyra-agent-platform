"""Project-scoped artifacts backed by the existing object store."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from veyra_agent_platform.contracts.artifact import ArtifactRecord, ArtifactSourceKind
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.artifacts.media import (
    ArtifactIntakeError,
    inspect_artifact,
    sanitize_filename,
)
from veyra_agent_platform.local.projects.service import ProjectError
from veyra_agent_platform.local.storage.objects import (
    object_path,
    read_object,
    write_object,
)
from veyra_agent_platform.local.storage.repositories import LocalRepository


class ArtifactService:
    def __init__(self, repository: LocalRepository, object_root: Path) -> None:
        self.repository = repository
        self.object_root = object_root

    def upload(
        self,
        project_id: str,
        filename: str | None,
        contents: bytes,
        *,
        claimed_type: str | None = None,
        source_kind: ArtifactSourceKind = "upload",
        run_id: str | None = None,
    ) -> dict[str, Any]:
        if self.repository.project(project_id) is None:
            raise ProjectError("Project was not found", "project_not_found")
        try:
            safe_name = sanitize_filename(filename)
            media_type, _kind = inspect_artifact(safe_name, contents, claimed_type)
        except ArtifactIntakeError as exc:
            raise ProjectError(str(exc), exc.code) from exc
        digest, _path = write_object(self.object_root, contents)
        created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        record = ArtifactRecord(
            artifact_id=f"art_{new_uuid7()}",
            project_id=project_id,
            sha256=digest,
            filename=safe_name,
            media_type=media_type,
            size_bytes=len(contents),
            storage_ref=f"sha256/{digest}",
            source_kind=source_kind,
            created_at=created_at,
            run_id=run_id,
        )
        with self.repository.transaction() as connection:
            self.repository.insert_artifact(connection, record)
        return record.to_dict()

    def get(self, project_id: str, artifact_id: str) -> dict[str, Any]:
        record = self._require(project_id, artifact_id)
        return record.to_dict()

    def ref(self, project_id: str, artifact_id: str) -> dict[str, Any]:
        return self._require(project_id, artifact_id).to_ref()

    def read_bytes(
        self, project_id: str, artifact_id: str
    ) -> tuple[ArtifactRecord, bytes]:
        record = self._require(project_id, artifact_id)
        try:
            payload = read_object(self.object_root, record.sha256)
        except ValueError as exc:
            raise ProjectError(
                "Artifact storage is missing or corrupted",
                "artifact_storage_invalid",
            ) from exc
        if len(payload) != record.size_bytes:
            raise ProjectError(
                "Artifact storage is missing or corrupted",
                "artifact_storage_invalid",
            )
        return record, payload

    def _require(self, project_id: str, artifact_id: str) -> ArtifactRecord:
        if self.repository.project(project_id) is None:
            raise ProjectError("Project was not found", "project_not_found")
        record = self.repository.artifact(project_id, artifact_id)
        if record is None:
            raise ProjectError("Artifact was not found", "artifact_not_found")
        try:
            object_path(self.object_root, record.sha256)
        except ValueError as exc:
            raise ProjectError(
                "Artifact storage is missing or corrupted",
                "artifact_storage_invalid",
            ) from exc
        return record
