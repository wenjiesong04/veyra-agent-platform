"""Safe, explicit materialization of downloaded Cloud File bytes into a Project."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from veyra_agent_platform.local.storage.durability import fsync_directory

_CHUNK_SIZE = 1024 * 1024
_HASH = re.compile(r"^[0-9a-f]{64}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_ALLOWED_ROOTS = {"assets", "knowledge"}


class ProjectMaterializeError(ValueError):
    def __init__(self, message: str, code: str = "project_materialize_invalid") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class MaterializedFile:
    relative_path: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


def materialize_stream(
    root: Path,
    relative_path: str,
    source: BinaryIO,
    *,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    max_bytes: int = 50_000_000,
) -> MaterializedFile:
    target = _safe_target(root, relative_path)
    if expected_sha256 is not None and not _HASH.fullmatch(expected_sha256):
        raise ProjectMaterializeError("Expected file hash is invalid")
    if expected_size is not None and expected_size < 0:
        raise ProjectMaterializeError("Expected file size is invalid")
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    if target.exists() or target.is_symlink():
        raise ProjectMaterializeError(
            "Target file already exists", "project_materialize_exists"
        )

    digest = hashlib.sha256()
    size = 0
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".veyra-materialize-", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as destination:
            while True:
                chunk = source.read(_CHUNK_SIZE)
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    raise ProjectMaterializeError("File stream is invalid")
                size += len(chunk)
                if size > max_bytes:
                    raise ProjectMaterializeError(
                        "File exceeds the local materialize limit", "file_too_large"
                    )
                digest.update(chunk)
                destination.write(chunk)
            if expected_size is not None and size != expected_size:
                raise ProjectMaterializeError("Downloaded file size does not match")
            actual_hash = digest.hexdigest()
            if expected_sha256 is not None and actual_hash != expected_sha256:
                raise ProjectMaterializeError("Downloaded file hash does not match")
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary_name, target)
        fsync_directory(target.parent)
    except ProjectMaterializeError:
        raise
    except OSError as exc:
        raise ProjectMaterializeError(
            "Project file could not be materialized", "project_materialize_failed"
        ) from exc
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return MaterializedFile(
        relative_path=target.relative_to(root).as_posix(),
        sha256=digest.hexdigest(),
        size_bytes=size,
    )


def _safe_target(root: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str):
        raise ProjectMaterializeError("Project relative path is invalid")
    normalized = unicodedata.normalize("NFKC", relative_path)
    if (
        not normalized
        or normalized.startswith(("/", "\\"))
        or "\\" in normalized
        or _CONTROL.search(normalized) is not None
    ):
        raise ProjectMaterializeError("Project relative path is invalid")
    parts = PurePosixPath(normalized).parts
    if (
        len(parts) < 2
        or parts[0] not in _ALLOWED_ROOTS
        or any(part in {"", ".", ".."} for part in parts)
        or parts[-1].startswith(".")
    ):
        raise ProjectMaterializeError("Project relative path is invalid")
    project_root = root.expanduser().absolute()
    if not project_root.is_dir() or project_root.is_symlink():
        raise ProjectMaterializeError("Project root is unavailable")
    current = project_root
    for part in parts[:-1]:
        current = current / part
        if not current.is_dir() or current.is_symlink():
            raise ProjectMaterializeError("Project destination is unavailable")
    target = project_root.joinpath(*parts)
    resolved = target.parent.resolve(strict=True)
    if not resolved.is_relative_to(project_root.resolve()):
        raise ProjectMaterializeError("Project relative path escapes its root")
    return target
