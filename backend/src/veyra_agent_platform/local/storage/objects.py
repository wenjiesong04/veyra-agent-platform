"""Content-addressed object storage outside SQLite."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path

_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def write_object(object_root: Path, contents: bytes) -> tuple[str, Path]:
    """Atomically retain bytes under their SHA-256 digest exactly once."""
    digest = hashlib.sha256(contents).hexdigest()
    destination = object_path(object_root, digest)
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


def object_path(object_root: Path, digest: str) -> Path:
    if not _DIGEST.fullmatch(digest):
        raise ValueError("invalid object digest")
    destination = object_root / "sha256" / digest
    if destination.is_symlink() or destination.parent.is_symlink():
        raise ValueError("object store path escaped")
    resolved_root = object_root.resolve()
    resolved = destination.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("object store path escaped")
    return destination


def read_object(object_root: Path, digest: str) -> bytes:
    destination = object_path(object_root, digest)
    if not destination.is_file() or destination.is_symlink():
        raise ValueError("object missing")
    payload = destination.read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("content-addressed object verification failed")
    return payload


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
