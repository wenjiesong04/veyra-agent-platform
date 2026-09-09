"""Native picker invocation remains shell-free and validation-bound."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from veyra_agent_platform.local.system import directory_picker
from veyra_agent_platform.local.system.directory_picker import (
    DirectoryPickerError,
    DirectoryPickerUnsupportedError,
    MacOSDirectoryPicker,
)


def test_macos_picker_invokes_osascript_with_argv_and_validates_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    observed: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["args"] = args
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(args[0], 0, f"{selected}\n", "")

    monkeypatch.setattr(directory_picker.sys, "platform", "darwin")
    monkeypatch.setattr(directory_picker.subprocess, "run", fake_run)

    result = MacOSDirectoryPicker().select_directory()

    assert result.selected is True
    assert result.path == selected.resolve()
    assert observed["args"] == (
        [
            "osascript",
            "-e",
            'POSIX path of (choose folder with prompt "Choose a Veyra Project folder")',
        ],
    )
    assert observed["kwargs"] == {"capture_output": True, "check": False, "text": True}


def test_macos_picker_passes_default_location_only_as_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    initial = tmp_path / 'managed"projects'
    observed: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["command"] = args[0]
        return subprocess.CompletedProcess(args[0], 0, f"{selected}\n", "")

    monkeypatch.setattr(directory_picker.sys, "platform", "darwin")
    monkeypatch.setattr(directory_picker.subprocess, "run", fake_run)

    result = MacOSDirectoryPicker().select_directory(initial_directory=initial)

    command = observed["command"]
    assert isinstance(command, list)
    assert result.selected is True
    assert initial.is_dir()
    script = " ".join(
        part
        for index, part in enumerate(command)
        if index > 0 and command[index - 1] == "-e"
    )
    assert str(initial) not in script
    assert command[-2:] == ["--", str(initial.resolve())]
    assert "set startFolder to POSIX file (item 1 of argv) as alias" in script
    assert "default location startFolder" in script
    assert "choose folder" in script


def test_macos_archive_picker_filters_zip_and_rejects_unsafe_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "team.vproject.zip"
    archive.write_bytes(b"PK")
    unsafe = tmp_path / "notes.txt"
    unsafe.write_text("not a zip", encoding="utf-8")
    observed: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["command"] = args[0]
        return subprocess.CompletedProcess(args[0], 0, f"{archive}\n", "")

    monkeypatch.setattr(directory_picker.sys, "platform", "darwin")
    monkeypatch.setattr(directory_picker.subprocess, "run", fake_run)

    result = MacOSDirectoryPicker().select_archive(initial_directory=tmp_path)

    command = observed["command"]
    assert isinstance(command, list)
    script = " ".join(
        part
        for index, part in enumerate(command)
        if index > 0 and command[index - 1] == "-e"
    )
    assert result.selected is True
    assert result.path == archive.resolve()
    assert 'choose file with prompt "Choose a Veyra Project archive"' in script
    assert 'of type {"zip"}' in script
    assert command[-1] == str(tmp_path.resolve())

    monkeypatch.setattr(
        directory_picker.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["osascript"], 0, str(unsafe), ""
        ),
    )
    with pytest.raises(DirectoryPickerError, match="not a zip file"):
        MacOSDirectoryPicker().select_archive()


def test_macos_picker_treats_user_cancellation_as_not_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(directory_picker.sys, "platform", "darwin")
    monkeypatch.setattr(
        directory_picker.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["osascript"], 1, "", "User canceled. (-128)"
        ),
    )

    assert MacOSDirectoryPicker().select_directory().selected is False
    assert MacOSDirectoryPicker().select_archive().selected is False

    monkeypatch.setattr(
        directory_picker.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["osascript"], 1, "", "28:70: execution error: 用户已取消。 (-128)"
        ),
    )
    assert MacOSDirectoryPicker().select_directory().selected is False
    assert MacOSDirectoryPicker().select_archive().selected is False


def test_macos_picker_rejects_unsafe_selection_and_unsupported_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unsafe = tmp_path / "unsafe"
    unsafe.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(directory_picker.sys, "platform", "darwin")
    monkeypatch.setattr(
        directory_picker.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["osascript"], 0, str(unsafe), ""
        ),
    )
    with pytest.raises(DirectoryPickerError, match="absent or unsafe"):
        MacOSDirectoryPicker().select_directory()

    monkeypatch.setattr(directory_picker.sys, "platform", "linux")
    with pytest.raises(DirectoryPickerUnsupportedError):
        MacOSDirectoryPicker().select_directory()
    with pytest.raises(DirectoryPickerUnsupportedError):
        MacOSDirectoryPicker().select_archive()


def test_macos_picker_reveals_a_directory_with_open_r(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = tmp_path / "dddd"
    selected.mkdir()
    observed: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["args"] = args
        return subprocess.CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr(directory_picker.sys, "platform", "darwin")
    monkeypatch.setattr(directory_picker.subprocess, "run", fake_run)

    MacOSDirectoryPicker().reveal_directory(selected)

    assert observed["args"] == (["open", "-R", str(selected.resolve())],)
