import os
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from veyra_agent_platform.community.app import create_app as create_community_app
from veyra_agent_platform.community.config import CommunitySettings
from veyra_agent_platform.local.app import create_app as create_local_app
from veyra_agent_platform.local.config import LocalSettings


def test_local_and_community_have_distinct_app_factories() -> None:
    local_app = create_local_app(LocalSettings(database_url="sqlite:///:memory:"))
    community_app = create_community_app(
        CommunitySettings(database_url="sqlite:///:memory:")
    )

    assert isinstance(local_app, FastAPI)
    assert isinstance(community_app, FastAPI)
    assert local_app.title != community_app.title
    assert local_app.state.settings.service_name == "local"
    assert community_app.state.settings.service_name == "community"


def test_each_app_exposes_only_the_versioned_scaffold_health_route() -> None:
    local_paths = {route.path for route in create_local_app().routes}
    community_paths = {route.path for route in create_community_app().routes}

    expected_paths = {
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/api/v1/health",
    }
    assert local_paths == expected_paths
    assert community_paths == expected_paths


def test_local_health_reports_identity_and_database_placeholder() -> None:
    settings = LocalSettings(
        app_version="0.2.0",
        build_sha="local-test-sha",
        database_url="sqlite:///:memory:",
    )

    response = TestClient(create_local_app(settings)).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "health.v1",
        "status": "ok",
        "service": "local",
        "app_version": "0.2.0",
        "build_sha": "local-test-sha",
        "database_revision": None,
        "database_ready": False,
    }


def test_community_health_reports_identity_and_database_placeholder() -> None:
    settings = CommunitySettings(
        app_version="0.2.0",
        build_sha="community-test-sha",
        database_url="sqlite:///:memory:",
    )

    response = TestClient(create_community_app(settings)).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "health.v1",
        "status": "ok",
        "service": "community",
        "app_version": "0.2.0",
        "build_sha": "community-test-sha",
        "database_revision": None,
        "database_ready": False,
    }


def test_build_identity_can_come_from_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VEYRA_APP_VERSION", "0.3.0")
    monkeypatch.setenv("VEYRA_BUILD_SHA", "env-test-sha")

    settings = LocalSettings()

    assert settings.app_version == "0.3.0"
    assert settings.build_sha == "env-test-sha"


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.2", "example.test", "::"])
def test_local_settings_reject_non_loopback_hosts(host: str) -> None:
    with pytest.raises(ValidationError, match="local service host"):
        LocalSettings(host=host)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_local_create_app_accepts_only_supported_loopback_hosts(host: str) -> None:
    settings = LocalSettings(host=host, database_url="sqlite:///:memory:")

    application = create_local_app(settings)

    assert application.state.settings.host == host


def test_local_cli_rejects_non_loopback_before_server_launch() -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["VEYRA_LOCAL_HOST"] = "0.0.0.0"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from veyra_agent_platform.local.app import main; main()",
        ],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )

    assert result.returncode != 0
    assert "local service host" in f"{result.stdout}\n{result.stderr}"
    assert "Uvicorn running" not in f"{result.stdout}\n{result.stderr}"


def test_community_sqlite_is_allowed_only_outside_production() -> None:
    for mode in ("development", "test"):
        settings = CommunitySettings(
            mode=mode,
            database_url="sqlite:///:memory:",
        )
        assert settings.environment == mode

    with pytest.raises(ValidationError, match="explicit PostgreSQL URL"):
        CommunitySettings(mode="production", database_url="sqlite:///:memory:")


def test_community_production_accepts_psycopg_postgresql_url() -> None:
    settings = CommunitySettings(
        environment="production",
        database_url="postgresql+psycopg://db.example/app",
    )

    assert settings.mode == "production"
