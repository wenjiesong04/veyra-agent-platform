"""Community Alembic evidence for the account/auth persistence migration."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_community_migration_creates_auth_and_outbox_tables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "community-migration.sqlite3"
    monkeypatch.setenv("VEYRA_COMMUNITY_MODE", "test")
    monkeypatch.setenv("VEYRA_COMMUNITY_DATABASE_URL", f"sqlite:///{database_path}")
    config = Config("backend/migrations/community/alembic.ini")
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        table_names = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert {
        "alembic_version",
        "community_users",
        "community_verification_codes",
        "community_auth_rate_limits",
        "community_sessions",
        "community_mail_outbox",
        "community_avatars",
    } <= table_names
