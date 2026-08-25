"""Alembic environment for the separate Community database."""

from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from veyra_agent_platform.community.config import CommunitySettings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _database_url() -> str:
    return CommunitySettings().database_url.replace("+aiosqlite", "")


def _ensure_sqlite_parent(database_url: str) -> None:
    parsed_url = make_url(database_url)
    if parsed_url.get_backend_name() != "sqlite" or not parsed_url.database:
        return
    if parsed_url.database == ":memory:":
        return
    Path(parsed_url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)


def run_migrations_offline() -> None:
    database_url = _database_url()
    context.configure(
        url=database_url,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    database_url = _database_url()
    _ensure_sqlite_parent(database_url)
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = database_url
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
