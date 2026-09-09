"""Native folder and archive selection with strict validation of returned paths."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

_FOLDER_PROMPT = "Choose a Veyra Project folder"
_ARCHIVE_PROMPT = "Choose a Veyra Project archive"
_PICKER_FOLDER_FAILED = (
    "The folder picker could not be opened. Allow disk access and try again."
)
_PICKER_ARCHIVE_FAILED = (
    "The archive picker could not be opened. Choose a .zip or .vproject.zip file."
)
_REVEAL_FAILED = "The Project folder could not be shown in the file manager."


class DirectoryPickerError(RuntimeError):
    """The native folder picker could not complete."""


class DirectoryPickerUnsupportedError(DirectoryPickerError):
    """The current platform has no supported native picker."""


@dataclass(frozen=True)
class DirectorySelection:
    """A validated native folder selection, or an explicit cancellation."""

    selected: bool
    path: Path | None = None

    @classmethod
    def cancelled(cls) -> DirectorySelection:
        return cls(selected=False)

    @classmethod
    def from_path(cls, value: str | Path) -> DirectorySelection:
        path = Path(value).expanduser()
        if not path.is_dir() or path.is_symlink():
            raise DirectoryPickerError("selected directory is absent or unsafe")
        return cls(selected=True, path=path.resolve(strict=True))


@dataclass(frozen=True)
class FileSelection:
    """A validated native archive selection, or an explicit cancellation."""

    selected: bool
    path: Path | None = None

    @classmethod
    def cancelled(cls) -> FileSelection:
        return cls(selected=False)

    @classmethod
    def from_archive(cls, value: str | Path) -> FileSelection:
        path = Path(value).expanduser()
        if path.is_symlink() or not path.is_file():
            raise DirectoryPickerError("selected archive is absent or unsafe")
        name = path.name.lower()
        if not name.endswith(".zip"):
            raise DirectoryPickerError("selected archive is not a zip file")
        return cls(selected=True, path=path.resolve(strict=True))


class DirectoryPicker(Protocol):
    """A picker dependency that the application factory can replace in tests."""

    def select_directory(
        self, *, initial_directory: Path | None = None
    ) -> DirectorySelection: ...

    def select_archive(
        self, *, initial_directory: Path | None = None
    ) -> FileSelection: ...

    def reveal_directory(self, path: Path) -> None: ...


class MacOSDirectoryPicker:
    """Open the macOS chooser through osascript without a shell."""

    def select_directory(
        self, *, initial_directory: Path | None = None
    ) -> DirectorySelection:
        selection = self._choose("folder", initial_directory)
        assert isinstance(selection, DirectorySelection)
        return selection

    def select_archive(self, *, initial_directory: Path | None = None) -> FileSelection:
        selection = self._choose("file", initial_directory)
        assert isinstance(selection, FileSelection)
        return selection

    def reveal_directory(self, path: Path) -> None:
        if sys.platform != "darwin":
            raise DirectoryPickerUnsupportedError("directory picker is unsupported")
        target = Path(path).expanduser()
        if target.is_symlink() or not target.exists():
            raise DirectoryPickerError("selected Project directory is absent or unsafe")
        resolved = target.resolve(strict=True)
        completed = subprocess.run(
            ["open", "-R", str(resolved)],
            capture_output=True,
            check=False,
            text=True,
        )
        if completed.returncode != 0:
            raise DirectoryPickerError(_REVEAL_FAILED)

    def _choose(
        self,
        kind: Literal["folder", "file"],
        initial_directory: Path | None,
    ) -> DirectorySelection | FileSelection:
        if sys.platform != "darwin":
            raise DirectoryPickerUnsupportedError("directory picker is unsupported")
        completed = subprocess.run(
            _osascript_command(kind, _usable_initial_directory(initial_directory)),
            capture_output=True,
            check=False,
            text=True,
        )
        if completed.returncode != 0:
            if _osascript_was_cancelled(completed.stdout, completed.stderr):
                return (
                    FileSelection.cancelled()
                    if kind == "file"
                    else DirectorySelection.cancelled()
                )
            raise DirectoryPickerError(
                _PICKER_ARCHIVE_FAILED if kind == "file" else _PICKER_FOLDER_FAILED
            )
        raw = completed.stdout.strip()
        if kind == "file":
            return FileSelection.from_archive(raw)
        return DirectorySelection.from_path(raw)


def _osascript_was_cancelled(stdout: str, stderr: str) -> bool:
    """Recognize AppleScript user-cancel, including localized macOS wording."""
    combined = f"{stdout}\n{stderr}"
    message = combined.casefold()
    return (
        "(-128)" in message
        or "user canceled" in message
        or "user cancelled" in message
        or "用户已取消" in combined
    )


def _usable_initial_directory(path: Path | None) -> Path | None:
    """Create and return a chooser start folder, or omit it when unusable."""
    if path is None:
        return None
    candidate = Path(path).expanduser()
    try:
        candidate.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    try:
        if not candidate.is_dir():
            return None
    except OSError:
        return None
    try:
        return candidate.resolve()
    except OSError:
        return None


def _osascript_command(
    kind: Literal["folder", "file"], initial_directory: Path | None
) -> list[str]:
    """Build argv-only osascript invocation; paths never enter the script text."""
    prompt = _ARCHIVE_PROMPT if kind == "file" else _FOLDER_PROMPT
    verb = "file" if kind == "file" else "folder"
    type_filter = ' of type {"zip"}' if kind == "file" else ""
    choose = f'choose {verb} with prompt "{prompt}"{type_filter}'
    if initial_directory is None:
        return ["osascript", "-e", f"POSIX path of ({choose})"]
    return [
        "osascript",
        "-e",
        "on run argv",
        "-e",
        "set startFolder to POSIX file (item 1 of argv) as alias",
        "-e",
        f"return POSIX path of ({choose} default location startFolder)",
        "-e",
        "end run",
        "--",
        str(initial_directory),
    ]
