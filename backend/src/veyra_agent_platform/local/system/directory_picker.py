"""Native folder selection with strict validation of the returned path."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


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


class DirectoryPicker(Protocol):
    """A picker dependency that the application factory can replace in tests."""

    def select_directory(self) -> DirectorySelection: ...


class MacOSDirectoryPicker:
    """Open the macOS folder chooser through osascript without a shell."""

    def select_directory(self) -> DirectorySelection:
        if sys.platform != "darwin":
            raise DirectoryPickerUnsupportedError("directory picker is unsupported")
        completed = subprocess.run(
            [
                "osascript",
                "-e",
                "POSIX path of (choose folder with prompt "
                '"Choose a Veyra Project folder")',
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        if completed.returncode != 0:
            message = f"{completed.stdout}\n{completed.stderr}".lower()
            if "user canceled" in message or "user cancelled" in message:
                return DirectorySelection.cancelled()
            raise DirectoryPickerError("native directory picker failed")
        return DirectorySelection.from_path(completed.stdout.strip())
