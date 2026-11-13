"""Flush directory entries after changing local workspace files."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def fsync_directory(directory: Path) -> None:
    # Windows CRT file descriptors cannot open directories. Callers still
    # flush regular file contents and use same-volume atomic replacements.
    if sys.platform == "win32":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
