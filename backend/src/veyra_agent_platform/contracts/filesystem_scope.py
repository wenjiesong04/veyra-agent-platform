"""Portable Project filesystem scopes; pure validation without host path access."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePosixPath, PureWindowsPath

from .common import ContractValidationError

NATIVE_PROJECT_FILESYSTEM_ADAPTERS = frozenset(
    {
        "veyra.runtime.filesystem.read",
        "veyra.runtime.filesystem.write",
        "veyra.runtime.filesystem.list",
        "veyra.runtime.filesystem.search",
        "veyra.runtime.tabular.compare",
    }
)
_SECRET_NAMES = frozenset({".env", "credentials.json", "id_rsa"})
_SECRET_SUFFIXES = (".key", ".pem", ".p12", ".token")


def project_path_parts(
    relative_path: str, *, allow_root: bool = False
) -> tuple[str, ...]:
    """Normalize a relative path lexically; Runtime still rejects host symlinks."""
    if not isinstance(relative_path, str) or len(relative_path) > 4_096:
        raise ContractValidationError("Project path must be a bounded string")
    if relative_path in {"", "."} and allow_root:
        return ()
    if (
        not relative_path.strip()
        or "\\" in relative_path
        or any(ord(char) < 32 or ord(char) == 127 for char in relative_path)
        or PureWindowsPath(relative_path).drive
    ):
        raise ContractValidationError("Project path must be a portable relative path")
    path = PurePosixPath(relative_path)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise ContractValidationError("Project path cannot escape the Project")
    parts = path.parts
    if not parts:
        raise ContractValidationError("Project path must identify a file or directory")
    if any(":" in part for part in parts):
        raise ContractValidationError("Project paths cannot use drive or stream syntax")
    if any(
        part.casefold() in _SECRET_NAMES or part.casefold().endswith(_SECRET_SUFFIXES)
        for part in parts
    ):
        raise ContractValidationError("Project path cannot access secret material")
    return parts


def project_scope_parts(value: str) -> tuple[str, ...]:
    """A scope is exactly project or project/<canonical relative directory>."""
    if value == "project":
        return ()
    if not isinstance(value, str) or not value.startswith("project/"):
        raise ContractValidationError("Filesystem scope must be inside project")
    relative = value.removeprefix("project/")
    parts = project_path_parts(relative)
    if relative != "/".join(parts) or any(part != part.strip() for part in parts):
        raise ContractValidationError("Filesystem scope must use a canonical directory")
    return parts


def normalize_project_scope(value: str) -> str:
    parts = project_scope_parts(value)
    return "project" + ("/" + "/".join(parts) if parts else "")


def path_in_project_scopes(
    relative_path: str,
    scopes: Sequence[str],
    *,
    allow_root: bool = False,
) -> bool:
    path = project_path_parts(relative_path, allow_root=allow_root)
    roots = tuple(project_scope_parts(scope) for scope in scopes)
    return any(path[: len(root)] == root for root in roots)


def filesystem_roots_satisfied(
    required: Sequence[str],
    granted: Sequence[str],
    *,
    allow_subscopes: bool = False,
) -> bool:
    """Native path-checked adapters can use a narrower part of their scope.

    Other executors retain the exact permission subset contract. This check
    establishes adapter availability, never authorizes an actual file path.
    """
    if not allow_subscopes:
        return set(required) <= set(granted)
    try:
        needs = tuple(project_scope_parts(root) for root in required)
        roots = tuple(project_scope_parts(root) for root in granted)
    except ContractValidationError:
        return False
    return all(
        any(root[: len(need)] == need or need[: len(root)] == root for root in roots)
        for need in needs
    )
