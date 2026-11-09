"""Guard direct common pins needed by both macOS and Linux CI resolution."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_HASH = re.compile(r"^\s*--hash=sha256:[0-9a-f]{64}")


def _lock_entry_has_hash(lock_path: Path, package: str, version: str) -> bool:
    lines = lock_path.read_text(encoding="utf-8").splitlines()
    prefix = f"{package}=={version}"
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            for candidate in lines[index + 1 :]:
                if _HASH.match(candidate):
                    return True
                if candidate and not candidate.startswith((" ", "#")):
                    return False
            return False
    return False


def test_common_linux_required_pins_are_explicit_and_hashed() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        dependencies = tomllib.load(stream)["project"]["dependencies"]

    assert "SQLAlchemy==2.0.43" in dependencies
    assert "greenlet==3.5.5" in dependencies
    assert "argon2-cffi==25.1.0" in dependencies
    for lock_name in ("runtime-py311.txt", "dev-py311.txt"):
        lock_path = ROOT / "requirements" / lock_name
        assert _lock_entry_has_hash(lock_path, "greenlet", "3.5.5")
        assert _lock_entry_has_hash(lock_path, "argon2-cffi", "25.1.0")
