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
from pathlib import Path
from typing import Any, cast


class LocalRepository:
    """Repository backed by one local SQLite connection per operation."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = str(database_path)
        self._memory_uri: str | None = None
        self._anchor: sqlite3.Connection | None = None
        if self.database_path == ":memory:":
            self._memory_uri = f"file:veyra-local-{id(self)}?mode=memory&cache=shared"
            self._anchor = sqlite3.connect(
                self._memory_uri, uri=True, isolation_level=None
            )
        else:
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._bootstrap_for_embedded_use()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._memory_uri or self.database_path,
            isolation_level=None,
            uri=self._memory_uri is not None,
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

    def _bootstrap_for_embedded_use(self) -> None:
        """Initialize the current local schema for an unopened desktop database.

        The identical DDL is recorded in the forward-only Alembic migration.
        Keeping this minimal bootstrap here lets the sidecar start before a UI
        exists to invoke a separate migration command, including for temporary
        SQLite databases used by tests.
        """
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def upsert_project(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        root_path: str,
        name: str,
        manifest_hash: str,
        indexed_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO projects(project_id, root_path, name, manifest_hash, indexed_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
              root_path=excluded.root_path, name=excluded.name,
              manifest_hash=excluded.manifest_hash, indexed_at=excluded.indexed_at
            """,
            (project_id, root_path, name, manifest_hash, indexed_at),
        )

    def project(self, project_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM projects WHERE project_id = ?", (project_id,)
                ).fetchone(),
            )

    def projects(self) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM projects ORDER BY name").fetchall()

    def agent(self, agent_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
                ).fetchone(),
            )

    def agents(self, project_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM agents WHERE project_id = ? ORDER BY slug", (project_id,)
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
    ) -> None:
        connection.execute(
            """
            INSERT INTO agents(
              agent_id, project_id, slug, source_path, source_file_hash, indexed_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
              project_id=excluded.project_id, slug=excluded.slug,
              source_path=excluded.source_path,
              source_file_hash=excluded.source_file_hash,
              indexed_at=excluded.indexed_at
            """,
            (agent_id, project_id, slug, source_path, source_file_hash, indexed_at),
        )

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
                   VALUES (lower(hex(randomblob(16))), ?, ?, ?, ?)""",
                (project_id, relative_path, digest, observed_at),
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

    def idempotent_response(
        self, connection: sqlite3.Connection, scope: str, key: str
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT response_json FROM idempotency_records WHERE scope = ? AND key = ?",
            (scope, key),
        ).fetchone()
        return None if row is None else json.loads(row["response_json"])

    def remember_response(
        self,
        connection: sqlite3.Connection,
        scope: str,
        key: str,
        response: dict[str, Any],
    ) -> None:
        connection.execute(
            """INSERT INTO idempotency_records(scope, key, response_json)
               VALUES (?, ?, ?)
               ON CONFLICT(scope, key) DO NOTHING""",
            (scope, key, json.dumps(response, sort_keys=True, separators=(",", ":"))),
        )


_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT PRIMARY KEY,
  root_path TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  manifest_hash TEXT NOT NULL,
  indexed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agents (
  agent_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  slug TEXT NOT NULL,
  source_path TEXT NOT NULL,
  source_file_hash TEXT NOT NULL,
  indexed_at TEXT NOT NULL,
  UNIQUE(project_id, slug)
);
CREATE TABLE IF NOT EXISTS agent_drafts (
  agent_id TEXT PRIMARY KEY REFERENCES agents(agent_id) ON DELETE CASCADE,
  draft_id TEXT NOT NULL UNIQUE,
  revision INTEGER NOT NULL CHECK(revision >= 0),
  source_json TEXT NOT NULL,
  source_file_hash TEXT NOT NULL,
  etag TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_versions (
  version_id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE RESTRICT,
  source_hash TEXT NOT NULL,
  behavior_hash TEXT NOT NULL,
  lock_hash TEXT NOT NULL,
  file_hash TEXT NOT NULL,
  source_json TEXT NOT NULL,
  source_text TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(agent_id, file_hash)
);
CREATE TABLE IF NOT EXISTS blobs (
  digest TEXT PRIMARY KEY,
  byte_length INTEGER NOT NULL CHECK(byte_length >= 0),
  object_path TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
  file_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  relative_path TEXT NOT NULL,
  current_blob_digest TEXT NOT NULL REFERENCES blobs(digest),
  observed_at TEXT NOT NULL,
  UNIQUE(project_id, relative_path)
);
CREATE TABLE IF NOT EXISTS file_versions (
  file_id TEXT NOT NULL REFERENCES files(file_id) ON DELETE CASCADE,
  blob_digest TEXT NOT NULL REFERENCES blobs(digest),
  observed_at TEXT NOT NULL,
  PRIMARY KEY(file_id, blob_digest)
);
CREATE TABLE IF NOT EXISTS agent_version_files (
  version_id TEXT NOT NULL REFERENCES agent_versions(version_id) ON DELETE CASCADE,
  file_id TEXT NOT NULL REFERENCES files(file_id) ON DELETE RESTRICT,
  PRIMARY KEY(version_id, file_id)
);
CREATE TABLE IF NOT EXISTS idempotency_records (
  scope TEXT NOT NULL,
  key TEXT NOT NULL,
  response_json TEXT NOT NULL,
  PRIMARY KEY(scope, key)
);
"""
