"""Managed Project storage stays application-data-relative, not a hardcoded path."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.projects import ProjectService
from veyra_agent_platform.local.projects.service import ProjectError
from veyra_agent_platform.local.storage import LocalRepository, migrate_local_database


def _projects(tmp_path: Path) -> tuple[ProjectService, Path]:
    database_path = tmp_path / "app.sqlite3"
    migrate_local_database(database_path)
    storage_root = tmp_path / "application-data" / "projects"
    projects = ProjectService(
        LocalRepository(database_path),
        tmp_path / "application-data" / "objects",
        project_storage_root=storage_root,
    )
    return projects, storage_root


def test_managed_create_uses_the_display_name_as_the_folder(
    tmp_path: Path,
) -> None:
    projects, storage_root = _projects(tmp_path)

    created = projects.create_managed(name="Inside")
    row = projects.repository.project(created["project_id"])
    root = Path(created["root_path"])

    assert row is not None
    assert root.name == "Inside"
    assert root.is_relative_to(storage_root)
    assert row["root_path"] == "Inside"
    assert not Path(row["root_path"]).is_absolute()
    assert (storage_root / "Inside" / "project.vproject.yaml").is_file()


def test_managed_create_sanitizes_folder_unsafe_display_names(
    tmp_path: Path,
) -> None:
    projects, storage_root = _projects(tmp_path)

    created = projects.create_managed(name="a/b:c*d")
    root = Path(created["root_path"])

    assert created["name"] == "abcd"
    assert root.name == "abcd"
    assert root.is_relative_to(storage_root)


def test_edit_renames_the_managed_folder_to_match_the_display_name(
    tmp_path: Path,
) -> None:
    projects, storage_root = _projects(tmp_path)
    created = projects.create_managed(name="Before")

    edited = projects.edit(created["project_id"], name="After")
    row = projects.repository.project(created["project_id"])

    assert Path(edited["root_path"]).name == "After"
    assert Path(edited["root_path"]).is_relative_to(storage_root)
    assert not (storage_root / "Before").exists()
    assert (storage_root / "After" / "project.vproject.yaml").is_file()
    assert row is not None
    assert row["root_path"] == "After"
    assert row["name"] == "After"


def test_open_indexes_an_external_folder_in_place(tmp_path: Path) -> None:
    projects, storage_root = _projects(tmp_path)
    external = tmp_path / "Downloads" / "test"
    external.parent.mkdir()
    created = projects.create(
        root_path=external, name="test", description="from downloads"
    )
    opened = projects.index(external)

    assert opened["project_id"] == created["project_id"]
    assert opened["name"] == "test"
    assert Path(opened["root_path"]) == external.resolve()
    assert not Path(opened["root_path"]).is_relative_to(storage_root)
    assert (external / "project.vproject.yaml").is_file()
    row = projects.repository.project(opened["project_id"])
    assert row is not None
    assert Path(row["root_path"]) == external.resolve()

    again = projects.index(external)
    assert Path(again["root_path"]) == external.resolve()


def test_reconcile_renames_legacy_uuid_folders_and_leaves_external_projects(
    tmp_path: Path,
) -> None:
    projects, storage_root = _projects(tmp_path)
    created = projects.create_managed(name="legacy")
    legacy_root = Path(created["root_path"])
    uuid_root = storage_root / f"project-{new_uuid7()}"
    os.replace(legacy_root, uuid_root)
    with projects.repository.transaction() as connection:
        connection.execute(
            "UPDATE projects SET root_path = ? WHERE project_id = ?",
            (uuid_root.name, created["project_id"]),
        )
    external = tmp_path / "Downloads" / "outside"
    external.parent.mkdir()
    outside = projects.create(root_path=external, name="outside")

    projects.reconcile_managed_storage()
    managed_row = projects.repository.project(created["project_id"])
    managed = projects.project_summary(created["project_id"])
    external_row = projects.repository.project(outside["project_id"])
    external_summary = projects.project_summary(outside["project_id"])

    assert managed_row is not None
    assert managed_row["root_path"] == "legacy"
    assert Path(managed["root_path"]).name == "legacy"
    assert Path(managed["root_path"]).is_relative_to(storage_root)
    assert not uuid_root.exists()
    assert (storage_root / "legacy" / "project.vproject.yaml").is_file()
    assert external_row is not None
    assert Path(external_row["root_path"]) == external.resolve()
    assert Path(external_summary["root_path"]) == external.resolve()
    assert (external / "project.vproject.yaml").is_file()


def test_index_rejects_a_project_subfolder_without_mutating_it(tmp_path: Path) -> None:
    projects, _storage_root = _projects(tmp_path)
    created = projects.create_managed(name="Inside")
    nested = Path(created["root_path"]) / "assets"
    before = {path.name for path in nested.iterdir()}

    with pytest.raises(ProjectError, match="not a Veyra Project") as caught:
        projects.index(nested)

    assert caught.value.code == "not_a_project"
    assert not (nested / "agents").exists()
    assert not (nested / "project.vproject.yaml").exists()
    assert {path.name for path in nested.iterdir()} == before
