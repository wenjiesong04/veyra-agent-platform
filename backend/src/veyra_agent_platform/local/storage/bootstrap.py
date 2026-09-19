"""Explicit Alembic bootstrap and schema-head verification for local SQLite."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

HEAD_REVISION = "local_0021_builder_operation_events"
_MIGRATIONS = Path(__file__).resolve().parents[4] / "migrations" / "local"


def _remove_sqlite_sidecars(database_path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        Path(f"{database_path}{suffix}").unlink(missing_ok=True)


def _schema_head(database_path: Path) -> str | None:
    if not database_path.is_file():
        return None
    with sqlite3.connect(database_path, timeout=5) as connection:
        try:
            row = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
        except sqlite3.Error:
            return None
    if row is None:
        return None
    value = row[0]
    return str(value) if value is not None else None


def migrate_local_database(database_path: Path) -> None:
    """Upgrade an application-owned SQLite file to the only supported schema head."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if _schema_head(database_path) == HEAD_REVISION:
        require_schema_head(database_path)
        return
    backup_path = database_path.with_suffix(database_path.suffix + ".pre-migration")
    had_database = database_path.is_file()
    if had_database:
        with sqlite3.connect(database_path, timeout=30) as connection:
            connection.execute("PRAGMA wal_checkpoint(FULL)")
        shutil.copy2(database_path, backup_path)
    config = Config(str(_MIGRATIONS / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    try:
        command.upgrade(config, "head")
    except Exception:
        if had_database:
            _remove_sqlite_sidecars(database_path)
            shutil.copy2(backup_path, database_path)
        else:
            database_path.unlink(missing_ok=True)
        _remove_sqlite_sidecars(database_path)
        raise
    require_schema_head(database_path)


def require_schema_head(database_path: Path) -> None:
    """Fail closed rather than letting repositories operate on an unknown schema."""
    if not database_path.is_file():
        raise RuntimeError("local SQLite database has not been migrated")
    with sqlite3.connect(database_path, timeout=5) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    if row is None or row[0] != HEAD_REVISION:
        raise RuntimeError(
            "local SQLite database is not at the required migration head"
        )
