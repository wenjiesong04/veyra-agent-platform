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

    def agent_origin(self, agent_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM community_agent_origins WHERE local_agent_id = ?",
                    (agent_id,),
                ).fetchone(),
            )

    def upsert_agent_origin(
        self,
        connection: sqlite3.Connection,
        *,
        local_agent_id: str,
        owner_handle: str,
        remote_slug: str,
        remote_version: str,
        remote_source_hash: str,
        imported_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO community_agent_origins(
              local_agent_id, owner_handle, remote_slug, remote_version,
              remote_source_hash, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(local_agent_id) DO UPDATE SET
              owner_handle = excluded.owner_handle,
              remote_slug = excluded.remote_slug,
              remote_version = excluded.remote_version,
              remote_source_hash = excluded.remote_source_hash,
              imported_at = excluded.imported_at
            """,
            (
                local_agent_id,
                owner_handle,
                remote_slug,
                remote_version,
                remote_source_hash,
                imported_at,
            ),
        )

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
            if linked is None:
                linked = connection.execute(
                    "SELECT 1 FROM workflow_version_files WHERE file_id = ?",
                    (row["file_id"],),
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

    def workflow(self, workflow_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    """SELECT * FROM workflows
                       WHERE workflow_id = ? AND removed_at IS NULL""",
                    (workflow_id,),
                ).fetchone(),
            )

    def upsert_workflow(
        self,
        connection: sqlite3.Connection,
        *,
        workflow_id: str,
        project_id: str,
        slug: str,
        source_path: str,
        source_file_hash: str,
        indexed_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO workflows(
              workflow_id, project_id, slug, source_path, source_file_hash,
              indexed_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                project_id,
                slug,
                source_path,
                source_file_hash,
                indexed_at,
            ),
        )

    def refresh_workflow(
        self,
        connection: sqlite3.Connection,
        *,
        workflow_id: str,
        slug: str,
        source_path: str,
        source_file_hash: str,
        indexed_at: str,
    ) -> None:
        connection.execute(
            """UPDATE workflows SET slug = ?, source_path = ?, source_file_hash = ?,
               indexed_at = ?, removed_at = NULL
               WHERE workflow_id = ?""",
            (slug, source_path, source_file_hash, indexed_at, workflow_id),
        )

    def remove_workflow(self, workflow_id: str, removed_at: str) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                """UPDATE workflows SET removed_at = ?
                   WHERE workflow_id = ? AND removed_at IS NULL""",
                (removed_at, workflow_id),
            )
            return cursor.rowcount == 1

    def restore_workflow(self, workflow_id: str) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE workflows SET removed_at = NULL WHERE workflow_id = ?",
                (workflow_id,),
            )
            return cursor.rowcount == 1

    def delete_workflows(
        self, connection: sqlite3.Connection, workflow_ids: set[str]
    ) -> None:
        for workflow_id in workflow_ids:
            has_versions = connection.execute(
                "SELECT 1 FROM workflow_versions WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if has_versions is not None:
                raise ValueError("cannot remove a Workflow with immutable versions")
            connection.execute(
                "DELETE FROM workflow_drafts WHERE workflow_id = ?", (workflow_id,)
            )
            connection.execute(
                "DELETE FROM workflow_draft_write_intents WHERE workflow_id = ?",
                (workflow_id,),
            )
        connection.executemany(
            "DELETE FROM workflows WHERE workflow_id = ?",
            ((workflow_id,) for workflow_id in workflow_ids),
        )

    def workflow_draft(self, workflow_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM workflow_drafts WHERE workflow_id = ?",
                    (workflow_id,),
                ).fetchone(),
            )

    def insert_workflow_draft(
        self,
        connection: sqlite3.Connection,
        *,
        workflow_id: str,
        draft_id: str,
        revision: int,
        source: dict[str, Any],
        source_file_hash: str,
        etag: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO workflow_drafts(
              workflow_id, draft_id, revision, source_json, source_file_hash, etag
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                draft_id,
                revision,
                json.dumps(source, sort_keys=True, separators=(",", ":")),
                source_file_hash,
                etag,
            ),
        )

    def update_workflow_draft(
        self,
        connection: sqlite3.Connection,
        *,
        workflow_id: str,
        expected_revision: int,
        source: dict[str, Any],
        source_file_hash: str,
        etag: str,
    ) -> int:
        cursor = connection.execute(
            """
            UPDATE workflow_drafts
            SET revision = revision + 1, source_json = ?, source_file_hash = ?, etag = ?
            WHERE workflow_id = ? AND revision = ?
            """,
            (
                json.dumps(source, sort_keys=True, separators=(",", ":")),
                source_file_hash,
                etag,
                workflow_id,
                expected_revision,
            ),
        )
        return cursor.rowcount

    def create_workflow_write_intent(
        self,
        connection: sqlite3.Connection,
        *,
        workflow_id: str,
        previous_source_text: str,
        intended_source_text: str,
    ) -> str:
        intent_id = new_uuid7()
        connection.execute(
            """INSERT INTO workflow_draft_write_intents(
                 intent_id, workflow_id, previous_source_text, intended_source_text
               ) VALUES (?, ?, ?, ?)""",
            (intent_id, workflow_id, previous_source_text, intended_source_text),
        )
        return intent_id

    def remove_workflow_write_intent(
        self, connection: sqlite3.Connection, intent_id: str
    ) -> None:
        connection.execute(
            "DELETE FROM workflow_draft_write_intents WHERE intent_id = ?",
            (intent_id,),
        )

    def workflow_write_intents(self) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM workflow_draft_write_intents"
            ).fetchall()

    def workflow_version_by_fingerprint(
        self, connection: sqlite3.Connection, workflow_id: str, source_file_hash: str
    ) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            connection.execute(
                """SELECT * FROM workflow_versions
                   WHERE workflow_id = ? AND file_hash = ?""",
                (workflow_id, source_file_hash),
            ).fetchone(),
        )

    def insert_workflow_version(
        self, connection: sqlite3.Connection, values: dict[str, Any]
    ) -> None:
        connection.execute(
            """
            INSERT INTO workflow_versions(
              version_id, workflow_id, source_hash, behavior_hash, lock_hash, file_hash,
              source_json, source_text, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["version_id"],
                values["workflow_id"],
                values["source_hash"],
                values["behavior_hash"],
                values["lock_hash"],
                values["file_hash"],
                json.dumps(values["source"], sort_keys=True, separators=(",", ":")),
                values["source_text"],
                values["created_at"],
            ),
        )

    def attach_file_to_workflow_version(
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
            raise RuntimeError(
                "committed Workflow source is absent from the file index"
            )
        connection.execute(
            """INSERT OR IGNORE INTO workflow_version_files(version_id, file_id)
               VALUES (?, ?)""",
            (version_id, row["file_id"]),
        )

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
        inputs: dict[str, Any] | None = None,
        conversation_id: str | None = None,
    ) -> None:
        connection.execute(
            "INSERT INTO runtime_runs("
            "run_id, project_id, agent_id, version_id, status, inputs_json, "
            "conversation_id, created_at"
            ") VALUES (?, ?, ?, ?, 'running', ?, ?, ?)",
            (
                run_id,
                project_id,
                agent_id,
                version_id,
                json.dumps(inputs or {}, sort_keys=True, separators=(",", ":")),
                conversation_id,
                created_at,
            ),
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

    def set_run_status(
        self, connection: sqlite3.Connection, run_id: str, *, status: str
    ) -> None:
        connection.execute(
            "UPDATE runtime_runs SET status = ? WHERE run_id = ?",
            (status, run_id),
        )

    def version(self, version_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM agent_versions WHERE version_id = ?",
                    (version_id,),
                ).fetchone(),
            )

    def agent_versions(self, agent_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM agent_versions WHERE agent_id = ? ORDER BY "
                "created_at DESC, version_id DESC",
                (agent_id,),
            ).fetchall()

    def project_agent_versions(self, project_id: str) -> list[sqlite3.Row]:
        """Include retained versions of soft-removed Agents for dependency checks."""
        with self._connect() as connection:
            return connection.execute(
                """SELECT v.* FROM agent_versions AS v
                   JOIN agents AS a ON a.agent_id = v.agent_id
                   WHERE a.project_id = ?
                   ORDER BY v.created_at DESC, v.version_id DESC""",
                (project_id,),
            ).fetchall()

    def workflow_versions(self, workflow_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM workflow_versions WHERE workflow_id = ? ORDER "
                "BY created_at DESC, version_id DESC",
                (workflow_id,),
            ).fetchall()

    def workflow_version(self, version_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM workflow_versions WHERE version_id = ?",
                    (version_id,),
                ).fetchone(),
            )

    def insert_tool_call(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        node_id: str,
        tool_reference: str,
        authorization: str,
        decision_code: str,
        decision_reason: str,
        input_digest: str,
        receipt: dict[str, Any] | None,
        created_at: str,
    ) -> None:
        connection.execute(
            """INSERT INTO runtime_tool_calls(
                 tool_call_id, run_id, node_id, tool_reference, authorization,
                 decision_code, decision_reason, input_digest, receipt_json, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_uuid7(),
                run_id,
                node_id,
                tool_reference,
                authorization,
                decision_code,
                decision_reason,
                input_digest,
                json.dumps(receipt, sort_keys=True, separators=(",", ":"))
                if receipt is not None
                else None,
                created_at,
            ),
        )

    def insert_approval_request(
        self,
        connection: sqlite3.Connection,
        *,
        approval_id: str,
        run_id: str,
        node_id: str,
        prompt: str,
        created_at: str,
    ) -> None:
        connection.execute(
            """INSERT INTO runtime_approval_requests(
                 approval_id, run_id, node_id, prompt, status, created_at
               ) VALUES (?, ?, ?, ?, 'pending', ?)""",
            (approval_id, run_id, node_id, prompt, created_at),
        )

    def pending_approval(
        self, connection: sqlite3.Connection, run_id: str
    ) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            connection.execute(
                """SELECT * FROM runtime_approval_requests
                   WHERE run_id = ? AND status = 'pending'
                   ORDER BY created_at DESC, approval_id DESC""",
                (run_id,),
            ).fetchone(),
        )

    def resolve_approval(
        self,
        connection: sqlite3.Connection,
        approval_id: str,
        *,
        status: str,
        command_id: str,
        resolved_at: str,
    ) -> None:
        connection.execute(
            """UPDATE runtime_approval_requests
               SET status = ?, resolved_at = ?, resolved_by_command_id = ?
               WHERE approval_id = ?""",
            (status, resolved_at, command_id, approval_id),
        )

    def insert_checkpoint(
        self,
        connection: sqlite3.Connection,
        *,
        checkpoint_id: str,
        run_id: str,
        node_id: str,
        waiting_kind: str,
        values: dict[str, Any],
        created_at: str,
    ) -> None:
        connection.execute(
            """INSERT INTO runtime_checkpoints(
                 checkpoint_id, run_id, node_id, waiting_kind, values_json, created_at
               ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                checkpoint_id,
                run_id,
                node_id,
                waiting_kind,
                json.dumps(values, sort_keys=True, separators=(",", ":")),
                created_at,
            ),
        )

    def latest_checkpoint(
        self, connection: sqlite3.Connection, run_id: str
    ) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            connection.execute(
                """SELECT * FROM runtime_checkpoints
                   WHERE run_id = ?
                   ORDER BY created_at DESC, checkpoint_id DESC""",
                (run_id,),
            ).fetchone(),
        )

    def insert_run_command(
        self,
        connection: sqlite3.Connection,
        *,
        command_id: str,
        run_id: str,
        command_type: str,
        payload: dict[str, Any],
        status: str,
        created_at: str,
        applied_at: str | None = None,
    ) -> None:
        connection.execute(
            """INSERT INTO runtime_run_commands(
                 command_id, run_id, command_type, payload_json, status,
                 created_at, applied_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                command_id,
                run_id,
                command_type,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                status,
                created_at,
                applied_at,
            ),
        )

    def mark_command_applied(
        self,
        connection: sqlite3.Connection,
        command_id: str,
        *,
        applied_at: str,
        status: str = "applied",
    ) -> None:
        connection.execute(
            """UPDATE runtime_run_commands
               SET status = ?, applied_at = ?
               WHERE command_id = ?""",
            (status, applied_at, command_id),
        )

    def cancel_pending_approvals(
        self, connection: sqlite3.Connection, run_id: str, *, resolved_at: str
    ) -> None:
        connection.execute(
            """UPDATE runtime_approval_requests
               SET status = 'cancelled', resolved_at = ?
               WHERE run_id = ? AND status = 'pending'""",
            (resolved_at, run_id),
        )

    def run_inputs(self, run_id: str) -> dict[str, Any]:
        row = self.run(run_id)
        if row is None or row["inputs_json"] in (None, ""):
            return {}
        return cast(dict[str, Any], json.loads(row["inputs_json"]))

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

    def agent_conversation(
        self,
        conversation_id: str,
        *,
        project_id: str | None = None,
        agent_id: str | None = None,
    ) -> sqlite3.Row | None:
        clauses = ["conversation_id = ?"]
        params: list[str] = [conversation_id]
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        if agent_id is not None:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        query = "SELECT * FROM agent_conversations WHERE " + " AND ".join(clauses)
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(query, tuple(params)).fetchone(),
            )

    def agent_conversations(self, project_id: str, agent_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT c.*, COUNT(m.message_id) AS message_count "
                "FROM agent_conversations c "
                "LEFT JOIN agent_conversation_messages m "
                "ON m.conversation_id = c.conversation_id "
                "WHERE c.project_id = ? AND c.agent_id = ? "
                "GROUP BY c.conversation_id "
                "ORDER BY c.updated_at DESC, c.conversation_id DESC",
                (project_id, agent_id),
            ).fetchall()

    def agent_conversation_messages(self, conversation_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM agent_conversation_messages "
                "WHERE conversation_id = ? ORDER BY sequence",
                (conversation_id,),
            ).fetchall()

    def create_agent_conversation(
        self,
        connection: sqlite3.Connection,
        *,
        conversation_id: str,
        project_id: str,
        agent_id: str,
        title: str,
        created_at: str,
    ) -> None:
        connection.execute(
            "INSERT INTO agent_conversations("
            "conversation_id, project_id, agent_id, title, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?)",
            (conversation_id, project_id, agent_id, title, created_at, created_at),
        )

    def append_agent_conversation_message(
        self,
        connection: sqlite3.Connection,
        *,
        message_id: str,
        conversation_id: str,
        sequence: int,
        role: str,
        content: str,
        run_id: str | None,
        created_at: str,
    ) -> None:
        connection.execute(
            "INSERT INTO agent_conversation_messages("
            "message_id, conversation_id, sequence, role, content, run_id, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                message_id,
                conversation_id,
                sequence,
                role,
                content,
                run_id,
                created_at,
            ),
        )

    def touch_agent_conversation(
        self, connection: sqlite3.Connection, conversation_id: str, updated_at: str
    ) -> None:
        connection.execute(
            "UPDATE agent_conversations SET updated_at = ? WHERE conversation_id = ?",
            (updated_at, conversation_id),
        )

    def run_events(self, run_id: str) -> list[dict[str, Any]]:
        return self.run_events_after(run_id, 0)

    def run_events_after(self, run_id: str, after: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT event_id, sequence, node_id, kind, payload_json, created_at
                   FROM runtime_run_events
                   WHERE run_id = ? AND sequence > ?
                   ORDER BY sequence""",
                (run_id, after),
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

    def latest_run_event_at(self, run_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT created_at FROM runtime_run_events "
                "WHERE run_id = ? ORDER BY sequence DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        return cast(str, row["created_at"]) if row is not None else None

    def replace_run_idempotent_payload(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        payload: dict[str, Any],
    ) -> None:
        for record in connection.execute(
            "SELECT scope, key, request_digest, response_json FROM idempotency_records"
        ).fetchall():
            response = json.loads(record["response_json"])
            if response.get("run_id") == run_id:
                self.replace_idempotent_response(
                    connection,
                    record["scope"],
                    record["key"],
                    record["request_digest"],
                    payload,
                )

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
                self.replace_run_idempotent_payload(
                    connection, row["run_id"], self._run_payload(recovered)
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
