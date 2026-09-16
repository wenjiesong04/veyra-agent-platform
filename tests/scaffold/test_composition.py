import os
import subprocess
import sys
from pathlib import Path

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


def test_each_app_exposes_its_versioned_routes(tmp_path: Path) -> None:
    local_paths = {
        route.path
        for route in create_local_app(
            LocalSettings(database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}")
        ).routes
    }
    community_paths = {route.path for route in create_community_app().routes}

    shared_paths = {
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/api/v1/health",
    }
    expected_local_paths = shared_paths | {
        "/api/v1/projects/{project_id}/agents/{agent_id}/versions",
        "/api/v1/projects/{project_id}/workflows/{workflow_id}/versions",
        "/api/v1/projects/{project_id}/workflows/{workflow_id}/run",
        "/api/v1/projects/{project_id}/workflows/{workflow_id}/runtime-readiness",
        "/api/v1/projects/{project_id}/workflows/{workflow_id}/runs",
        "/api/v1/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}",
        "/api/v1/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}/commands",
        "/api/v1/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}/events",
        "/api/v1/projects",
        "/api/v1/projects/open",
        "/api/v1/projects/import",
        "/api/v1/projects/import-path",
        "/api/v1/agent-imports",
        "/api/v1/agent-imports/{import_id}",
        "/api/v1/agent-imports/{import_id}/apply",
        "/api/v1/projects/{project_id}",
        "/api/v1/projects/{project_id}/export",
        "/api/v1/projects/{project_id}/resources",
        "/api/v1/projects/{project_id}/resources/{resource_id}/versions/{version}",
        "/api/v1/projects/{project_id}/files",
        "/api/v1/projects/{project_id}/files/content",
        "/api/v1/projects/{project_id}/agent-templates",
        "/api/v1/projects/{project_id}/agents",
        "/api/v1/projects/{project_id}/agents/import",
        "/api/v1/projects/{project_id}/agents/{agent_id}",
        "/api/v1/projects/{project_id}/agents/{agent_id}/draft",
        "/api/v1/projects/{project_id}/agents/{agent_id}/draft/reload",
        "/api/v1/projects/{project_id}/agents/{agent_id}/validate",
        "/api/v1/projects/{project_id}/agents/{agent_id}/commit",
        "/api/v1/projects/{project_id}/agents/{agent_id}/export",
        "/api/v1/projects/{project_id}/workflows",
        "/api/v1/projects/{project_id}/workflows/{workflow_id}",
        "/api/v1/projects/{project_id}/workflows/{workflow_id}/draft",
        "/api/v1/projects/{project_id}/workflows/{workflow_id}/draft/reload",
        "/api/v1/projects/{project_id}/workflows/{workflow_id}/validate",
        "/api/v1/projects/{project_id}/workflows/{workflow_id}/commit",
        "/api/v1/projects/{project_id}/knowledge",
        "/api/v1/projects/{project_id}/knowledge/ingest",
        "/api/v1/projects/{project_id}/knowledge/{knowledge_id}",
        "/api/v1/projects/{project_id}/knowledge/{knowledge_id}/index",
        "/api/v1/projects/{project_id}/knowledge/{knowledge_id}/chunks/{chunk_id}",
        "/api/v1/components",
        "/api/v1/resources",
        "/api/v1/resources/drafts",
        "/api/v1/resources/{resource_id}/versions/{version}",
        "/api/v1/resources/{resource_id}/versions/{version}/approve",
        "/api/v1/plugins",
        "/api/v1/plugins/trash",
        "/api/v1/plugins/trash/{trash_id}/restore",
        "/api/v1/plugins/import",
        "/api/v1/plugins/{plugin_id}/versions/{version}/activate",
        "/api/v1/plugins/{plugin_id}/versions/{version}/disable",
        "/api/v1/plugins/{plugin_id}/versions/{version}/uninstall",
        "/api/v1/plugins/{plugin_id}/versions/{version}/download",
        "/api/v1/secrets",
        "/api/v1/secrets/{secret_ref}",
        "/api/v1/mcp/servers",
        "/api/v1/mcp/servers/import",
        "/api/v1/mcp/servers/{server_id}",
        "/api/v1/mcp/servers/{server_id}/discover",
        "/api/v1/mcp/servers/{server_id}/readiness",
        "/api/v1/mcp/servers/{server_id}/tools/{resource_id}/versions/{version}/approve",
        "/api/v1/projects/{project_id}/work-items",
        "/api/v1/work-items/{work_item_id}",
        "/api/v1/work-items/{work_item_id}/dispatch",
        "/api/v1/work-items/{work_item_id}/retry",
        "/api/v1/work-items/{work_item_id}/cancel",
        "/api/v1/work-items/{work_item_id}/recover",
        "/api/v1/orchestrator/status",
        "/api/v1/projects/{project_id}/agents/{agent_id}/run",
        "/api/v1/projects/{project_id}/agents/{agent_id}/conversations",
        "/api/v1/projects/{project_id}/agents/{agent_id}/conversations/{conversation_id}",
        "/api/v1/projects/{project_id}/agents/{agent_id}/runs",
        "/api/v1/projects/{project_id}/agents/{agent_id}/runs/{run_id}",
        "/api/v1/projects/{project_id}/agents/{agent_id}/runs/{run_id}/commands",
        "/api/v1/projects/{project_id}/agents/{agent_id}/runs/{run_id}/events",
        "/api/v1/projects/{project_id}/runtime-profile",
        "/api/v1/projects/{project_id}/agents/{agent_id}/runtime-profile",
        "/api/v1/projects/{project_id}/agents/{agent_id}/runtime-readiness",
        "/api/v1/projects/{project_id}/factory/sessions",
        "/api/v1/projects/{project_id}/factory/sessions/{session_id}",
        "/api/v1/projects/{project_id}/factory/sessions/{session_id}/messages",
        "/api/v1/projects/{project_id}/factory/sessions/{session_id}/generate",
        "/api/v1/projects/{project_id}/factory/sessions/{session_id}/apply-draft",
        "/api/v1/projects/{project_id}/edit-proposals",
        "/api/v1/projects/{project_id}/builder/resolve",
        "/api/v1/projects/{project_id}/edit-proposals/{proposal_id}",
        "/api/v1/projects/{project_id}/edit-proposals/{proposal_id}/commands",
        "/api/v1/system/select-directory",
        "/api/v1/system/select-archive",
        "/api/v1/system/reveal-project",
        "/api/v1/factory/status",
        "/api/v1/runtime/status",
        "/api/v1/runtime/profile/validate",
    }
    assert local_paths == expected_local_paths
    assert community_paths == shared_paths | {
        "/api/v1/ready",
        "/api/v1/auth/verification-codes",
        "/api/v1/auth/registration-code",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/password-reset/request",
        "/api/v1/auth/password-reset/confirm",
        "/api/v1/account/me",
        "/api/v1/account/profile",
        "/api/v1/account/avatar",
        "/api/v1/account/sessions",
        "/api/v1/account/sessions/{session_id}",
        "/api/v1/avatars/{user_id}",
        "/api/v1/registry/agents",
        "/api/v1/registry/moderation/queue",
        "/api/v1/registry/agents/{owner_handle}/{slug}",
        "/api/v1/registry/agents/{owner_handle}/{slug}/versions",
        "/api/v1/registry/agents/{owner_handle}/{slug}/versions/{version}",
        "/api/v1/registry/agents/{owner_handle}/{slug}/versions/{version}/download",
        "/api/v1/registry/agents/{owner_handle}/{slug}/versions/{version}/moderate",
        "/api/v1/registry/agents/{owner_handle}/{slug}/versions/{version}/star",
        "/api/v1/registry/agents/{owner_handle}/{slug}/versions/{version}/reviews",
        "/api/v1/registry/agents/{owner_handle}/{slug}/versions/{version}/report",
        "/api/v1/registry/plugins",
        "/api/v1/registry/plugins/moderation/queue",
        "/api/v1/registry/plugins/{owner_handle}/{slug}",
        "/api/v1/registry/plugins/{owner_handle}/{slug}/versions",
        "/api/v1/registry/plugins/{owner_handle}/{slug}/versions/{version}",
        "/api/v1/registry/plugins/{owner_handle}/{slug}/versions/{version}/download",
        "/api/v1/registry/plugins/{owner_handle}/{slug}/versions/{version}/moderate",
    }


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
        "status": "starting",
        "service": "local",
        "app_version": "0.2.0",
        "build_sha": "local-test-sha",
        "database_revision": None,
        "database_ready": False,
    }


def test_community_health_reports_unstarted_database_state() -> None:
    settings = CommunitySettings(
        app_version="0.2.0",
        build_sha="community-test-sha",
        database_url="sqlite:///:memory:",
    )

    response = TestClient(create_community_app(settings)).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "health.v1",
        "status": "starting",
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


def test_settings_do_not_read_a_malicious_cwd_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "VEYRA_LOCAL_HOST=0.0.0.0\n"
        "VEYRA_ENVIRONMENT=production\n"
        "VEYRA_COMMUNITY_DATABASE_URL=sqlite:///:memory:\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    for key in (
        "VEYRA_LOCAL_HOST",
        "VEYRA_ENVIRONMENT",
        "VEYRA_COMMUNITY_DATABASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)

    local_settings = LocalSettings()
    community_settings = CommunitySettings()

    assert local_settings.host == "127.0.0.1"
    assert local_settings.mode == "development"
    assert community_settings.mode == "development"
    assert community_settings.database_url.startswith("sqlite:///")


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


@pytest.mark.parametrize("mode", ["production", "release"])
def test_local_packaged_modes_require_concrete_build_sha(mode: str) -> None:
    for build_sha in ("unknown", ""):
        with pytest.raises(ValidationError, match="concrete VEYRA_BUILD_SHA"):
            LocalSettings(mode=mode, build_sha=build_sha)

    settings = LocalSettings(
        mode=mode,
        build_sha="release-test-sha",
        database_url="sqlite:///:memory:",
    )
    assert settings.mode == mode


def test_community_sqlite_is_allowed_only_outside_production() -> None:
    for mode in ("development", "test"):
        settings = CommunitySettings(
            mode=mode,
            database_url="sqlite:///:memory:",
        )
        assert settings.environment == mode

    with pytest.raises(ValidationError, match=r"postgresql\+psycopg://"):
        CommunitySettings(
            mode="production",
            build_sha="community-test-sha",
            database_url="sqlite:///:memory:",
        )

    with pytest.raises(ValidationError, match=r"postgresql\+psycopg://"):
        CommunitySettings(
            mode="production",
            build_sha="community-test-sha",
            database_url="postgresql://db.example/app",
        )


def test_global_environment_selects_community_production_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VEYRA_ENVIRONMENT", "production")
    monkeypatch.setenv("VEYRA_BUILD_SHA", "community-test-sha")
    monkeypatch.setenv(
        "VEYRA_COMMUNITY_DATABASE_URL",
        "postgresql+psycopg://db.example/app",
    )
    monkeypatch.setenv(
        "VEYRA_AUTH_HMAC_SECRET", "production-auth-hmac-secret-that-is-long-enough"
    )
    monkeypatch.setenv("VEYRA_COMMUNITY_ORIGIN", "https://community.veyra.example")
    monkeypatch.setenv("VEYRA_COMMUNITY_REQUIRE_MODERATION", "true")
    monkeypatch.setenv("VEYRA_COMMUNITY_MODERATOR_HANDLES", "test-moderator")
    monkeypatch.setenv("VEYRA_COMMUNITY_OBJECT_STORAGE_BACKEND", "s3")
    monkeypatch.setenv("VEYRA_COMMUNITY_S3_ENDPOINT_URL", "http://minio.example:9000")
    monkeypatch.setenv("VEYRA_COMMUNITY_S3_BUCKET", "veyra-community")
    monkeypatch.setenv("VEYRA_COMMUNITY_S3_ACCESS_KEY_ID", "test-access")
    monkeypatch.setenv(
        "VEYRA_COMMUNITY_S3_SECRET_ACCESS_KEY", "test-secret-that-is-long-enough"
    )

    settings = CommunitySettings()

    assert settings.mode == "production"


def test_community_production_accepts_psycopg_postgresql_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VEYRA_BUILD_SHA", raising=False)
    with pytest.raises(ValidationError, match="concrete VEYRA_BUILD_SHA"):
        CommunitySettings(
            mode="production",
            database_url="postgresql+psycopg://db.example/app",
        )

    settings = CommunitySettings(
        environment="production",
        build_sha="community-test-sha",
        database_url="postgresql+psycopg://db.example/app",
        auth_hmac_secret="production-auth-hmac-secret-that-is-long-enough",
        public_origin="https://community.veyra.example",
        require_moderation=True,
        moderator_handles="test-moderator",
        object_storage_backend="s3",
        s3_endpoint_url="http://minio.example:9000",
        s3_bucket="veyra-community",
        s3_access_key_id="test-access",
        s3_secret_access_key="test-secret-that-is-long-enough",
    )

    assert settings.mode == "production"
