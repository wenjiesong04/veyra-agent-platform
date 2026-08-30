"""Load host-side process environment for local sidecar startup.

This reads only the repository-root gitignored `.env`. It never reads a
Project-directory `.env`, and it does not override variables already present
in the process environment.
"""

from __future__ import annotations

import os
import re
from collections.abc import MutableMapping
from pathlib import Path

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_host_process_env(
    *,
    environ: MutableMapping[str, str] | None = None,
    repo_root: Path | None = None,
) -> Path | None:
    """Populate missing process variables from the repo-root `.env` file."""

    env: MutableMapping[str, str] = os.environ if environ is None else environ
    root = repo_root or _repository_root()
    path = root / ".env"
    if not path.is_file() or path.is_symlink():
        return None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if _ENV_NAME.fullmatch(name) is None:
            continue
        current = env.get(name, "")
        if current.strip():
            continue
        env[name] = value.strip().strip("'\"")
    return path


def _repository_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "docs").is_dir():
            return parent
    return Path.cwd()
