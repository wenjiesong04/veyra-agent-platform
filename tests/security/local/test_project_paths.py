from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from veyra_agent_platform.local.projects import ProjectService
from veyra_agent_platform.local.projects.service import ProjectError
from veyra_agent_platform.local.storage import LocalRepository, migrate_local_database

ROOT = Path(__file__).resolve().parents[3]


def test_index_rejects_symlinked_agent_source(tmp_path: Path) -> None:
    fixture = ROOT / "contracts" / "fixtures" / "project"
    root = tmp_path / "project"
    root.mkdir()
    manifest = json.loads((fixture / "project.vproject.yaml").read_text())
    manifest["agents"] = [manifest["agents"][0]]
    manifest["default_agent_id"] = manifest["agents"][0]["agent_id"]
    (root / "project.vproject.yaml").write_text(json.dumps(manifest), encoding="utf-8")
    outside = tmp_path / "outside.vagent.yaml"
    outside.write_text(
        (fixture / "agents" / "github-triage" / "agent.vagent.yaml").read_text(),
        encoding="utf-8",
    )
    target = root / "agents" / "github-triage"
    target.mkdir(parents=True)
    os.symlink(outside, target / "agent.vagent.yaml")
    database_path = tmp_path / "app.sqlite3"
    migrate_local_database(database_path)
    projects = ProjectService(LocalRepository(database_path), tmp_path / "objects")

    with pytest.raises(ProjectError, match="symlink"):
        projects.index(root)
