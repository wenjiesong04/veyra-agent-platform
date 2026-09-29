"""Portable Project Artifact envelopes shared by Local and Cloud sync."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from .canonical import sha256_digest
from .common import (
    ContractValidationError,
    freeze_json,
    require_mapping,
    require_string,
    require_uuid7,
    thaw_json,
)

ProjectArtifactKind = Literal[
    "agent",
    "agent_version",
    "workflow",
    "custom_component",
    "knowledge_metadata",
]

PROJECT_ARTIFACT_KINDS = frozenset(
    {"agent", "agent_version", "workflow", "custom_component", "knowledge_metadata"}
)
_HASH = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_KEYS = {
    "api_key",
    "credential_id",
    "keychain_ref",
    "local_path",
    "root_path",
    "source_path",
    "storage_ref",
    "device_id",
    "secret_ref",
}
_PATH_VALUE = re.compile(r"^(?:/|[A-Za-z]:\\|file://|\\\\)")


@dataclass(frozen=True)
class ProjectArtifactEnvelope:
    project_id: str
    artifact_kind: ProjectArtifactKind
    artifact_id: str
    schema_version: str
    content_hash: str
    revision: int
    deleted: bool
    immutable: bool
    payload: dict[str, Any]

    @classmethod
    def from_dict(cls, data: Any) -> ProjectArtifactEnvelope:
        item = require_mapping(data, "Project Artifact envelope")
        required = {
            "project_id",
            "artifact_kind",
            "artifact_id",
            "schema_version",
            "content_hash",
            "revision",
            "deleted",
            "immutable",
            "payload",
        }
        missing = required - set(item)
        if missing:
            raise ContractValidationError(
                f"Project Artifact envelope is missing: {', '.join(sorted(missing))}"
            )
        project_id = require_uuid7(item["project_id"], "project_id")
        kind = item["artifact_kind"]
        if kind not in PROJECT_ARTIFACT_KINDS:
            raise ContractValidationError("artifact_kind is not supported")
        artifact_id = require_string(item["artifact_id"], "artifact_id")
        schema_version = require_string(item["schema_version"], "schema_version")
        content_hash = require_string(item["content_hash"], "content_hash")
        if not _HASH.fullmatch(content_hash):
            raise ContractValidationError("content_hash must be a SHA-256 digest")
        revision = item["revision"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ContractValidationError("revision must be a positive integer")
        if not isinstance(item["deleted"], bool) or not isinstance(
            item["immutable"], bool
        ):
            raise ContractValidationError("deleted and immutable must be booleans")
        payload = thaw_json(freeze_json(require_mapping(item["payload"], "payload")))
        _validate_portable_value(payload)
        if content_hash != sha256_digest(payload):
            raise ContractValidationError("content_hash does not match payload")
        return cls(
            project_id=project_id,
            artifact_kind=kind,
            artifact_id=artifact_id,
            schema_version=schema_version,
            content_hash=content_hash,
            revision=revision,
            deleted=item["deleted"],
            immutable=item["immutable"],
            payload=payload,
        )

    @classmethod
    def build(
        cls,
        *,
        project_id: str,
        artifact_kind: ProjectArtifactKind,
        artifact_id: str,
        payload: dict[str, Any],
        revision: int = 1,
        deleted: bool = False,
        immutable: bool = False,
    ) -> ProjectArtifactEnvelope:
        _validate_portable_value(payload)
        return cls(
            project_id=require_uuid7(project_id, "project_id"),
            artifact_kind=artifact_kind,
            artifact_id=require_string(artifact_id, "artifact_id"),
            schema_version="project.artifact.v1",
            content_hash=sha256_digest(payload),
            revision=revision,
            deleted=deleted,
            immutable=immutable,
            payload=payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "artifact_kind": self.artifact_kind,
            "artifact_id": self.artifact_id,
            "schema_version": self.schema_version,
            "content_hash": self.content_hash,
            "revision": self.revision,
            "deleted": self.deleted,
            "immutable": self.immutable,
            "payload": self.payload,
        }


def _validate_portable_value(value: Any, *, key: str | None = None) -> None:
    if isinstance(value, dict):
        for name, item in value.items():
            lowered = str(name).casefold()
            if lowered in _FORBIDDEN_KEYS:
                raise ContractValidationError(
                    f"payload contains forbidden field: {name}"
                )
            if lowered in {
                "secret_refs",
                "filesystem_read_roots",
                "filesystem_write_roots",
            } and item not in ([], {}, None):
                raise ContractValidationError(
                    f"payload contains device-only field: {name}"
                )
            _validate_portable_value(item, key=lowered)
        return
    if isinstance(value, list):
        for item in value:
            _validate_portable_value(item, key=key)
        return
    if isinstance(value, str) and (
        key in {"path", "uri", "url"} and _PATH_VALUE.match(value)
    ):
        raise ContractValidationError("payload contains an absolute or local URI")
