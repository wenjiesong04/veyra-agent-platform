"""SQLite repository for Project-scoped Factory conversations."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast


class FactorySessionRepository:
    """Keep conversation messages separate from Project source files."""

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

    def create_session(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        project_id: str,
        state: str,
        ready: bool,
        next_prompt: str,
        resource_plan: list[dict[str, Any]],
        created_at: str,
    ) -> None:
        connection.execute(
            """INSERT INTO factory_sessions(
                session_id, project_id, state, ready, next_prompt,
                resource_plan_json, blueprint_json, diagnostics_json,
                missing_capabilities_json, identity_json, revision,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, '[]', '[]', '{}', 0, ?, ?)""",
            (
                session_id,
                project_id,
                state,
                int(ready),
                next_prompt,
                json.dumps(resource_plan, ensure_ascii=False, sort_keys=True),
                created_at,
                created_at,
            ),
        )

    def session(
        self, session_id: str, project_id: str | None = None
    ) -> sqlite3.Row | None:
        with self._connect() as connection:
            if project_id is None:
                query = "SELECT * FROM factory_sessions WHERE session_id = ?"
                params: tuple[str, ...] = (session_id,)
            else:
                query = (
                    "SELECT * FROM factory_sessions "
                    "WHERE session_id = ? AND project_id = ?"
                )
                params = (session_id, project_id)
            return cast(
                sqlite3.Row | None, connection.execute(query, params).fetchone()
            )

    def messages(self, session_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM factory_messages WHERE session_id = ? ORDER BY sequence",
                (session_id,),
            ).fetchall()

    def append_message(
        self,
        connection: sqlite3.Connection,
        *,
        message_id: str,
        session_id: str,
        sequence: int,
        role: str,
        content: str,
        created_at: str,
    ) -> None:
        connection.execute(
            """INSERT INTO factory_messages(
                message_id, session_id, sequence, role, content, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (message_id, session_id, sequence, role, content, created_at),
        )

    def update_session(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        *,
        state: str | None = None,
        ready: bool | None = None,
        next_prompt: str | None = None,
        resource_plan: list[dict[str, Any]] | None = None,
        blueprint: Mapping[str, Any] | None = None,
        diagnostics: list[str] | None = None,
        missing_capabilities: list[dict[str, Any]] | None = None,
        identity: Mapping[str, str] | None = None,
        revision: int | None = None,
        updated_at: str,
    ) -> None:
        current = connection.execute(
            "SELECT * FROM factory_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if current is None:
            raise ValueError("unknown Factory session")
        values = {
            "state": state if state is not None else current["state"],
            "ready": int(ready if ready is not None else bool(current["ready"])),
            "next_prompt": next_prompt
            if next_prompt is not None
            else current["next_prompt"],
            "resource_plan_json": json.dumps(
                resource_plan
                if resource_plan is not None
                else json.loads(current["resource_plan_json"]),
                ensure_ascii=False,
                sort_keys=True,
            ),
            "blueprint_json": (
                json.dumps(blueprint, ensure_ascii=False, sort_keys=True)
                if blueprint is not None
                else current["blueprint_json"]
            ),
            "diagnostics_json": json.dumps(
                diagnostics
                if diagnostics is not None
                else json.loads(current["diagnostics_json"]),
                ensure_ascii=False,
                sort_keys=True,
            ),
            "missing_capabilities_json": json.dumps(
                missing_capabilities
                if missing_capabilities is not None
                else json.loads(current["missing_capabilities_json"]),
                ensure_ascii=False,
                sort_keys=True,
            ),
            "identity_json": json.dumps(
                dict(identity)
                if identity is not None
                else json.loads(current["identity_json"] or "{}"),
                ensure_ascii=False,
                sort_keys=True,
            ),
            "revision": revision
            if revision is not None
            else int(current["revision"]) + 1,
            "updated_at": updated_at,
            "session_id": session_id,
        }
        connection.execute(
            """UPDATE factory_sessions SET state = :state, ready = :ready,
               next_prompt = :next_prompt, resource_plan_json = :resource_plan_json,
               blueprint_json = :blueprint_json, diagnostics_json = :diagnostics_json,
               missing_capabilities_json = :missing_capabilities_json,
               identity_json = :identity_json,
               revision = :revision, updated_at = :updated_at
               WHERE session_id = :session_id""",
            values,
        )

    @staticmethod
    def payload(row: sqlite3.Row, messages: list[sqlite3.Row]) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "session_id": row["session_id"],
            "project_id": row["project_id"],
            "state": row["state"],
            "ready": bool(row["ready"]),
            "next_prompt": row["next_prompt"],
            "resource_plan": json.loads(row["resource_plan_json"]),
            "blueprint": json.loads(row["blueprint_json"])
            if row["blueprint_json"]
            else None,
            "diagnostics": json.loads(row["diagnostics_json"]),
            "missing_capabilities": json.loads(row["missing_capabilities_json"]),
            "candidate": _identity(row),
            "revision": row["revision"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "messages": [
                {
                    "schema_version": "1.0",
                    "message_id": message["message_id"],
                    "sequence": message["sequence"],
                    "role": message["role"],
                    "content": message["content"],
                    "created_at": message["created_at"],
                }
                for message in messages
            ],
        }


def _identity(row: sqlite3.Row) -> dict[str, str] | None:
    keys = row.keys()
    raw = row["identity_json"] if "identity_json" in keys else "{}"
    if not raw:
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        return None
    name = str(parsed.get("name") or "").strip()
    slug = str(parsed.get("slug") or "").strip()
    if not name:
        return None
    payload = {"name": name}
    if slug:
        payload["slug"] = slug
    return payload
