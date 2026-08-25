"""Content-addressed object storage outside SQLite."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


def write_object(object_root: Path, contents: bytes) -> tuple[str, Path]:
    """Atomically retain bytes under their SHA-256 digest exactly once."""
    digest = hashlib.sha256(contents).hexdigest()
    destination = object_root / "sha256" / digest
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        existing = destination.read_bytes()
        if (
            len(existing) != len(contents)
            or hashlib.sha256(existing).hexdigest() != digest
        ):
            raise ValueError("content-addressed object verification failed")
        return digest, destination
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".veyra-", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
        _fsync_directory(destination.parent)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return digest, destination


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
