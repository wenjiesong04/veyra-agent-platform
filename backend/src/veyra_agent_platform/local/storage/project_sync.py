"""Device-local Project Sync state and metadata hashing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

SyncState = Literal[
    "local_only",
    "pending_upload",
    "synced",
    "pending_push",
    "pending_pull",
    "conflict",
    "error",
]
PendingOperation = Literal["ensure", "push", "pull", "archive"]

SYNC_STATES = frozenset(
    {
        "local_only",
        "pending_upload",
        "synced",
        "pending_push",
        "pending_pull",
        "conflict",
        "error",
    }
)
PENDING_OPERATIONS = frozenset({"ensure", "push", "pull", "archive"})


@dataclass(frozen=True)
class ProjectSyncState:
    project_id: str
    sync_enabled: bool
    state: SyncState
    cloud_revision: int | None
    local_metadata_hash: str | None
    last_synced_hash: str | None
    last_synced_at: str | None
    pending_operation: PendingOperation | None
    remote_name: str | None
    remote_description: str | None
    error_code: str | None


def project_metadata_hash(
    *, project_id: str, name: str, description: str, lifecycle: str = "active"
) -> str:
    payload = {
        "description": description,
        "lifecycle": lifecycle,
        "name": name,
        "project_id": project_id,
        "schema_version": "project.metadata.v1",
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def now_text() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
