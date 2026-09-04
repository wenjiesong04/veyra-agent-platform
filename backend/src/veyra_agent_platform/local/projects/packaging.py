"""Portable Project archives: source, README, tests, and resources only."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml  # type: ignore[import-untyped]

from veyra_agent_platform.contracts.agent import AgentSource, ProjectManifest
from veyra_agent_platform.contracts.common import ContractValidationError, new_uuid7

MAX_INDEXED_FILE_BYTES = 1_000_000
MAX_INDEXED_TOTAL_BYTES = 10_000_000
MAX_PROJECT_ARCHIVE_BYTES = 12_000_000
_ALLOWED_SUFFIXES = {".yaml", ".yml", ".md", ".txt", ".json"}
_ARCHIVE_PREFIXES = ("agents/", "resources/", "tests/")
_FORBIDDEN_SECRET_NAMES = {".env", "id_rsa", "credentials.json"}
_FORBIDDEN_SECRET_SUFFIXES = {".key", ".pem", ".p12", ".token"}
_UNIX_SYMLINK_MODE = 0o120000


class ProjectPackageError(ValueError):
    """A Project archive is unsafe, oversized, or structurally invalid."""

    def __init__(self, message: str, code: str = "project_package_invalid") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProjectArchive:
    sources: list[AgentSource]
    parents: dict[str, str]
    extra_files: dict[str, bytes]
    name: str
    description: str
    default_agent_id: str | None


def pack_project_files(root: Path, files: list[Path]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            relative = path.relative_to(root).as_posix()
            _assert_archive_path(relative)
            archive.write(path, arcname=relative)
    payload = buffer.getvalue()
    if len(payload) > MAX_PROJECT_ARCHIVE_BYTES:
        raise ProjectPackageError("Project archive exceeds the export size limit")
    return payload


def unpack_project_archive(filename: str | None, contents: bytes) -> ProjectArchive:
    if not isinstance(filename, str) or not filename.lower().endswith(
        (".vproject.zip", ".zip")
    ):
        raise ProjectPackageError("import must be a .vproject.zip archive")
    if not isinstance(contents, bytes) or len(contents) > MAX_PROJECT_ARCHIVE_BYTES:
        raise ProjectPackageError("Project archive exceeds the import size limit")
    try:
        archive = zipfile.ZipFile(io.BytesIO(contents))
    except zipfile.BadZipFile as exc:
        raise ProjectPackageError("Project archive is not a valid zip") from exc
    members = _read_members(archive)
    if "project.vproject.yaml" not in members:
        raise ProjectPackageError("Project archive is missing project.vproject.yaml")
    try:
        manifest = ProjectManifest.from_dict(
            _parse_mapping(members["project.vproject.yaml"], "Project manifest")
        )
        sources, extra_files = _sources_and_extras(manifest, members)
    except ContractValidationError as exc:
        raise ProjectPackageError(str(exc), "contract_invalid") from exc
    return _remap_identities(manifest, sources, extra_files)


def _read_members(archive: zipfile.ZipFile) -> dict[str, bytes]:
    members: dict[str, bytes] = {}
    total = 0
    for info in archive.infolist():
        if info.is_dir() or info.filename.endswith("/"):
            continue
        if info.flag_bits & 0x1:
            raise ProjectPackageError("Project archive members must not be encrypted")
        if _is_symlink_member(info):
            raise ProjectPackageError("Project archive may not contain symbolic links")
        relative = _assert_archive_path(info.filename)
        if relative in members:
            raise ProjectPackageError("Project archive contains duplicate paths")
        if info.file_size > MAX_INDEXED_FILE_BYTES:
            raise ProjectPackageError("Project file exceeds the indexing size limit")
        try:
            payload = archive.read(info)
        except RuntimeError as exc:
            raise ProjectPackageError(
                "Project archive member could not be read"
            ) from exc
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProjectPackageError("Project archive files must be UTF-8") from exc
        total += len(payload)
        if len(payload) > MAX_INDEXED_FILE_BYTES or total > MAX_INDEXED_TOTAL_BYTES:
            raise ProjectPackageError("Project exceeds the indexing total size limit")
        members[relative] = payload
    return members


def _is_symlink_member(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == _UNIX_SYMLINK_MODE


def _assert_archive_path(raw: str) -> str:
    if not isinstance(raw, str) or not raw or raw.endswith("/"):
        raise ProjectPackageError("Project archive path is invalid")
    candidate = raw.replace("\\", "/")
    if (
        candidate.startswith("/")
        or candidate.startswith("./")
        or ":" in candidate
        or "\x00" in candidate
    ):
        raise ProjectPackageError("Project archive path escapes its root")
    path = PurePosixPath(candidate)
    if (
        path.is_absolute()
        or any(part in {"", ".", "..", "~"} for part in path.parts)
        or path.parts[0] == "~"
    ):
        raise ProjectPackageError("Project archive path escapes its root")
    relative = path.as_posix()
    if relative != "project.vproject.yaml" and not relative.startswith(
        _ARCHIVE_PREFIXES
    ):
        raise ProjectPackageError("Project archive contains a disallowed path")
    name = Path(relative).name.lower()
    suffix = Path(relative).suffix.lower()
    if name in _FORBIDDEN_SECRET_NAMES or suffix in _FORBIDDEN_SECRET_SUFFIXES:
        raise ProjectPackageError("secrets must not be stored in a Project directory")
    if suffix not in _ALLOWED_SUFFIXES:
        raise ProjectPackageError("Project archive contains a disallowed file type")
    return relative


def _sources_and_extras(
    manifest: ProjectManifest, members: dict[str, bytes]
) -> tuple[list[tuple[str, AgentSource]], dict[str, bytes]]:
    sources: list[tuple[str, AgentSource]] = []
    claimed = {"project.vproject.yaml"}
    for entry in manifest.agents:
        source_path = f"{entry.path}/agent.vagent.yaml"
        payload = members.get(source_path)
        if payload is None:
            raise ProjectPackageError("Project archive is missing an Agent source file")
        source = AgentSource.from_dict(_parse_mapping(payload, entry.slug))
        if source.agent_id != entry.agent_id or source.slug != entry.slug:
            raise ProjectPackageError(
                "Project manifest Agent identity does not match source"
            )
        sources.append((entry.agent_id, source))
        claimed.add(source_path)
    extra = {path: payload for path, payload in members.items() if path not in claimed}
    listed_prefixes = tuple(f"{entry.path}/" for entry in manifest.agents)
    for path in extra:
        if path.startswith("agents/") and not path.startswith(listed_prefixes):
            raise ProjectPackageError("Project archive contains a disallowed path")
    return sources, extra


def _remap_identities(
    manifest: ProjectManifest,
    sources: list[tuple[str, AgentSource]],
    extra_files: dict[str, bytes],
) -> ProjectArchive:
    id_map = {old_id: new_uuid7() for old_id, _source in sources}
    remapped_sources: list[AgentSource] = []
    parents: dict[str, str] = {}
    slug_map: dict[str, str] = {}
    occupied_slugs: set[str] = set()
    occupied_names: set[str] = set()
    for old_id, source in sources:
        slug = _unique_slug(source.slug, occupied_slugs)
        occupied_slugs.add(slug)
        name = _unique_name(source.name, occupied_names)
        occupied_names.add(name)
        source_payload = source.to_dict()
        source_payload.update({"agent_id": id_map[old_id], "slug": slug, "name": name})
        remapped_sources.append(AgentSource.from_dict(source_payload))
        slug_map[old_id] = slug
        entry = next(item for item in manifest.agents if item.agent_id == old_id)
        if entry.parent_agent_id is not None:
            parents[id_map[old_id]] = id_map[entry.parent_agent_id]
    rewritten_extras: dict[str, bytes] = {}
    for path, body in extra_files.items():
        rewritten_extras[_rewrite_extra_path(path, slug_map, manifest)] = body
    default_agent_id = (
        id_map[manifest.default_agent_id]
        if manifest.default_agent_id is not None
        else None
    )
    return ProjectArchive(
        sources=remapped_sources,
        parents=parents,
        extra_files=rewritten_extras,
        name=manifest.name,
        description=manifest.description,
        default_agent_id=default_agent_id,
    )


def _rewrite_extra_path(
    path: str, slug_map: dict[str, str], manifest: ProjectManifest
) -> str:
    for entry in manifest.agents:
        prefix = f"{entry.path}/"
        if path.startswith(prefix):
            new_slug = slug_map[entry.agent_id]
            return f"agents/{new_slug}/{path.removeprefix(prefix)}"
    return path


def _unique_slug(base: str, occupied: set[str]) -> str:
    candidate = base
    suffix = 1
    while candidate in occupied:
        marker = f"-{suffix}"
        candidate = f"{base[: 63 - len(marker)]}{marker}"
        suffix += 1
    return candidate


def _unique_name(base: str, occupied: set[str]) -> str:
    candidate = base
    suffix = 1
    occupied_keys = {value.casefold() for value in occupied}
    while candidate.casefold() in occupied_keys:
        candidate = f"{base}({suffix})"
        suffix += 1
    return candidate


def _parse_mapping(payload: bytes, name: str) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectPackageError("Project archive files must be UTF-8") from exc
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ProjectPackageError(f"invalid {name} YAML") from exc
    if not isinstance(loaded, dict):
        raise ProjectPackageError(f"{name} must contain an object")
    return loaded
