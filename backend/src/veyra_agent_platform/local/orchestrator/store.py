"""SQLite persistence for local WorkItems. Runtime state stays outside Projects."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast


class OrchestratorStore:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = str(database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, isolation_level=None)
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

    def create(
        self,
        connection: sqlite3.Connection,
        *,
        work_item_id: str,
        project_id: str,
        title: str,
        description: str,
        agent_id: str,
        agent_version_id: str,
        agent_source_hash: str,
        depends_on: list[str],
        inputs: dict[str, Any],
        status: str,
        created_at: str,
    ) -> None:
        connection.execute(
            """INSERT INTO work_items(
                work_item_id, project_id, title, description, agent_id,
                agent_version_id, agent_source_hash,
                depends_on_json, inputs_json, status, run_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
            (
                work_item_id,
                project_id,
                title,
                description,
                agent_id,
                agent_version_id,
                agent_source_hash,
                json.dumps(depends_on, ensure_ascii=False),
                json.dumps(inputs, ensure_ascii=False, sort_keys=True),
                status,
                created_at,
                created_at,
            ),
        )

    def get(self, work_item_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM work_items WHERE work_item_id = ?",
                    (work_item_id,),
                ).fetchone(),
            )

    def list_project(self, project_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                """SELECT * FROM work_items WHERE project_id = ?
                   ORDER BY created_at ASC, work_item_id ASC""",
                (project_id,),
            ).fetchall()

    def list_all(self) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM work_items ORDER BY created_at DESC, work_item_id ASC"
            ).fetchall()

    @staticmethod
    def active_counts_in_connection(
        connection: sqlite3.Connection, project_id: str
    ) -> tuple[int, int]:
        global_count = connection.execute(
            "SELECT COUNT(*) FROM work_items "
            "WHERE status IN ('running', 'waiting', 'cancelling')"
        ).fetchone()[0]
        project_count = connection.execute(
            "SELECT COUNT(*) FROM work_items "
            "WHERE project_id = ? AND status IN ('running', 'waiting', 'cancelling')",
            (project_id,),
        ).fetchone()[0]
        return int(global_count), int(project_count)

    def update(
        self,
        connection: sqlite3.Connection,
        work_item_id: str,
        **fields: Any,
    ) -> None:
        assignments = []
        values: list[Any] = []
        mapping = {
            "title": "title",
            "description": "description",
            "agent_id": "agent_id",
            "agent_version_id": "agent_version_id",
            "agent_source_hash": "agent_source_hash",
            "status": "status",
            "run_id": "run_id",
            "attempt_number": "attempt_number",
            "lease_token": "lease_token",
            "lease_expires_at": "lease_expires_at",
            "failure_class": "failure_class",
            "updated_at": "updated_at",
        }
        for key, column in mapping.items():
            if key in fields:
                assignments.append(f"{column} = ?")
                values.append(fields[key])
        if "depends_on" in fields:
            assignments.append("depends_on_json = ?")
            values.append(json.dumps(fields["depends_on"], ensure_ascii=False))
        if "inputs" in fields:
            assignments.append("inputs_json = ?")
            values.append(
                json.dumps(fields["inputs"], ensure_ascii=False, sort_keys=True)
            )
        if not assignments:
            return
        values.append(work_item_id)
        connection.execute(
            f"UPDATE work_items SET {', '.join(assignments)} WHERE work_item_id = ?",
            values,
        )

    def create_attempt(
        self,
        connection: sqlite3.Connection,
        *,
        attempt_id: str,
        work_item_id: str,
        attempt_number: int,
        lease_token: str,
        claimed_at: str,
        created_at: str,
        operation: str,
        previous_run_id: str | None,
        request_key: str,
    ) -> None:
        connection.execute(
            "INSERT INTO work_item_attempts("
            "attempt_id, work_item_id, attempt_number, run_id, status, "
            "lease_token, failure_class, claimed_at, started_at, finished_at, "
            "created_at, operation, previous_run_id, request_key"
            ") VALUES (?, ?, ?, NULL, 'dispatching', ?, NULL, ?, "
            "NULL, NULL, ?, ?, ?, ?)",
            (
                attempt_id,
                work_item_id,
                attempt_number,
                lease_token,
                claimed_at,
                created_at,
                operation,
                previous_run_id,
                request_key,
            ),
        )

    def claim(
        self,
        connection: sqlite3.Connection,
        *,
        work_item_id: str,
        attempt_number: int,
        lease_token: str,
        lease_expires_at: str,
        updated_at: str,
        expected_attempt_number: int,
        expected_status: str,
    ) -> bool:
        cursor = connection.execute(
            "UPDATE work_items SET status = 'running', run_id = NULL, "
            "attempt_number = ?, lease_token = ?, lease_expires_at = ?, "
            "failure_class = NULL, updated_at = ? "
            "WHERE work_item_id = ? AND status = ? AND attempt_number = ? "
            "AND lease_token IS NULL",
            (
                attempt_number,
                lease_token,
                lease_expires_at,
                updated_at,
                work_item_id,
                expected_status,
                expected_attempt_number,
            ),
        )
        return cursor.rowcount == 1

    def bind_run(
        self,
        connection: sqlite3.Connection,
        *,
        work_item_id: str,
        lease_token: str,
        run_id: str,
        updated_at: str,
    ) -> bool:
        cursor = connection.execute(
            "UPDATE work_items SET run_id = ?, updated_at = ? "
            "WHERE work_item_id = ? AND status = 'running' "
            "AND lease_token = ? AND (run_id IS NULL OR run_id = ?)",
            (run_id, updated_at, work_item_id, lease_token, run_id),
        )
        return cursor.rowcount == 1

    def fail_stalled(
        self,
        connection: sqlite3.Connection,
        *,
        work_item_id: str,
        run_id: str | None,
        lease_token: str,
        failure_class: str,
        updated_at: str,
    ) -> bool:
        conditions = "work_item_id = ? AND status = 'running' AND lease_token = ?"
        parameters: list[Any] = [work_item_id, lease_token]
        if run_id is None:
            conditions += " AND run_id IS NULL"
        else:
            conditions += " AND run_id = ?"
            parameters.append(run_id)
        cursor = connection.execute(
            "UPDATE work_items SET status = 'failed', "
            "lease_token = NULL, lease_expires_at = NULL, failure_class = ?, "
            f"updated_at = ? WHERE {conditions}",
            [failure_class, updated_at, *parameters],
        )
        return cursor.rowcount == 1

    def attempt(self, attempt_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM work_item_attempts WHERE attempt_id = ?",
                    (attempt_id,),
                ).fetchone(),
            )

    def latest_attempt(self, work_item_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM work_item_attempts WHERE work_item_id = ? "
                    "ORDER BY attempt_number DESC LIMIT 1",
                    (work_item_id,),
                ).fetchone(),
            )

    def attempts(self, work_item_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM work_item_attempts WHERE work_item_id = ? "
                "ORDER BY attempt_number DESC LIMIT 20",
                (work_item_id,),
            ).fetchall()

    @staticmethod
    def latest_attempt_in_connection(
        connection: sqlite3.Connection, work_item_id: str
    ) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            connection.execute(
                "SELECT * FROM work_item_attempts WHERE work_item_id = ? "
                "ORDER BY attempt_number DESC LIMIT 1",
                (work_item_id,),
            ).fetchone(),
        )

    def update_attempt(
        self,
        connection: sqlite3.Connection,
        attempt_id: str,
        **fields: Any,
    ) -> None:
        mapping = {
            "run_id": "run_id",
            "status": "status",
            "failure_class": "failure_class",
            "error_code": "error_code",
            "started_at": "started_at",
            "finished_at": "finished_at",
        }
        assignments = []
        values: list[Any] = []
        for key, column in mapping.items():
            if key in fields:
                assignments.append(f"{column} = ?")
                values.append(fields[key])
        if not assignments:
            return
        values.append(attempt_id)
        connection.execute(
            f"UPDATE work_item_attempts SET {', '.join(assignments)} "
            "WHERE attempt_id = ?",
            values,
        )

    @staticmethod
    def payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "work_item_id": row["work_item_id"],
            "project_id": row["project_id"],
            "title": row["title"],
            "description": row["description"],
            "agent_id": row["agent_id"],
            "agent_version_id": row["agent_version_id"],
            "agent_source_hash": row["agent_source_hash"],
            "binding_required": row["agent_version_id"] is None,
            "depends_on": json.loads(row["depends_on_json"]),
            "inputs": json.loads(row["inputs_json"]),
            "status": row["status"],
            "run_id": row["run_id"],
            "attempt_number": int(row["attempt_number"]),
            "lease_expires_at": row["lease_expires_at"],
            "failure_class": row["failure_class"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def attempt_payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "attempt_id": row["attempt_id"],
            "attempt_number": int(row["attempt_number"]),
            "operation": row["operation"],
            "previous_run_id": row["previous_run_id"],
            "error_code": row["error_code"],
            "run_id": row["run_id"],
            "status": row["status"],
            "failure_class": row["failure_class"],
            "claimed_at": row["claimed_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "created_at": row["created_at"],
        }
