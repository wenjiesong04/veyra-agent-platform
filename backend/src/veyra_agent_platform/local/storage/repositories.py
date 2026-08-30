"""Small, explicit SQLite repository for project-owned Agent indexes.

The project directory is authoritative.  These rows make it possible to find,
compare, and retain immutable snapshots without placing runtime state in a
user's project tree.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from veyra_agent_platform.contracts.common import new_uuid7

from .bootstrap import require_schema_head


class IdempotencyConflict(ValueError):
    """An idempotency key was reused for a different request."""


class LocalRepository:
    """Repository backed by one local SQLite connection per operation."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = str(database_path)
        if self.database_path == ":memory:":
            raise ValueError("migrate a temporary file-backed SQLite database instead")
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        require_schema_head(Path(self.database_path))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def upsert_project(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        root_path: str,
        name: str,
        description: str,
        manifest_hash: str,
        indexed_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO projects(
              project_id, root_path, name, description, manifest_hash, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, root_path, name, description, manifest_hash, indexed_at),
        )

    def project(self, project_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    """SELECT * FROM projects
                       WHERE project_id = ? AND removed_at IS NULL""",
                    (project_id,),
                ).fetchone(),
            )

    def project_by_root(self, root_path: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM projects WHERE root_path = ? AND removed_at IS NULL",
                    (root_path,),
                ).fetchone(),
            )

    def projects(self) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                """SELECT * FROM projects WHERE removed_at IS NULL
                   ORDER BY CASE WHEN pinned_at IS NULL THEN 1 ELSE 0 END,
                            indexed_at DESC, project_id ASC"""
            ).fetchall()

    def set_project_pinned(
        self, project_id: str, pinned_at: str | None
    ) -> sqlite3.Row | None:
        with self.transaction() as connection:
            cursor = connection.execute(
                """UPDATE projects SET pinned_at = ?
                   WHERE project_id = ? AND removed_at IS NULL""",
                (pinned_at, project_id),
            )
            if cursor.rowcount == 0:
                return None
            if pinned_at is not None:
                connection.execute(
                    """UPDATE projects SET pinned_at = NULL
                       WHERE project_id != ? AND removed_at IS NULL""",
                    (project_id,),
                )
            return cast(
                sqlite3.Row,
                connection.execute(
                    """SELECT * FROM projects
                       WHERE project_id = ? AND removed_at IS NULL""",
                    (project_id,),
                ).fetchone(),
            )

    def remove_project(self, project_id: str, removed_at: str) -> bool:
        """Soft-remove one active Project, retaining its original root identity."""
        with self.transaction() as connection:
            cursor = connection.execute(
                """UPDATE projects SET removed_at = ?, pinned_at = NULL
                   WHERE project_id = ? AND removed_at IS NULL""",
                (removed_at, project_id),
            )
            return cursor.rowcount == 1

    def agent(self, agent_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM agents WHERE agent_id = ? AND removed_at IS NULL",
                    (agent_id,),
                ).fetchone(),
            )

    def agents(self, project_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                """SELECT * FROM agents
                   WHERE project_id = ? AND removed_at IS NULL
                   ORDER BY slug""",
                (project_id,),
            ).fetchall()

    def upsert_agent(
        self,
        connection: sqlite3.Connection,
        *,
        agent_id: str,
        project_id: str,
        slug: str,
        source_path: str,
        source_file_hash: str,
        indexed_at: str,
        parent_agent_id: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO agents(
              agent_id, project_id, slug, source_path, source_file_hash,
              parent_agent_id, indexed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                project_id,
                slug,
                source_path,
                source_file_hash,
                parent_agent_id,
                indexed_at,
            ),
        )

    def refresh_agent(
        self,
        connection: sqlite3.Connection,
        *,
        agent_id: str,
        slug: str,
        source_path: str,
        source_file_hash: str,
        indexed_at: str,
        parent_agent_id: str | None = None,
    ) -> None:
        connection.execute(
            """UPDATE agents SET slug = ?, source_path = ?, source_file_hash = ?,
               parent_agent_id = ?, indexed_at = ?, removed_at = NULL
               WHERE agent_id = ?""",
            (
                slug,
                source_path,
                source_file_hash,
                parent_agent_id,
                indexed_at,
                agent_id,
            ),
        )

    def remove_agent(self, agent_id: str, removed_at: str) -> bool:
        """Soft-remove one Agent while retaining versions, Runs, and Draft history."""
        with self.transaction() as connection:
            cursor = connection.execute(
                """UPDATE agents SET removed_at = ?
                   WHERE agent_id = ? AND removed_at IS NULL""",
                (removed_at, agent_id),
            )
            return cursor.rowcount == 1

    def restore_agent(self, agent_id: str) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE agents SET removed_at = NULL WHERE agent_id = ?",
                (agent_id,),
            )
            return cursor.rowcount == 1

    def delete_agents(
        self, connection: sqlite3.Connection, agent_ids: set[str]
    ) -> None:
        for agent_id in agent_ids:
            has_versions = connection.execute(
                "SELECT 1 FROM agent_versions WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            if has_versions is not None:
                raise ValueError("cannot remove an Agent with immutable versions")
            connection.execute(
                "DELETE FROM agent_drafts WHERE agent_id = ?", (agent_id,)
            )
        connection.executemany(
            "DELETE FROM agents WHERE agent_id = ?",
            ((agent_id,) for agent_id in agent_ids),
        )

    def reconcile_files(
        self, connection: sqlite3.Connection, project_id: str, kept_paths: set[str]
    ) -> None:
        rows = connection.execute(
            "SELECT file_id, relative_path FROM files WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        stale = [row for row in rows if row["relative_path"] not in kept_paths]
        for row in stale:
            linked = connection.execute(
                "SELECT 1 FROM agent_version_files WHERE file_id = ?", (row["file_id"],)
            ).fetchone()
            if linked is not None:
                continue
            connection.execute(
                "DELETE FROM file_versions WHERE file_id = ?", (row["file_id"],)
            )
            connection.execute("DELETE FROM files WHERE file_id = ?", (row["file_id"],))

    def draft(self, agent_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM agent_drafts WHERE agent_id = ?", (agent_id,)
                ).fetchone(),
            )

    def insert_draft(
        self,
        connection: sqlite3.Connection,
        *,
        agent_id: str,
        draft_id: str,
        revision: int,
        source: dict[str, Any],
        source_file_hash: str,
        etag: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO agent_drafts(
              agent_id, draft_id, revision, source_json, source_file_hash, etag
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                draft_id,
                revision,
                json.dumps(source, sort_keys=True, separators=(",", ":")),
                source_file_hash,
                etag,
            ),
        )

    def update_draft(
        self,
        connection: sqlite3.Connection,
        *,
        agent_id: str,
        expected_revision: int,
        source: dict[str, Any],
        source_file_hash: str,
        etag: str,
    ) -> int:
        cursor = connection.execute(
            """
            UPDATE agent_drafts
            SET revision = revision + 1, source_json = ?, source_file_hash = ?, etag = ?
            WHERE agent_id = ? AND revision = ?
            """,
            (
                json.dumps(source, sort_keys=True, separators=(",", ":")),
                source_file_hash,
                etag,
                agent_id,
                expected_revision,
            ),
        )
        return cursor.rowcount

    def version_by_fingerprint(
        self, connection: sqlite3.Connection, agent_id: str, source_file_hash: str
    ) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            connection.execute(
                """SELECT * FROM agent_versions
                   WHERE agent_id = ? AND file_hash = ?""",
                (agent_id, source_file_hash),
            ).fetchone(),
        )

    def insert_version(
        self, connection: sqlite3.Connection, values: dict[str, Any]
    ) -> None:
        connection.execute(
            """
            INSERT INTO agent_versions(
              version_id, agent_id, source_hash, behavior_hash, lock_hash, file_hash,
              source_json, source_text, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["version_id"],
                values["agent_id"],
                values["source_hash"],
                values["behavior_hash"],
                values["lock_hash"],
                values["file_hash"],
                json.dumps(values["source"], sort_keys=True, separators=(",", ":")),
                values["source_text"],
                values["created_at"],
            ),
        )

    def add_blob_and_file(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        relative_path: str,
        digest: str,
        byte_length: int,
        object_path: str,
        observed_at: str,
    ) -> None:
        connection.execute(
            """INSERT INTO blobs(digest, byte_length, object_path, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(digest) DO NOTHING""",
            (digest, byte_length, object_path, observed_at),
        )
        row = connection.execute(
            """SELECT file_id, current_blob_digest FROM files
               WHERE project_id = ? AND relative_path = ?""",
            (project_id, relative_path),
        ).fetchone()
        if row is None:
            connection.execute(
                """INSERT INTO files(
                     file_id, project_id, relative_path,
                     current_blob_digest, observed_at
                   )
                   VALUES (?, ?, ?, ?, ?)""",
                (new_uuid7(), project_id, relative_path, digest, observed_at),
            )
            row = connection.execute(
                "SELECT file_id FROM files WHERE project_id = ? AND relative_path = ?",
                (project_id, relative_path),
            ).fetchone()
        elif row["current_blob_digest"] != digest:
            connection.execute(
                """UPDATE files SET current_blob_digest = ?, observed_at = ?
                   WHERE file_id = ?""",
                (digest, observed_at, row["file_id"]),
            )
        connection.execute(
            """INSERT OR IGNORE INTO file_versions(file_id, blob_digest, observed_at)
               VALUES (?, ?, ?)""",
            (row["file_id"], digest, observed_at),
        )

    def attach_file_to_version(
        self,
        connection: sqlite3.Connection,
        *,
        version_id: str,
        project_id: str,
        relative_path: str,
    ) -> None:
        row = connection.execute(
            """SELECT file_id FROM files
               WHERE project_id = ? AND relative_path = ?""",
            (project_id, relative_path),
        ).fetchone()
        if row is None:
            raise RuntimeError("committed Agent source is absent from the file index")
        connection.execute(
            """INSERT OR IGNORE INTO agent_version_files(version_id, file_id)
               VALUES (?, ?)""",
            (version_id, row["file_id"]),
        )

    def create_write_intent(
        self,
        connection: sqlite3.Connection,
        *,
        agent_id: str,
        previous_source_text: str,
        intended_source_text: str,
    ) -> str:
        intent_id = new_uuid7()
        connection.execute(
            """INSERT INTO draft_write_intents(
                 intent_id, agent_id, previous_source_text, intended_source_text
               ) VALUES (?, ?, ?, ?)""",
            (intent_id, agent_id, previous_source_text, intended_source_text),
        )
        return intent_id

    def remove_write_intent(
        self, connection: sqlite3.Connection, intent_id: str
    ) -> None:
        connection.execute(
            "DELETE FROM draft_write_intents WHERE intent_id = ?", (intent_id,)
        )

    def write_intents(self) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM draft_write_intents").fetchall()

    def idempotent_response(
        self, connection: sqlite3.Connection, scope: str, key: str, request_digest: str
    ) -> dict[str, Any] | None:
        row = connection.execute(
            """SELECT request_digest, response_json FROM idempotency_records
               WHERE scope = ? AND key = ?""",
            (scope, key),
        ).fetchone()
        if row is None:
            return None
        if row["request_digest"] != request_digest:
            raise IdempotencyConflict("idempotency key was reused for another request")
        return cast(dict[str, Any], json.loads(row["response_json"]))

    def remember_response(
        self,
        connection: sqlite3.Connection,
        scope: str,
        key: str,
        request_digest: str,
        response: dict[str, Any],
    ) -> None:
        connection.execute(
            """INSERT INTO idempotency_records(
                 scope, key, request_digest, response_json
               )
               VALUES (?, ?, ?, ?)""",
            (
                scope,
                key,
                request_digest,
                json.dumps(response, sort_keys=True, separators=(",", ":")),
            ),
        )

    def replace_idempotent_response(
        self,
        connection: sqlite3.Connection,
        scope: str,
        key: str,
        request_digest: str,
        response: dict[str, Any],
    ) -> None:
        connection.execute(
            """UPDATE idempotency_records SET response_json = ?
               WHERE scope = ? AND key = ? AND request_digest = ?""",
            (
                json.dumps(response, sort_keys=True, separators=(",", ":")),
                scope,
                key,
                request_digest,
            ),
        )

    def create_run(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        project_id: str,
        agent_id: str,
        version_id: str,
        created_at: str,
    ) -> None:
        connection.execute(
            "INSERT INTO runtime_runs("
            "run_id, project_id, agent_id, version_id, status, created_at"
            ") VALUES (?, ?, ?, ?, 'running', ?)",
            (run_id, project_id, agent_id, version_id, created_at),
        )

    def add_run_events(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        events: list[tuple[str | None, str, dict[str, Any]]],
    ) -> None:
        start = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) "
            "FROM runtime_run_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
        for offset, (node_id, event_type, payload) in enumerate(events, start=1):
            connection.execute(
                """INSERT INTO runtime_run_events(
                     event_id, run_id, sequence, node_id, kind, payload_json, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    new_uuid7(),
                    run_id,
                    start + offset,
                    node_id,
                    event_type,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                ),
            )

    def finish_run(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        *,
        status: str,
        result: dict[str, Any] | None,
        code: str | None,
        message: str | None,
        finished_at: str,
    ) -> None:
        connection.execute(
            "UPDATE runtime_runs SET status = ?, result_json = ?, error_code = ?, "
            "error_message = ?, finished_at = ? WHERE run_id = ?",
            (
                status,
                json.dumps(result, sort_keys=True, separators=(",", ":"))
                if result is not None
                else None,
                code,
                message,
                finished_at,
                run_id,
            ),
        )

    def run(self, run_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
                ).fetchone(),
            )

    def runs(self, agent_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM runtime_runs WHERE agent_id = ? "
                "ORDER BY created_at DESC, run_id DESC",
                (agent_id,),
            ).fetchall()

    def run_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT event_id, sequence, node_id, kind, payload_json, created_at
                   FROM runtime_run_events WHERE run_id = ? ORDER BY sequence""",
                (run_id,),
            ).fetchall()
        return [
            {
                "schema_version": "1.0",
                "event_id": row["event_id"],
                "run_id": run_id,
                "sequence": row["sequence"],
                "node_id": row["node_id"],
                "kind": row["kind"],
                "payload": json.loads(row["payload_json"]),
                "timestamp": row["created_at"],
            }
            for row in rows
        ]

    def interrupt_orphan_runs(self) -> None:
        """Close local runs left nonterminal by a prior process termination."""
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT run_id FROM runtime_runs WHERE status = 'running'"
            ).fetchall()
            for row in rows:
                self.add_run_events(
                    connection, row["run_id"], [(None, "run.interrupted", {})]
                )
                self.finish_run(
                    connection,
                    row["run_id"],
                    status="interrupted",
                    result=None,
                    code="run_interrupted",
                    message="local Runtime restarted before this run finished",
                    finished_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                )
                recovered = connection.execute(
                    "SELECT * FROM runtime_runs WHERE run_id = ?", (row["run_id"],)
                ).fetchone()
                assert recovered is not None
                payload = self._run_payload(recovered)
                for record in connection.execute(
                    "SELECT scope, key, request_digest, response_json "
                    "FROM idempotency_records"
                ).fetchall():
                    response = json.loads(record["response_json"])
                    if response.get("run_id") == row["run_id"]:
                        self.replace_idempotent_response(
                            connection,
                            record["scope"],
                            record["key"],
                            record["request_digest"],
                            payload,
                        )

    @staticmethod
    def _run_payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "run_id": row["run_id"],
            "project_id": row["project_id"],
            "agent_id": row["agent_id"],
            "version_id": row["version_id"],
            "status": row["status"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": (
                {"code": row["error_code"], "message": row["error_message"]}
                if row["error_code"]
                else None
            ),
            "created_at": row["created_at"],
            "finished_at": row["finished_at"],
        }
