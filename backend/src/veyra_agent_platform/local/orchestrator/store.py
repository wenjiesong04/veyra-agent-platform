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
        depends_on: list[str],
        inputs: dict[str, Any],
        status: str,
        created_at: str,
    ) -> None:
        connection.execute(
            """INSERT INTO work_items(
                work_item_id, project_id, title, description, agent_id,
                depends_on_json, inputs_json, status, run_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
            (
                work_item_id,
                project_id,
                title,
                description,
                agent_id,
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
            "status": "status",
            "run_id": "run_id",
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

    @staticmethod
    def payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "work_item_id": row["work_item_id"],
            "project_id": row["project_id"],
            "title": row["title"],
            "description": row["description"],
            "agent_id": row["agent_id"],
            "depends_on": json.loads(row["depends_on_json"]),
            "inputs": json.loads(row["inputs_json"]),
            "status": row["status"],
            "run_id": row["run_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
