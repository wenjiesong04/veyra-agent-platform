"""Project-scoped ArtifactRef metadata. Bytes stay in the object store."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ArtifactSourceKind = Literal["upload", "runtime_output", "project_file_import"]


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    project_id: str
    sha256: str
    filename: str
    media_type: str
    size_bytes: int
    storage_ref: str
    source_kind: ArtifactSourceKind
    created_at: str
    run_id: str | None = None

    def to_ref(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": "artifact",
            "artifact_id": self.artifact_id,
            "media_type": self.media_type,
            "filename": self.filename,
        }
        return payload

    def event_payload(self, node_id: str) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "media_type": self.media_type,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "digest": self.sha256,
            "node_id": node_id,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "kind": "artifact",
            "artifact_id": self.artifact_id,
            "project_id": self.project_id,
            "sha256": self.sha256,
            "filename": self.filename,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "storage_ref": self.storage_ref,
            "source_kind": self.source_kind,
            "created_at": self.created_at,
        }
        if self.run_id:
            payload["run_id"] = self.run_id
        return payload
