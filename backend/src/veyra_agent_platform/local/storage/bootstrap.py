"""Explicit Alembic bootstrap and schema-head verification for local SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

HEAD_REVISION = "local_0003_project_integrity"
_MIGRATIONS = Path(__file__).resolve().parents[4] / "migrations" / "local"


def migrate_local_database(database_path: Path) -> None:
    """Upgrade an application-owned SQLite file to the only supported schema head."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    config = Config(str(_MIGRATIONS / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")
    require_schema_head(database_path)


def require_schema_head(database_path: Path) -> None:
    """Fail closed rather than letting repositories operate on an unknown schema."""
    if not database_path.is_file():
        raise RuntimeError("local SQLite database has not been migrated")
    with sqlite3.connect(database_path) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    if row is None or row[0] != HEAD_REVISION:
        raise RuntimeError(
            "local SQLite database is not at the required migration head"
        )
