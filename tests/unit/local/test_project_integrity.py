from __future__ import annotations

import json
import shutil
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import OperationalError

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.library import LibraryService
from veyra_agent_platform.local.library.service import DraftConflict
from veyra_agent_platform.local.projects import ProjectService
from veyra_agent_platform.local.projects.service import (
    MAX_INDEXED_FILE_BYTES,
    ProjectError,
)
from veyra_agent_platform.local.storage import (
    IdempotencyConflict,
    LocalRepository,
    migrate_local_database,
)
from veyra_agent_platform.local.storage.bootstrap import HEAD_REVISION

ROOT = Path(__file__).resolve().parents[3]


def _sources() -> list[dict[str, object]]:
    fixture = ROOT / "contracts" / "fixtures" / "project" / "agents"
    return [
        json.loads((fixture / slug / "agent.vagent.yaml").read_text())
        for slug in ("github-triage", "release-summary")
    ]


def _services(tmp_path: Path) -> tuple[ProjectService, LibraryService]:
    database_path = tmp_path / "app.sqlite3"
    migrate_local_database(database_path)
    projects = ProjectService(LocalRepository(database_path), tmp_path / "objects")
    return projects, LibraryService(projects.repository, projects)


def test_only_alembic_bootstraps_schema_and_fresh_upgrade_is_repeatable(
    tmp_path: Path,
) -> None:
    fresh = tmp_path / "fresh.sqlite3"
    with pytest.raises(RuntimeError, match="has not been migrated"):
        LocalRepository(fresh)
    migrate_local_database(fresh)
    migrate_local_database(fresh)
    assert LocalRepository(fresh).projects() == []
    collision = tmp_path / "legacy-embedded-ddl.sqlite3"
    with sqlite3.connect(collision) as connection:
        connection.execute("CREATE TABLE projects (project_id TEXT PRIMARY KEY)")
    with pytest.raises(OperationalError, match="already exists"):
        migrate_local_database(collision)


def test_lifecycle_migration_empty_and_upgrade_identity(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh.sqlite3"
    migrate_local_database(fresh)
    with sqlite3.connect(fresh) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (HEAD_REVISION,)
        assert "removed_at" in {
            row[1] for row in connection.execute("PRAGMA table_info(projects)")
        }

    upgraded = tmp_path / "upgraded.sqlite3"
    config = Config("backend/migrations/local/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{upgraded}")
    command.upgrade(config, "local_0004_project_metadata")
    migrate_local_database(upgraded)
    with sqlite3.connect(upgraded) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (HEAD_REVISION,)

    from_0005 = tmp_path / "from-0005.sqlite3"
    config.set_main_option("sqlalchemy.url", f"sqlite:///{from_0005}")
    command.upgrade(config, "local_0005_project_lifecycle")
    migrate_local_database(from_0005)
    with sqlite3.connect(from_0005) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (HEAD_REVISION,)
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'runtime_runs'"
        ).fetchone() == ("runtime_runs",)


def test_managed_delete_rolls_back_move_when_database_marking_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "app.sqlite3"
    migrate_local_database(database_path)
    managed_root = tmp_path / "application-data" / "projects"
    projects = ProjectService(
        LocalRepository(database_path),
        tmp_path / "objects",
        project_storage_root=managed_root,
    )
    created = projects.create_managed(name="Rollback")
    root = Path(created["root_path"])
    monkeypatch.setattr(projects.repository, "remove_project", lambda *_: False)

    with pytest.raises(ProjectError, match="unknown Project"):
        projects.remove(created["project_id"])

    assert root.is_dir()
    assert not (
        managed_root.parent / "trash" / "projects" / created["project_id"]
    ).exists()


def test_failed_duplicate_name_index_restores_external_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, _ = _services(tmp_path)
    projects.create(root_path=tmp_path / "first", name="Duplicate")
    projects.create(root_path=tmp_path / "second", name="Other")
    manifest_path = tmp_path / "second" / "project.vproject.yaml"
    manifest = json.loads(manifest_path.read_text())
    manifest["name"] = "Duplicate"
    original_text = json.dumps(manifest)
    manifest_path.write_text(original_text, encoding="utf-8")
    monkeypatch.setattr(
        projects,
        "_collect_allowed_files",
        lambda *_: (_ for _ in ()).throw(OSError("index unavailable")),
    )

    with pytest.raises(OSError, match="index unavailable"):
        projects.index(tmp_path / "second")

    assert manifest_path.read_text(encoding="utf-8") == original_text


def test_template_projects_fork_agent_identities_and_write_agent_scaffolding(
    tmp_path: Path,
) -> None:
    projects, _ = _services(tmp_path)
    first = projects.create(root_path=tmp_path / "one", name="One", sources=_sources())
    second = projects.create(root_path=tmp_path / "two", name="Two", sources=_sources())

    assert {item["agent_id"] for item in first["agents"]}.isdisjoint(
        {item["agent_id"] for item in second["agents"]}
    )
    assert len(projects.repository.agents(first["project_id"])) == 2
    for agent in first["agents"]:
        root = tmp_path / "one" / agent["source_path"]
        assert (root.parent / "README.md").is_file()
        assert (root.parent / "tests").is_dir()


def test_empty_project_creates_required_layout_and_reopens(tmp_path: Path) -> None:
    projects, _ = _services(tmp_path)
    root = tmp_path / "empty"

    created = projects.create(root_path=root, name="Empty")

    manifest = json.loads((root / "project.vproject.yaml").read_text())
    assert manifest["agents"] == []
    assert manifest["default_agent_id"] is None
    assert (root / "agents").is_dir()
    assert (root / "resources").is_dir()
    assert (root / "tests").is_dir()
    assert created["agent_count"] == 0
    assert created["agents"] == []
    assert created["indexed_at"]
    assert projects.index(root)["project_id"] == created["project_id"]


def test_legacy_manifest_without_description_indexes_as_empty(tmp_path: Path) -> None:
    projects, _ = _services(tmp_path)
    root = tmp_path / "legacy"
    created = projects.create(root_path=root, name="Legacy", description="Retained")
    manifest_path = root / "project.vproject.yaml"
    manifest = json.loads(manifest_path.read_text())
    del manifest["description"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    indexed = projects.index(root)

    assert created["description"] == "Retained"
    assert indexed["description"] == ""


def test_index_reconciles_unversioned_manifest_removal_and_rejects_duplicate_copy(
    tmp_path: Path,
) -> None:
    projects, library = _services(tmp_path)
    created = projects.create(
        root_path=tmp_path / "one", name="One", sources=_sources()
    )
    project_id = created["project_id"]
    manifest_path = tmp_path / "one" / "project.vproject.yaml"
    manifest = json.loads(manifest_path.read_text())
    removed = manifest["agents"].pop()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    summary = projects.index(tmp_path / "one")
    assert {item["agent_id"] for item in summary["agents"]} == {
        manifest["agents"][0]["agent_id"]
    }
    copied = tmp_path / "copied"
    shutil.copytree(tmp_path / "one", copied)
    with pytest.raises(ProjectError, match="duplicate Project ID"):
        projects.index(copied)
    first_agent = summary["agents"][0]["agent_id"]
    draft = library.draft(project_id, first_agent)
    library.commit(
        project_id=project_id,
        agent_id=first_agent,
        expected_revision=draft["revision"],
        expected_etag=draft["etag"],
        idempotency_key=new_uuid7(),
    )
    manifest["agents"] = [removed]
    manifest["default_agent_id"] = removed["agent_id"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ProjectError, match="immutable versions"):
        projects.index(tmp_path / "one")
    assert removed["agent_id"] not in {item["agent_id"] for item in summary["agents"]}


def test_index_excludes_git_and_rejects_oversized_allowed_file(tmp_path: Path) -> None:
    projects, _ = _services(tmp_path)
    created = projects.create(
        root_path=tmp_path / "project", name="One", sources=_sources()
    )
    git_file = tmp_path / "project" / ".git" / "objects" / "payload"
    git_file.parent.mkdir(parents=True)
    git_file.write_bytes(b"not indexed")
    projects.index(tmp_path / "project")
    with projects.repository._connect() as connection:
        git_rows = connection.execute(
            """SELECT relative_path FROM files
               WHERE project_id = ? AND relative_path LIKE '.git%'""",
            (created["project_id"],),
        ).fetchall()
    assert git_rows == []
    (tmp_path / "project" / "resources" / "too-big.txt").write_bytes(
        b"x" * (MAX_INDEXED_FILE_BYTES + 1)
    )
    with pytest.raises(ProjectError, match="size limit"):
        projects.index(tmp_path / "project")


def test_atomic_create_failure_leaves_no_target_or_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, _ = _services(tmp_path)

    def fail_write(_: Path, __: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(projects, "atomic_write", fail_write)
    target = tmp_path / "target"
    with pytest.raises(OSError, match="disk full"):
        projects.create(root_path=target, name="One", sources=_sources())
    assert not target.exists()
    assert not list(tmp_path.glob(".target.veyra-staging-*"))


def test_agent_install_failure_restores_manifest_and_agent_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, _ = _services(tmp_path)
    created = projects.create(root_path=tmp_path / "project", name="One")
    root = Path(created["root_path"])
    manifest_path = root / "project.vproject.yaml"
    previous_manifest = manifest_path.read_text(encoding="utf-8")

    def fail_index(_: Path) -> dict[str, object]:
        raise OSError("index unavailable")

    monkeypatch.setattr(projects, "index", fail_index)
    with pytest.raises(OSError, match="index unavailable"):
        projects.create_agent(project_id=created["project_id"], mode="blank")

    assert manifest_path.read_text(encoding="utf-8") == previous_manifest
    assert list((root / "agents").iterdir()) == []
    assert projects.repository.agents(created["project_id"]) == []


def test_create_accepts_existing_empty_directory_and_refuses_nonempty_root(
    tmp_path: Path,
) -> None:
    projects, _ = _services(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()

    created = projects.create(root_path=empty, name="Empty", sources=_sources())

    assert created["project_id"]
    assert (empty / "project.vproject.yaml").is_file()

    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    preserved = nonempty / "not-a-project.txt"
    preserved.write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(ProjectError, match="not empty"):
        projects.create(root_path=nonempty, name="No")
    assert preserved.read_text(encoding="utf-8") == "do not overwrite"


def test_create_failure_restores_preexisting_empty_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, _ = _services(tmp_path)
    target = tmp_path / "empty"
    target.mkdir()

    def fail_index(_: Path) -> dict[str, object]:
        raise OSError("index unavailable")

    monkeypatch.setattr(projects, "index", fail_index)
    with pytest.raises(OSError, match="index unavailable"):
        projects.create(root_path=target, name="One", sources=_sources())

    assert target.is_dir()
    assert not target.is_symlink()
    assert list(target.iterdir()) == []
    assert not list(tmp_path.glob(".empty.veyra-staging-*"))


def test_reload_accepts_external_edit_and_divergent_idempotency_conflicts(
    tmp_path: Path,
) -> None:
    projects, library = _services(tmp_path)
    created = projects.create(
        root_path=tmp_path / "project", name="One", sources=_sources()
    )
    agent = created["agents"][0]
    project_id, agent_id = created["project_id"], agent["agent_id"]
    draft = library.draft(project_id, agent_id)
    first = deepcopy(draft["source"])
    first["description"] = "first"
    key = new_uuid7()
    library.replace_draft(
        project_id=project_id,
        agent_id=agent_id,
        source=first,
        expected_revision=draft["revision"],
        expected_etag=draft["etag"],
        idempotency_key=key,
    )
    second = deepcopy(first)
    second["description"] = "different request"
    with pytest.raises(IdempotencyConflict):
        library.replace_draft(
            project_id=project_id,
            agent_id=agent_id,
            source=second,
            expected_revision=draft["revision"],
            expected_etag=draft["etag"],
            idempotency_key=key,
        )
    source_path = tmp_path / "project" / agent["source_path"]
    external = json.loads(source_path.read_text())
    external["description"] = "external"
    source_path.write_text(json.dumps(external), encoding="utf-8")
    with pytest.raises(DraftConflict):
        library.draft(project_id, agent_id)
    reloaded = library.reload_from_disk(project_id, agent_id)
    assert reloaded["source"]["description"] == "external"
