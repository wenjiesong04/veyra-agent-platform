from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.library import LibraryService
from veyra_agent_platform.local.library.service import DraftConflict
from veyra_agent_platform.local.projects import ProjectService
from veyra_agent_platform.local.storage import LocalRepository

ROOT = Path(__file__).resolve().parents[3]


def _sources() -> list[dict[str, object]]:
    fixtures = ROOT / "contracts" / "fixtures" / "project" / "agents"
    names = ("github-triage", "release-summary")
    return [
        json.loads((fixtures / name / "agent.vagent.yaml").read_text(encoding="utf-8"))
        for name in names
    ]


def _services(tmp_path: Path) -> tuple[ProjectService, LibraryService]:
    repository = LocalRepository(tmp_path / "app.sqlite3")
    projects = ProjectService(repository, tmp_path / "application-data" / "objects")
    return projects, LibraryService(repository, projects)


def test_create_indexes_multi_agent_project_and_reopens_without_moving(
    tmp_path: Path,
) -> None:
    projects, _ = _services(tmp_path)
    root = tmp_path / "user-selected-project"

    created = projects.create(root_path=root, name="Example", sources=_sources())
    (root / "resources" / "brief.md").write_text("brief", encoding="utf-8")
    indexed = projects.index(root)

    assert (root / "project.vproject.yaml").is_file()
    assert (root / "resources").is_dir()
    assert (root / "tests").is_dir()
    assert len(created["agents"]) == 2
    assert indexed["root_path"] == str(root.resolve())
    restarted_projects, _ = _services(tmp_path)
    reopened = restarted_projects.index(root)
    assert reopened["project_id"] == created["project_id"]
    assert reopened["root_path"] == str(root.resolve())


def test_draft_revision_etag_idempotency_and_immutable_versions(tmp_path: Path) -> None:
    projects, library = _services(tmp_path)
    created = projects.create(
        root_path=tmp_path / "project", name="Example", sources=_sources()
    )
    project_id = created["project_id"]
    agent_id = created["agents"][0]["agent_id"]
    original = library.draft(project_id, agent_id)
    changed = deepcopy(original["source"])
    changed["description"] = "Changed documentation only."

    saved = library.replace_draft(
        project_id=project_id,
        agent_id=agent_id,
        source=changed,
        expected_revision=original["revision"],
        expected_etag=original["etag"],
        idempotency_key=new_uuid7(),
    )
    with pytest.raises(DraftConflict):
        library.replace_draft(
            project_id=project_id,
            agent_id=agent_id,
            source=changed,
            expected_revision=original["revision"],
            expected_etag=original["etag"],
            idempotency_key=new_uuid7(),
        )
    first_commit = library.commit(
        project_id=project_id, agent_id=agent_id, idempotency_key=new_uuid7()
    )
    repeated_commit = library.commit(
        project_id=project_id, agent_id=agent_id, idempotency_key=new_uuid7()
    )
    assert saved["revision"] == 1
    assert first_commit["version_id"] == repeated_commit["version_id"]
    assert len(first_commit["file_hash"]) == 64
    with projects.repository._connect() as connection:
        versions = connection.execute(
            "SELECT source_text FROM agent_versions WHERE agent_id = ?", (agent_id,)
        ).fetchall()
        links = connection.execute(
            "SELECT version_id FROM agent_version_files WHERE version_id = ?",
            (first_commit["version_id"],),
        ).fetchall()
    assert len(versions) == 1
    assert len(links) == 1
    assert "Changed documentation only." in versions[0]["source_text"]


def test_external_source_change_conflicts_until_reindex(tmp_path: Path) -> None:
    projects, library = _services(tmp_path)
    created = projects.create(
        root_path=tmp_path / "project", name="Example", sources=_sources()
    )
    project_id = created["project_id"]
    agent = created["agents"][0]
    source_path = tmp_path / "project" / agent["source_path"]
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["description"] = "Edited outside Studio."
    source_path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(DraftConflict):
        library.draft(project_id, agent["agent_id"])
    projects.index(tmp_path / "project")
    with pytest.raises(DraftConflict):
        library.draft(project_id, agent["agent_id"])
