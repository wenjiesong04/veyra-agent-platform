"""Contract coverage for explicitly authorized native folder selection."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from veyra_agent_platform.local.app import create_app
from veyra_agent_platform.local.config import LocalSettings
from veyra_agent_platform.local.system import DirectorySelection
from veyra_agent_platform.local.system.directory_picker import (
    DirectoryPickerUnsupportedError,
)


class FakePicker:
    def __init__(self, selection: DirectorySelection | Exception) -> None:
        self.selection = selection
        self.calls = 0

    def select_directory(self) -> DirectorySelection:
        self.calls += 1
        if isinstance(self.selection, Exception):
            raise self.selection
        return self.selection


def _client(tmp_path: Path, picker: FakePicker) -> TestClient:
    settings = LocalSettings(database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}")
    return TestClient(create_app(settings, directory_picker=picker))


def _headers(origin: str | None = None) -> dict[str, str]:
    headers = {"X-Veyra-Desktop-Intent": "select-directory"}
    if origin is not None:
        headers["Origin"] = origin
    return headers


def test_select_directory_returns_a_typed_selected_folder(tmp_path: Path) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    picker = FakePicker(DirectorySelection.from_path(selected))
    with _client(tmp_path, picker) as client:
        response = client.post(
            "/api/v1/system/select-directory", headers=_headers("http://localhost:5173")
        )

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1.0",
        "status": "selected",
        "root_path": str(selected.resolve()),
    }
    assert picker.calls == 1


def test_select_directory_returns_a_typed_cancellation(tmp_path: Path) -> None:
    picker = FakePicker(DirectorySelection.cancelled())
    with _client(tmp_path, picker) as client:
        response = client.post("/api/v1/system/select-directory", headers=_headers())

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1.0",
        "status": "cancelled",
        "root_path": None,
    }
    assert picker.calls == 1


def test_select_directory_forbids_missing_intent_and_untrusted_origin(
    tmp_path: Path,
) -> None:
    picker = FakePicker(DirectorySelection.cancelled())
    with _client(tmp_path, picker) as client:
        missing_intent = client.post("/api/v1/system/select-directory")
        untrusted_origin = client.post(
            "/api/v1/system/select-directory",
            headers=_headers("https://attacker.example"),
        )

    assert missing_intent.status_code == 403
    assert missing_intent.json()["code"] == "desktop_intent_required"
    assert untrusted_origin.status_code == 403
    assert untrusted_origin.json()["code"] == "origin_not_allowed"
    assert picker.calls == 0


def test_select_directory_returns_typed_unsupported_response(tmp_path: Path) -> None:
    picker = FakePicker(
        DirectoryPickerUnsupportedError("directory picker is unsupported")
    )
    with _client(tmp_path, picker) as client:
        response = client.post("/api/v1/system/select-directory", headers=_headers())

    assert response.status_code == 501
    assert response.json()["schema_version"] == "1.0"
    assert response.json()["code"] == "directory_picker_unsupported"
