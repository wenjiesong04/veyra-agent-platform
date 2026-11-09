from __future__ import annotations

from pathlib import Path

import pytest

from veyra_agent_platform.local import config
from veyra_agent_platform.local.config import LocalSettings


def test_local_settings_default_project_storage_root_is_application_managed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        config,
        "user_data_dir",
        lambda *_args, **_kwargs: str(
            tmp_path / "platform-data" / "Veyra Agent Platform"
        ),
    )

    settings = LocalSettings(database_url="sqlite:///:memory:")

    assert settings.project_storage_root == (
        tmp_path / "platform-data" / "Veyra Agent Platform" / "v1" / "projects"
    )


def test_local_settings_accepts_an_injected_project_storage_root(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "isolated-projects"

    settings = LocalSettings(
        database_url="sqlite:///:memory:", project_storage_root=storage_root
    )

    assert settings.project_storage_root == storage_root
