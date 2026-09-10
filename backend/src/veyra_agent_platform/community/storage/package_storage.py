"""Content-addressed local storage for Community registry packages."""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path


class LocalPackageStorage:
    """Store validated package bytes outside the Community database."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, content: bytes) -> str:
        storage_id = hashlib.sha256(content).hexdigest()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = self.root / storage_id
        if target.is_file():
            return storage_id
        temporary = self.root / f".{storage_id}.{secrets.token_hex(8)}.tmp"
        try:
            with temporary.open("xb") as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return storage_id

    def get(self, storage_id: str) -> bytes | None:
        if len(storage_id) != 64 or any(
            char not in "0123456789abcdef" for char in storage_id
        ):
            return None
        try:
            return (self.root / storage_id).read_bytes()
        except FileNotFoundError:
            return None
