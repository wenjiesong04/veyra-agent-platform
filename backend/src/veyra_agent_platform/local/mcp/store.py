"""SQLite persistence for host-side MCP server configuration."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast


class McpServerStore:
    """Keep MCP command configuration out of Project directories."""

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
        server_id: str,
        name: str,
        command: str,
        args: Sequence[str],
        env_names: dict[str, str],
        enabled: bool,
        created_at: str,
    ) -> None:
        connection.execute(
            """INSERT INTO mcp_servers(
                server_id, name, command, args_json, env_names_json, enabled,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                server_id,
                name,
                command,
                json.dumps(args, ensure_ascii=False),
                json.dumps(env_names, ensure_ascii=False, sort_keys=True),
                int(enabled),
                created_at,
                created_at,
            ),
        )

    def get(self, server_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM mcp_servers WHERE server_id = ?", (server_id,)
                ).fetchone(),
            )

    def list(self) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM mcp_servers ORDER BY created_at ASC, server_id ASC"
            ).fetchall()

    def delete(self, server_id: str) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM mcp_servers WHERE server_id = ?", (server_id,)
            )
            return cursor.rowcount > 0

    def set_enabled(
        self, server_id: str, *, enabled: bool, updated_at: str
    ) -> sqlite3.Row | None:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE mcp_servers SET enabled = ?, updated_at = ? "
                "WHERE server_id = ?",
                (int(enabled), updated_at, server_id),
            )
            if cursor.rowcount == 0:
                return None
            return cast(
                sqlite3.Row,
                connection.execute(
                    "SELECT * FROM mcp_servers WHERE server_id = ?", (server_id,)
                ).fetchone(),
            )

    def update(
        self,
        server_id: str,
        *,
        name: str,
        command: str,
        args: Sequence[str],
        env_names: dict[str, str],
        enabled: bool,
        updated_at: str,
    ) -> sqlite3.Row | None:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE mcp_servers SET name = ?, command = ?, args_json = ?, "
                "env_names_json = ?, enabled = ?, updated_at = ? "
                "WHERE server_id = ?",
                (
                    name,
                    command,
                    json.dumps(args, ensure_ascii=False),
                    json.dumps(env_names, ensure_ascii=False, sort_keys=True),
                    int(enabled),
                    updated_at,
                    server_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            return cast(
                sqlite3.Row,
                connection.execute(
                    "SELECT * FROM mcp_servers WHERE server_id = ?", (server_id,)
                ).fetchone(),
            )

    @staticmethod
    def payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "server_id": row["server_id"],
            "name": row["name"],
            "command": row["command"],
            "args": json.loads(row["args_json"]),
            "env_names": json.loads(row["env_names_json"]),
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


MappingLike = sqlite3.Row
