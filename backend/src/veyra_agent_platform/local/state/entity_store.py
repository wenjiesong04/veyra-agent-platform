"""Narrow project entity store. Not a generic database product."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import new_uuid7


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class EntityStoreError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EntityStore:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = str(database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def define_type(
        self,
        project_id: str,
        entity_type: str,
        schema: dict[str, Any],
    ) -> None:
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO project_entities(
                    project_id, entity_type, schema_json, created_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id, entity_type) DO UPDATE SET
                    schema_json = excluded.schema_json
                """,
                (
                    project_id,
                    entity_type,
                    json.dumps(schema, sort_keys=True, ensure_ascii=False),
                    now,
                ),
            )
            connection.commit()

    def write(
        self,
        *,
        project_id: str,
        entity_type: str,
        payload: dict[str, Any],
        status: str,
        entity_id: str | None = None,
        source: str = "workflow",
    ) -> dict[str, Any]:
        now = _now()
        record_id = entity_id or new_uuid7()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM entity_records WHERE entity_id = ?",
                (record_id,),
            ).fetchone()
            if existing is not None and (
                existing["project_id"] != project_id
                or existing["entity_type"] != entity_type
            ):
                raise EntityStoreError(
                    "entity_scope_conflict",
                    "Entity belongs to a different Project or entity type",
                )
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO entity_records(
                        entity_id, project_id, entity_type, payload_json,
                        status, revision, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        record_id,
                        project_id,
                        entity_type,
                        json.dumps(payload, sort_keys=True, ensure_ascii=False),
                        status,
                        now,
                        now,
                    ),
                )
                self._event(
                    connection,
                    record_id,
                    field="create",
                    old_digest="",
                    new_digest=sha256_digest(payload),
                    source=source,
                    created_at=now,
                )
                revision = 1
            else:
                old = json.loads(existing["payload_json"])
                revision = int(existing["revision"]) + 1
                connection.execute(
                    """
                    UPDATE entity_records SET payload_json = ?, status = ?,
                    revision = ?, updated_at = ?
                    WHERE entity_id = ?
                    """,
                    (
                        json.dumps(payload, sort_keys=True, ensure_ascii=False),
                        status,
                        revision,
                        now,
                        record_id,
                    ),
                )
                self._event(
                    connection,
                    record_id,
                    field="payload",
                    old_digest=sha256_digest(old),
                    new_digest=sha256_digest(payload),
                    source=source,
                    created_at=now,
                )
            connection.commit()
        return {
            "entity_id": record_id,
            "entity_type": entity_type,
            "status": status,
            "revision": revision,
            "payload": payload,
        }

    def read(self, project_id: str, entity_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM entity_records
                WHERE project_id = ? AND entity_id = ?
                """,
                (project_id, entity_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "entity_id": row["entity_id"],
            "entity_type": row["entity_type"],
            "status": row["status"],
            "revision": row["revision"],
            "payload": json.loads(row["payload_json"]),
            "updated_at": row["updated_at"],
        }

    def _event(
        self,
        connection: sqlite3.Connection,
        entity_id: str,
        *,
        field: str,
        old_digest: str,
        new_digest: str,
        source: str,
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO entity_events(
                event_id, entity_id, field, old_digest, new_digest,
                source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_uuid7(),
                entity_id,
                field,
                old_digest,
                new_digest,
                source,
                created_at,
            ),
        )
