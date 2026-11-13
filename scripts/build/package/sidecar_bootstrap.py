"""Start the local service from a PyInstaller bundle without a repository cwd."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _source_root() -> Path:
    """Locate the bundled source tree or the repository source tree."""
    bundle_root = Path(__file__).resolve().parent
    if getattr(sys, "frozen", False):
        return bundle_root / "backend" / "src"
    return Path(__file__).resolve().parents[3] / "backend" / "src"


def main() -> None:
    source_root = _source_root()
    if not source_root.is_dir():
        raise SystemExit(f"local sidecar source bundle is missing: {source_root}")
    sys.path.insert(0, str(source_root))
    module = importlib.import_module("veyra_agent_platform.local.app")
    entrypoint = getattr(module, "main", None)
    if not callable(entrypoint):
        raise SystemExit("veyra local sidecar entrypoint is unavailable")
    entrypoint()


if __name__ == "__main__":
    main()
