"""Verify hashed lock contents and installed versions for one lock profile."""

from __future__ import annotations

import argparse
import importlib.metadata
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
BUILD_INPUT = ROOT / "requirements" / "build.in"
_REQUIREMENT = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\[[^\]]+\])?==([^\s;]+)\s*$"
)
_LOCK_PACKAGE = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)==([^\s\\]+)(?:\s*\\)?\s*$"
)
_HASH = re.compile(r"^\s*--hash=sha256:[0-9a-f]{64}\s*\\?\s*$")


@dataclass
class LockEntry:
    name: str
    version: str
    hashes: set[str] = field(default_factory=set)


def _canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _direct_pins(kind: str) -> dict[str, tuple[str, str]]:
    with PYPROJECT.open("rb") as stream:
        project = tomllib.load(stream)

    raw_requirements = [*project["build-system"]["requires"]]
    raw_requirements.extend(
        line.strip()
        for line in BUILD_INPUT.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    raw_requirements.extend(project["project"]["dependencies"])
    if kind == "dev":
        raw_requirements.extend(project["project"]["optional-dependencies"]["dev"])

    pins: dict[str, tuple[str, str]] = {}
    for raw_requirement in raw_requirements:
        match = _REQUIREMENT.fullmatch(raw_requirement)
        if match is None:
            raise ValueError(f"dependency is not an exact == pin: {raw_requirement}")
        name, version = match.groups()
        key = _canonical_name(name)
        previous = pins.get(key)
        if previous is not None and previous[1] != version:
            raise ValueError(f"conflicting direct pins for {name}")
        pins[key] = (name, version)
    return pins


def _parse_lock(lock_path: Path) -> dict[str, LockEntry]:
    entries: dict[str, LockEntry] = {}
    current: LockEntry | None = None
    for line_number, line in enumerate(
        lock_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _HASH.fullmatch(stripped):
            if current is None:
                raise ValueError(f"hash without package at {lock_path}:{line_number}")
            current.hashes.add(stripped.split(":", 1)[1].rstrip("\\"))
            continue
        if stripped.startswith("--") or stripped.startswith("-"):
            continue
        match = _LOCK_PACKAGE.fullmatch(stripped)
        if match is None:
            raise ValueError(f"invalid lock line at {lock_path}:{line_number}")
        name, version = match.groups()
        key = _canonical_name(name)
        if key in entries:
            raise ValueError(f"duplicate package in {lock_path}:{line_number}: {name}")
        current = LockEntry(name=name, version=version)
        entries[key] = current

    missing_hashes = [entry.name for entry in entries.values() if not entry.hashes]
    if missing_hashes:
        raise ValueError(
            f"lock entries without hashes: {', '.join(sorted(missing_hashes))}"
        )
    return entries


def _installed_versions() -> dict[str, str]:
    return {
        _canonical_name(distribution.metadata["Name"]): distribution.version
        for distribution in importlib.metadata.distributions()
        if distribution.metadata["Name"]
    }


def verify(lock_path: Path, kind: str) -> int:
    direct = _direct_pins(kind)
    entries = _parse_lock(lock_path)
    installed = _installed_versions()
    errors: list[str] = []

    for key in sorted(direct):
        name, version = direct[key]
        entry = entries.get(key)
        if entry is None:
            errors.append(f"lock missing direct pin {name}=={version}")
        elif entry.version != version:
            errors.append(
                f"lock direct-pin drift for {name}: expected {version}, "
                f"found {entry.version}"
            )

    for key in sorted(entries):
        entry = entries[key]
        actual = installed.get(key)
        if actual is None:
            errors.append(
                f"installed distribution missing {entry.name}=={entry.version}"
            )
        elif actual != entry.version:
            errors.append(
                f"installed version drift for {entry.name}: lock={entry.version}, "
                f"installed={actual}"
            )

    if errors:
        print(f"Lock verification failed for {lock_path}:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        f"Lock verified: {lock_path} ({len(entries)} packages, "
        f"{len(direct)} direct pins, hashes present)."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--kind", choices=("runtime", "dev"), required=True)
    args = parser.parse_args()
    return verify(
        ROOT / args.lock if not args.lock.is_absolute() else args.lock, args.kind
    )


if __name__ == "__main__":
    raise SystemExit(main())
