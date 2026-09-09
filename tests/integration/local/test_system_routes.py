"""Contract coverage for explicitly authorized native folder selection."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.system import DirectorySelection, FileSelection
from veyra_agent_platform.local.system.directory_picker import (
    DirectoryPickerError,
    DirectoryPickerUnsupportedError,
)


class FakePicker:
    def __init__(
        self,
        selection: DirectorySelection | Exception | None = None,
        *,
        archive: FileSelection | Exception | None = None,
        reveal_error: Exception | None = None,
    ) -> None:
        self.selection = selection
        self.archive = archive
        self.reveal_error = reveal_error
        self.directory_calls: list[Path | None] = []
        self.archive_calls: list[Path | None] = []
        self.revealed: list[Path] = []

    def select_directory(
        self, *, initial_directory: Path | None = None
    ) -> DirectorySelection:
        self.directory_calls.append(initial_directory)
        if self.selection is None:
            raise AssertionError("select_directory was not configured")
        if isinstance(self.selection, Exception):
            raise self.selection
        return self.selection

    def select_archive(self, *, initial_directory: Path | None = None) -> FileSelection:
        self.archive_calls.append(initial_directory)
        if self.archive is None:
            raise AssertionError("select_archive was not configured")
        if isinstance(self.archive, Exception):
            raise self.archive
        return self.archive

    def reveal_directory(self, path: Path) -> None:
        if self.reveal_error is not None:
            raise self.reveal_error
        self.revealed.append(Path(path))


def _client(tmp_path: Path, picker: FakePicker) -> tuple[TestClient, Path]:
    storage_root = tmp_path / "projects"
    settings = LocalSettings(
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        project_storage_root=storage_root,
    )
    return TestClient(create_app(settings, directory_picker=picker)), storage_root


def _headers(
    intent: str = "select-directory", origin: str | None = None
) -> dict[str, str]:
    headers = {"X-Veyra-Desktop-Intent": intent}
    if origin is not None:
        headers["Origin"] = origin
    return headers


def test_select_directory_returns_a_typed_selected_folder(tmp_path: Path) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    picker = FakePicker(DirectorySelection.from_path(selected))
    client, _storage_root = _client(tmp_path, picker)
    with client:
        response = client.post(
            "/api/v1/system/select-directory",
            headers=_headers(origin="http://localhost:5173"),
        )

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1.0",
        "status": "selected",
        "root_path": str(selected.resolve()),
    }
    assert picker.directory_calls == [None]


def test_select_archive_returns_a_typed_selected_zip(tmp_path: Path) -> None:
    archive = tmp_path / "team.vproject.zip"
    archive.write_bytes(b"PK")
    picker = FakePicker(archive=FileSelection.from_archive(archive))
    client, _storage_root = _client(tmp_path, picker)
    with client:
        response = client.post(
            "/api/v1/system/select-archive",
            headers=_headers("select-archive", "http://127.0.0.1:5173"),
        )

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1.0",
        "status": "selected",
        "path": str(archive.resolve()),
    }
    assert picker.archive_calls == [None]


def test_select_directory_returns_a_typed_cancellation(tmp_path: Path) -> None:
    picker = FakePicker(DirectorySelection.cancelled())
    client, _storage_root = _client(tmp_path, picker)
    with client:
        response = client.post("/api/v1/system/select-directory", headers=_headers())

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1.0",
        "status": "cancelled",
        "root_path": None,
    }
    assert picker.directory_calls


def test_select_directory_forbids_missing_intent_and_untrusted_origin(
    tmp_path: Path,
) -> None:
    picker = FakePicker(DirectorySelection.cancelled())
    client, _storage_root = _client(tmp_path, picker)
    with client:
        missing_intent = client.post("/api/v1/system/select-directory")
        untrusted_origin = client.post(
            "/api/v1/system/select-directory",
            headers=_headers(origin="https://attacker.example"),
        )
        wrong_intent = client.post(
            "/api/v1/system/select-directory",
            headers=_headers("select-archive"),
        )

    assert missing_intent.status_code == 403
    assert missing_intent.json()["code"] == "desktop_intent_required"
    assert untrusted_origin.status_code == 403
    assert untrusted_origin.json()["code"] == "origin_not_allowed"
    assert wrong_intent.status_code == 403
    assert picker.directory_calls == []


def test_select_directory_returns_typed_unsupported_response(tmp_path: Path) -> None:
    picker = FakePicker(
        DirectoryPickerUnsupportedError("directory picker is unsupported")
    )
    client, _storage_root = _client(tmp_path, picker)
    with client:
        response = client.post("/api/v1/system/select-directory", headers=_headers())

    assert response.status_code == 501
    assert response.json()["schema_version"] == "1.0"
    assert response.json()["code"] == "directory_picker_unsupported"


def test_reveal_project_opens_the_indexed_folder(tmp_path: Path) -> None:
    picker = FakePicker()
    client, _storage_root = _client(tmp_path, picker)
    with client:
        created = client.post("/api/v1/projects", json={"name": "Inside"})
        response = client.post(
            "/api/v1/system/reveal-project",
            json={"project_id": created.json()["project_id"]},
            headers=_headers("reveal-project", "http://localhost:5173"),
        )

    assert created.status_code == 201
    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1.0",
        "status": "revealed",
        "root_path": created.json()["root_path"],
    }
    assert picker.revealed == [Path(created.json()["root_path"])]


def test_reveal_project_forbids_missing_intent_and_unknown_projects(
    tmp_path: Path,
) -> None:
    picker = FakePicker()
    client, _storage_root = _client(tmp_path, picker)
    with client:
        created = client.post("/api/v1/projects", json={"name": "Inside"})
        missing_intent = client.post(
            "/api/v1/system/reveal-project",
            json={"project_id": created.json()["project_id"]},
        )
        extra_path = client.post(
            "/api/v1/system/reveal-project",
            json={
                "project_id": created.json()["project_id"],
                "root_path": str(tmp_path / "outside"),
            },
            headers=_headers("reveal-project"),
        )
        unknown = client.post(
            "/api/v1/system/reveal-project",
            json={"project_id": "missing-project"},
            headers=_headers("reveal-project"),
        )

    assert missing_intent.status_code == 403
    assert extra_path.status_code == 422
    assert unknown.status_code == 422
    assert picker.revealed == []


def test_reveal_project_returns_typed_picker_failure(tmp_path: Path) -> None:
    picker = FakePicker(
        reveal_error=DirectoryPickerError("native directory picker failed")
    )
    client, _storage_root = _client(tmp_path, picker)
    with client:
        created = client.post("/api/v1/projects", json={"name": "Inside"})
        response = client.post(
            "/api/v1/system/reveal-project",
            json={"project_id": created.json()["project_id"]},
            headers=_headers("reveal-project"),
        )

    assert response.status_code == 500
    assert response.json()["code"] == "directory_picker_failed"
    assert picker.revealed == []
