"""Community readiness evidence against the Alembic revision table."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from veyra_agent_platform.community.app import (
    COMMUNITY_DATABASE_HEAD,
    create_app,
)
from veyra_agent_platform.community.config import CommunitySettings


def _upgrade(
    monkeypatch: pytest.MonkeyPatch, database_path: Path, revision: str
) -> None:
    monkeypatch.setenv("VEYRA_COMMUNITY_MODE", "test")
    monkeypatch.setenv("VEYRA_COMMUNITY_DATABASE_URL", f"sqlite:///{database_path}")
    command.upgrade(Config("backend/migrations/community/alembic.ini"), revision)


def _settings(database_path: Path) -> CommunitySettings:
    return CommunitySettings(
        mode="test",
        database_url=f"sqlite:///{database_path}",
        app_version="0.2.0",
        build_sha="community-health-test",
    )


def test_health_is_ready_at_the_required_alembic_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "migrated.sqlite3"
    _upgrade(monkeypatch, database_path, "head")
    application = create_app(_settings(database_path))

    with TestClient(application) as client:
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        assert response.json() == {
            "schema_version": "health.v1",
            "status": "ok",
            "service": "community",
            "app_version": "0.2.0",
            "build_sha": "community-health-test",
            "database_revision": COMMUNITY_DATABASE_HEAD,
            "database_ready": True,
        }

    assert application.state.database_ready is False


def test_health_is_not_ready_and_does_not_create_an_unmigrated_schema(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "unmigrated.sqlite3"
    application = create_app(_settings(database_path))

    with TestClient(application) as client:
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        assert response.json()["status"] == "starting"
        assert response.json()["database_revision"] is None
        assert response.json()["database_ready"] is False
        table_names = inspect(
            application.state.community_database.engine
        ).get_table_names()
        assert table_names == []


def test_health_reports_an_older_revision_as_not_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "behind.sqlite3"
    previous_revision = "community_0001_scaffold_baseline"
    _upgrade(monkeypatch, database_path, previous_revision)
    application = create_app(_settings(database_path))

    with TestClient(application) as client:
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        assert response.json()["status"] == "starting"
        assert response.json()["database_revision"] == previous_revision
        assert response.json()["database_ready"] is False
