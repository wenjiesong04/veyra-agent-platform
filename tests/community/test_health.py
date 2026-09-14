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

        readiness = client.get("/api/v1/ready")
        assert readiness.status_code == 200
        assert readiness.json() == {
            "schema_version": "readiness.v1",
            "status": "ready",
            "ready": True,
            "service": "community",
            "app_version": "0.2.0",
            "build_sha": "community-health-test",
            "database_revision": COMMUNITY_DATABASE_HEAD,
            "database_ready": True,
            "object_storage_ready": True,
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
        readiness = client.get("/api/v1/ready")
        assert readiness.status_code == 503
        assert readiness.json()["ready"] is False
        assert readiness.json()["database_ready"] is False
        assert readiness.json()["object_storage_ready"] is True
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


def test_ready_fails_closed_when_object_storage_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "migrated.sqlite3"
    _upgrade(monkeypatch, database_path, "head")
    application = create_app(_settings(database_path))

    class UnavailableStorage:
        def check_ready(self) -> bool:
            return False

    application.state.package_storage = UnavailableStorage()
    application.state.avatar_storage = UnavailableStorage()

    with TestClient(application) as client:
        response = client.get("/api/v1/ready")

        assert response.status_code == 503
        assert response.json()["status"] == "starting"
        assert response.json()["ready"] is False
        assert response.json()["database_ready"] is True
        assert response.json()["object_storage_ready"] is False
