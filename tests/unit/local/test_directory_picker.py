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
