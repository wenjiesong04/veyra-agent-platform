"""Narrow project entity store. Not a generic database product."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import new_uuid7

_QUERY_MAX_RECORDS = 50
_QUERY_MAX_SCAN = 500
_QUERY_MAX_BYTES = 1_000_000
_QUERY_MAX_FILTERS = 8
_QUERY_MAX_FILTER_BYTES = 4_096
ENTITY_HISTORY_MAX_RECORDS = 25
ENTITY_HISTORY_MAX_BYTES = 1_000_000


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
        record_id = entity_id or new_uuid7()
        with self._connect() as connection:
            # Serialize the identity/revision read with its record/event/snapshot
            # writes. A failed snapshot must roll back the whole state change.
            connection.execute("BEGIN IMMEDIATE")
            now = _now()
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
                if (
                    connection.execute(
                        "SELECT 1 FROM entity_revisions WHERE entity_id = ? LIMIT 1",
                        (record_id,),
                    ).fetchone()
                    is None
                ):
                    self._snapshot(
                        connection,
                        record_id,
                        revision=int(existing["revision"]),
                        payload_json=existing["payload_json"],
                        status=existing["status"],
                        source="legacy_baseline",
                        recorded_at=existing["updated_at"],
                        snapshot_kind="baseline",
                    )
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
            self._snapshot(
                connection,
                record_id,
                revision=revision,
                payload_json=json.dumps(payload, sort_keys=True, ensure_ascii=False),
                status=status,
                source=source,
                recorded_at=now,
                snapshot_kind="write",
            )
            connection.commit()
        return {
            "entity_id": record_id,
            "entity_type": entity_type,
            "status": status,
            "revision": revision,
            "payload": payload,
        }

    def ensure_type(
        self, project_id: str, entity_type: str, schema: dict[str, Any]
    ) -> None:
        """Atomically create a type, or keep an identical existing definition."""

        if not project_id or not entity_type or not isinstance(schema, dict):
            raise EntityStoreError(
                "entity_schema_invalid", "Project, entity type and schema are required"
            )
        try:
            expected = sha256_digest(schema)
            encoded = json.dumps(schema, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError, RecursionError) as exc:
            raise EntityStoreError(
                "entity_schema_invalid", "Entity type schema must be canonical JSON"
            ) from exc
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO project_entities(
                    project_id, entity_type, schema_json, created_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id, entity_type) DO NOTHING
                """,
                (project_id, entity_type, encoded, _now()),
            )
            row = connection.execute(
                """
                SELECT schema_json FROM project_entities
                WHERE project_id = ? AND entity_type = ?
                """,
                (project_id, entity_type),
            ).fetchone()
            try:
                existing = json.loads(row["schema_json"])
                if not isinstance(existing, dict):
                    raise ValueError("invalid schema")
                digest = sha256_digest(existing)
            except (TypeError, ValueError, RecursionError) as exc:
                raise EntityStoreError(
                    "entity_schema_invalid", "Stored entity type schema is invalid"
                ) from exc
            if digest != expected:
                raise EntityStoreError(
                    "entity_schema_conflict",
                    "This Project already has a different definition "
                    "for the entity type",
                )

    def read_type_schema(
        self, project_id: str, entity_type: str
    ) -> dict[str, Any] | None:
        """Return one Project's declared type without replacing its definition."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT schema_json FROM project_entities
                WHERE project_id = ? AND entity_type = ?
                """,
                (project_id, entity_type),
            ).fetchone()
        if row is None:
            return None
        try:
            schema = json.loads(row["schema_json"])
        except (TypeError, ValueError, RecursionError) as exc:
            raise EntityStoreError(
                "entity_schema_invalid", "Stored entity type schema is invalid"
            ) from exc
        if not isinstance(schema, dict):
            raise EntityStoreError(
                "entity_schema_invalid", "Stored entity type schema is invalid"
            )
        return schema

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

    def query(
        self,
        *,
        project_id: str,
        entity_type: str,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Read a bounded, project-scoped snapshot; filters never become SQL."""

        if not isinstance(project_id, str) or not project_id.strip():
            raise EntityStoreError("entity_query_invalid", "Project scope is required")
        if (
            not isinstance(entity_type, str)
            or not entity_type.strip()
            or len(entity_type) > 80
        ):
            raise EntityStoreError(
                "entity_query_invalid", "Entity type must contain 1 to 80 characters"
            )
        if type(limit) is not int or not 1 <= limit <= _QUERY_MAX_RECORDS:
            raise EntityStoreError(
                "entity_query_invalid", "Query limit must be an integer from 1 to 50"
            )
        selected = {} if filters is None else filters
        if (
            not isinstance(selected, dict)
            or len(selected) > _QUERY_MAX_FILTERS
            or any(
                not isinstance(key, str) or not key or len(key) > 80 for key in selected
            )
        ):
            raise EntityStoreError(
                "entity_query_invalid", "Filters must contain up to 8 data field names"
            )
        try:
            encoded = json.dumps(selected, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, RecursionError) as exc:
            raise EntityStoreError(
                "entity_query_invalid", "Filters must contain JSON values"
            ) from exc
        if len(encoded.encode("utf-8")) > _QUERY_MAX_FILTER_BYTES:
            raise EntityStoreError(
                "entity_query_invalid", "Query filters exceed the size limit"
            )

        records: list[dict[str, Any]] = []
        scanned = 0
        read_bytes = 0
        truncated = False
        with self._connect() as connection:
            # Keep metadata sizes and subsequent payload reads in one snapshot.
            # The type index includes rowid, so newest-created records come first.
            connection.execute("BEGIN")
            candidates = connection.execute(
                """
                SELECT entity_id, entity_type, status, revision, updated_at,
                       length(CAST(payload_json AS BLOB)) AS payload_bytes
                FROM entity_records
                WHERE project_id = ? AND entity_type = ?
                ORDER BY rowid DESC LIMIT ?
                """,
                (project_id, entity_type, _QUERY_MAX_SCAN + 1),
            ).fetchall()
            truncated = len(candidates) > _QUERY_MAX_SCAN
            for index, row in enumerate(candidates[:_QUERY_MAX_SCAN]):
                if read_bytes + row["payload_bytes"] > _QUERY_MAX_BYTES:
                    truncated = True
                    break
                material = connection.execute(
                    """
                    SELECT payload_json FROM entity_records
                    WHERE project_id = ? AND entity_type = ? AND entity_id = ?
                    """,
                    (project_id, entity_type, row["entity_id"]),
                ).fetchone()
                read_bytes += row["payload_bytes"]
                scanned += 1
                try:
                    data = json.loads(material["payload_json"])
                except (TypeError, ValueError, RecursionError) as exc:
                    raise EntityStoreError(
                        "entity_query_invalid", "Stored entity data is invalid"
                    ) from exc
                if not isinstance(data, dict):
                    raise EntityStoreError(
                        "entity_query_invalid", "Stored entity data is invalid"
                    )
                if not all(
                    name in data and _json_equal(data[name], value)
                    for name, value in selected.items()
                ):
                    continue
                records.append(
                    {
                        "entity_id": row["entity_id"],
                        "entity_type": row["entity_type"],
                        "revision": row["revision"],
                        "status": row["status"],
                        "data": data,
                        "updated_at": row["updated_at"],
                    }
                )
                if len(records) == limit:
                    truncated = truncated or index + 1 < len(candidates)
                    break
        return {"records": records, "scanned": scanned, "truncated": truncated}

    def history(
        self,
        *,
        project_id: str,
        entity_type: str,
        entity_id: str,
        limit: int = ENTITY_HISTORY_MAX_RECORDS,
        before_revision: int | None = None,
    ) -> dict[str, Any] | None:
        """Read saved snapshots newest-first, never reconstruct digest-only past."""
        if any(
            not isinstance(value, str) or not value.strip() or len(value) > maximum
            for value, maximum in (
                (project_id, 200),
                (entity_type, 80),
                (entity_id, 200),
            )
        ):
            raise EntityStoreError(
                "entity_history_invalid",
                "Project, entity type and entity ID are required",
            )
        if type(limit) is not int or not 1 <= limit <= ENTITY_HISTORY_MAX_RECORDS:
            raise EntityStoreError(
                "entity_history_invalid",
                "History limit must be an integer from 1 to 25",
            )
        if before_revision is not None and (
            type(before_revision) is not int
            or not 1 <= before_revision <= 9_223_372_036_854_775_807
        ):
            raise EntityStoreError(
                "entity_history_invalid", "Before revision must be a positive integer"
            )
        with self._connect() as connection:
            connection.execute("BEGIN")
            current = connection.execute(
                """SELECT revision FROM entity_records
                   WHERE project_id = ? AND entity_type = ? AND entity_id = ?""",
                (project_id, entity_type, entity_id),
            ).fetchone()
            if current is None:
                return None
            coverage = connection.execute(
                """SELECT MIN(revision) AS first_revision,
                          MAX(revision) AS last_revision, COUNT(*) AS total,
                          SUM(snapshot_kind = 'baseline') AS baselines
                   FROM entity_revisions WHERE entity_id = ?""",
                (entity_id,),
            ).fetchone()
            candidates = connection.execute(
                """SELECT revision,
                          length(CAST(payload_json AS BLOB)) AS payload_bytes,
                          length(CAST(status AS BLOB)) +
                          length(CAST(source AS BLOB)) +
                          length(CAST(recorded_at AS BLOB)) AS metadata_bytes
                   FROM entity_revisions
                   WHERE entity_id = ? AND (? IS NULL OR revision < ?)
                   ORDER BY revision DESC LIMIT ?""",
                (entity_id, before_revision, before_revision, limit + 1),
            ).fetchall()
            result: dict[str, Any] = {
                "entity_id": entity_id,
                "entity_type": entity_type,
                "current_revision": current["revision"],
                "available_from": coverage["first_revision"],
                "incomplete": bool(
                    coverage["baselines"]
                    or coverage["first_revision"] != 1
                    or coverage["last_revision"] != current["revision"]
                    or coverage["total"] != current["revision"]
                ),
                "revisions": [],
                "truncated": len(candidates) > limit,
                "next_before_revision": None,
            }
            read_bytes = 0
            for candidate in candidates[:limit]:
                # Check sizes before loading either historical contents or source.
                candidate_bytes = (
                    candidate["payload_bytes"] + candidate["metadata_bytes"]
                )
                if read_bytes + candidate_bytes > ENTITY_HISTORY_MAX_BYTES:
                    result["truncated"] = True
                    break
                read_bytes += candidate_bytes
                row = connection.execute(
                    """SELECT revision, payload_json, status, source, recorded_at,
                              snapshot_kind FROM entity_revisions
                       WHERE entity_id = ? AND revision = ?""",
                    (entity_id, candidate["revision"]),
                ).fetchone()
                try:
                    data = json.loads(row["payload_json"])
                    if not isinstance(data, dict):
                        raise ValueError("invalid history payload")
                    entry = {
                        "revision": row["revision"],
                        "data": data,
                        "status": row["status"],
                        "source": row["source"],
                        "recorded_at": row["recorded_at"],
                        "snapshot_kind": row["snapshot_kind"],
                    }
                    result["revisions"].append(entry)
                    # Include metadata and serialization overhead in the bound.
                    if (
                        len(
                            json.dumps(
                                result, ensure_ascii=False, allow_nan=False
                            ).encode("utf-8")
                        )
                        > ENTITY_HISTORY_MAX_BYTES - 100
                    ):
                        result["revisions"].pop()
                        result["truncated"] = True
                        break
                except (TypeError, ValueError, RecursionError) as exc:
                    raise EntityStoreError(
                        "entity_history_invalid", "Stored entity history is invalid"
                    ) from exc
            if result["truncated"] and candidates:
                result["next_before_revision"] = (
                    result["revisions"][-1]["revision"]
                    if result["revisions"]
                    else candidates[0]["revision"]
                )
            return result

    def _snapshot(
        self,
        connection: sqlite3.Connection,
        entity_id: str,
        *,
        revision: int,
        payload_json: str,
        status: str,
        source: str,
        recorded_at: str,
        snapshot_kind: str,
    ) -> None:
        connection.execute(
            """INSERT INTO entity_revisions(
                entity_id, revision, payload_json, status, source,
                recorded_at, snapshot_kind
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                entity_id,
                revision,
                payload_json,
                status,
                source,
                recorded_at,
                snapshot_kind,
            ),
        )

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


def _json_equal(left: Any, right: Any) -> bool:
    """JSON booleans differ from numbers, including within arrays and objects."""

    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, int | float) and isinstance(right, int | float):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _json_equal(value, right[name]) for name, value in left.items()
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_equal(first, second)
            for first, second in zip(left, right, strict=True)
        )
    return bool(left == right)
