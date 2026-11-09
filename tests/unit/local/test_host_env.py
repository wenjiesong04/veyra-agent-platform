from __future__ import annotations

from pathlib import Path

from veyra_agent_platform.local.host_env import load_host_process_env


def test_host_env_loads_repo_root_without_overriding_or_reading_project_env(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / ".env").write_text(
        "MOONSHOT_API_KEY=sk-host\nALREADY_SET=from-file\n",
        encoding="utf-8",
    )
    project_env = tmp_path / "projects" / "project-1" / ".env"
    project_env.parent.mkdir(parents=True)
    project_env.write_text("MOONSHOT_API_KEY=sk-project\n", encoding="utf-8")
    environ = {"ALREADY_SET": "keep-me"}

    loaded = load_host_process_env(environ=environ, repo_root=tmp_path)

    assert loaded == tmp_path / ".env"
    assert environ["MOONSHOT_API_KEY"] == "sk-host"
    assert environ["ALREADY_SET"] == "keep-me"
