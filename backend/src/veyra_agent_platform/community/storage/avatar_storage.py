"""Narrow local object storage boundary for Community avatars."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Protocol


class AvatarStorage(Protocol):
    """Storage operations required by the avatar application service."""

    def put(self, content: bytes) -> str: ...

    def get(self, storage_id: str) -> bytes | None: ...

    def delete(self, storage_id: str) -> None: ...

    def check_ready(self) -> bool: ...


class LocalAvatarStorage:
    """Development object store with generated identifiers and atomic writes."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def put(self, content: bytes) -> str:
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        storage_id = secrets.token_hex(32)
        target = self._path(storage_id)
        temporary = self._root / f".{storage_id}.{secrets.token_hex(8)}.tmp"
        try:
            with temporary.open("xb") as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return storage_id

    def check_ready(self) -> bool:
        """Local storage is ready because its root is created on first write."""

        return True

    def get(self, storage_id: str) -> bytes | None:
        path = self._path(storage_id)
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None

    def delete(self, storage_id: str) -> None:
        try:
            self._path(storage_id).unlink()
        except FileNotFoundError:
            return

    def _path(self, storage_id: str) -> Path:
        valid_characters = "0123456789abcdef"
        if len(storage_id) != 64 or any(
            char not in valid_characters for char in storage_id
        ):
            raise ValueError("invalid generated avatar storage identifier")
        return self._root / storage_id
