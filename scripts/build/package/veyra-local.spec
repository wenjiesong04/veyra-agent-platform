"""PyInstaller spec for the declarative, local-only Veyra sidecar."""

from __future__ import annotations

from pathlib import Path

from PyInstaller.building.build_main import Analysis, EXE, PYZ
from PyInstaller.utils.hooks import collect_all

SPEC_DIR = Path(
    str(globals().get("SPECPATH", Path.cwd() / "scripts" / "build" / "package"))
).resolve()
ROOT = SPEC_DIR.parents[2]


def _tree(root: Path, destination: str, *, suffixes: set[str] | None = None):
    entries = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] == "community":
            # The Desktop bundle owns Local only. Community remains a separate service.
            continue
        if suffixes is not None and path.suffix not in suffixes:
            continue
        target = Path(destination) / relative.parent
        entries.append((str(path), target.as_posix()))
    return entries


datas = []
datas.extend(
    _tree(
        ROOT / "backend" / "src" / "veyra_agent_platform",
        "backend/src/veyra_agent_platform",
        suffixes={".py"},
    )
)
datas.extend(
    _tree(
        ROOT / "backend" / "migrations" / "local",
        "backend/migrations/local",
        suffixes={".ini", ".py", ".mako"},
    )
)
datas.extend(
    _tree(
        ROOT / "resources" / "nodes",
        "resources/nodes",
        suffixes={".yaml", ".md"},
    )
)
datas.extend(
    _tree(
        ROOT / "contracts" / "schemas",
        "contracts/schemas",
        suffixes={".json"},
    )
)

binaries = []
hiddenimports = []
for dependency in (
    "aiosqlite",
    "alembic",
    "argon2",
    "cryptography",
    "fastapi",
    "httpx",
    "jsonschema",
    "keyring",
    "platformdirs",
    "pydantic",
    "pydantic_settings",
    "sqlalchemy",
    "starlette",
    "uvicorn",
    "yaml",
):
    dependency_datas, dependency_binaries, dependency_hiddenimports = collect_all(
        dependency
    )
    datas.extend(dependency_datas)
    binaries.extend(dependency_binaries)
    hiddenimports.extend(dependency_hiddenimports)

# The Local source is carried as data so its repository-relative migration and
# catalog paths remain valid inside the bundle. These standard-library imports
# therefore need to be declared explicitly rather than discovered from frozen
# first-party modules.
hiddenimports.extend(["html.parser", "urllib.parse", "xml.etree.ElementTree"])


analysis = Analysis(
    [str(ROOT / "scripts" / "build" / "package" / "sidecar_bootstrap.py")],
    pathex=[str(ROOT / "scripts" / "build" / "package")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["veyra_agent_platform", "veyra_agent_platform.community"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="veyra-local",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
)
