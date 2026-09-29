from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veyra_agent_platform.local import config
from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings


def test_acceptance_client_does_not_write_user_project_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_root = tmp_path / "platform-data" / "Veyra Agent Platform"
    monkeypatch.setattr(
        config,
        "user_data_dir",
        lambda *_args, **_kwargs: str(user_root),
    )
    isolated_projects = tmp_path / "isolated-projects"
    isolated_db = tmp_path / "app.sqlite3"
    settings = LocalSettings(
        database_url=f"sqlite:///{isolated_db}",
        project_storage_root=isolated_projects,
    )
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/v1/projects", json={"name": "Acceptance fixture"})
        assert created.status_code == 201, created.text
    user_projects = user_root / "v1" / "projects"
    assert not user_projects.exists() or not any(user_projects.rglob("*"))
    assert any(isolated_projects.iterdir())
