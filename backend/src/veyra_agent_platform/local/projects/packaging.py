"""Portable Project archives: source, README, tests, and resources only."""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml  # type: ignore[import-untyped]

from veyra_agent_platform.contracts.agent import AgentSource, ProjectManifest
from veyra_agent_platform.contracts.canonical import file_hash
from veyra_agent_platform.contracts.common import (
    ContractValidationError,
    new_uuid7,
    require_uuid7,
)
from veyra_agent_platform.contracts.resource import (
    ResourceKind,
    ResourceManifest,
    ResourceRef,
)
from veyra_agent_platform.contracts.workflow import WorkflowSource
from veyra_agent_platform.local.projects.layout import (
    ARCHIVE_PREFIXES,
    listed_archive_prefixes,
    resource_yaml_path,
)

MAX_INDEXED_FILE_BYTES = 1_000_000
MAX_INDEXED_TOTAL_BYTES = 10_000_000
MAX_PROJECT_ARCHIVE_BYTES = 12_000_000
_ALLOWED_SUFFIXES = {".yaml", ".yml", ".md", ".txt", ".json"}
_ARCHIVE_PREFIXES = ARCHIVE_PREFIXES
_FORBIDDEN_SECRET_NAMES = {".env", "id_rsa", "credentials.json"}
_FORBIDDEN_SECRET_SUFFIXES = {".key", ".pem", ".p12", ".token"}
_UNIX_SYMLINK_MODE = 0o120000


class ProjectPackageError(ValueError):
    """A Project archive is unsafe, oversized, or structurally invalid."""

    def __init__(self, message: str, code: str = "project_package_invalid") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ImportedAgentVersion:
    version_id: str
    source: AgentSource


@dataclass(frozen=True)
class ProjectArchive:
    manifest: ProjectManifest
    agent_versions: tuple[ImportedAgentVersion, ...]
    sources: list[AgentSource]
    parents: dict[str, str]
    extra_files: dict[str, bytes]
    name: str
    description: str
    default_agent_id: str | None


def pack_project_files(
    root: Path,
    files: list[Path],
    *,
    extra_files: dict[str, bytes] | None = None,
) -> bytes:
    members = {path.relative_to(root).as_posix(): path.read_bytes() for path in files}
    for relative, payload in (extra_files or {}).items():
        if relative in members:
            raise ProjectPackageError("Project archive contains duplicate paths")
        members[relative] = payload
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, payload in sorted(members.items()):
            _assert_archive_path(relative)
            archive.writestr(relative, payload)
    payload = buffer.getvalue()
    if len(payload) > MAX_PROJECT_ARCHIVE_BYTES:
        raise ProjectPackageError("Project archive exceeds the export size limit")
    # Export and import enforce the same structural and digest guarantees.
    _validated_members(zipfile.ZipFile(io.BytesIO(payload)))
    return payload


def _validated_members(
    archive: zipfile.ZipFile,
) -> tuple[
    ProjectManifest,
    list[tuple[str, AgentSource]],
    dict[str, bytes],
    dict[str, ImportedAgentVersion],
]:
    with archive:
        members = _read_members(archive)
    if "project.vproject.yaml" not in members:
        raise ProjectPackageError("Project archive is missing project.vproject.yaml")
    try:
        manifest = ProjectManifest.from_dict(
            _parse_mapping(members["project.vproject.yaml"], "Project manifest")
        )
        sources, extra_files = _sources_and_extras(manifest, members)
        snapshots = _read_agent_versions(manifest, members)
        _validate_workflow_references(manifest, members, snapshots)
    except ContractValidationError as exc:
        raise ProjectPackageError(str(exc), "contract_invalid") from exc
    return manifest, sources, extra_files, snapshots


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
    manifest, sources, extra_files, snapshots = _validated_members(archive)
    return _remap_identities(manifest, sources, extra_files, snapshots)


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
        except (RuntimeError, zipfile.BadZipFile) as exc:
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
        if source.version != entry.version:
            raise ProjectPackageError(
                "Project manifest Agent version does not match source"
            )
        metadata = members.get(resource_yaml_path(entry.path))
        if metadata is not None:
            _validate_resource_metadata(entry, ResourceKind.AGENT, metadata)
        sources.append((entry.agent_id, source))
        claimed.add(source_path)
        claimed.add(resource_yaml_path(entry.path))
    ids = [entry.agent_id for entry in manifest.agents]
    for entries in (
        manifest.workflows,
        manifest.components,
        manifest.knowledge,
        manifest.assets,
    ):
        for owned_entry in entries:
            ids.append(owned_entry.resource_id)
            metadata_path = resource_yaml_path(owned_entry.path)
            if metadata_path not in members:
                raise ProjectPackageError("Project archive is missing resource.yaml")
            _validate_resource_metadata(
                owned_entry, owned_entry.kind, members[metadata_path]
            )
            if owned_entry.kind is ResourceKind.WORKFLOW:
                source_path = f"{owned_entry.path}/workflow.vworkflow.yaml"
                if source_path not in members:
                    raise ProjectPackageError(
                        "Project archive is missing a Workflow source file"
                    )
                workflow = WorkflowSource.from_dict(
                    _parse_mapping(members[source_path], owned_entry.slug)
                )
                if (workflow.workflow_id, workflow.slug, workflow.version) != (
                    owned_entry.resource_id,
                    owned_entry.slug,
                    owned_entry.version,
                ):
                    raise ProjectPackageError(
                        "Project manifest Workflow identity or version does not "
                        "match source"
                    )
            if (
                owned_entry.kind is ResourceKind.KNOWLEDGE
                and f"{owned_entry.path}/document.md" not in members
            ):
                raise ProjectPackageError(
                    "Project archive is missing a Knowledge document"
                )
    if len(set(ids)) != len(ids) or manifest.project_id in ids:
        raise ProjectPackageError(
            "Project resource IDs must be unique across resource kinds"
        )
    extra = {path: payload for path, payload in members.items() if path not in claimed}
    identity_prefixes = {
        "agents/": listed_archive_prefixes(list(manifest.agents)),
        "workflows/": listed_archive_prefixes(list(manifest.workflows)),
        "components/": listed_archive_prefixes(list(manifest.components)),
    }
    library_prefixes = {
        "knowledge/": listed_archive_prefixes(list(manifest.knowledge)),
        "assets/": listed_archive_prefixes(list(manifest.assets)),
    }
    for path in extra:
        for prefix, listed in identity_prefixes.items():
            if path.startswith(prefix) and (not listed or not path.startswith(listed)):
                raise ProjectPackageError("Project archive contains a disallowed path")
        for prefix, listed in library_prefixes.items():
            if path.startswith(prefix) and listed and not path.startswith(listed):
                raise ProjectPackageError("Project archive contains a disallowed path")
    return sources, extra


def _validate_resource_metadata(entry: Any, kind: ResourceKind, payload: bytes) -> None:
    resource = ResourceManifest.from_dict(_parse_mapping(payload, "resource manifest"))
    resource_id = entry.agent_id if kind is ResourceKind.AGENT else entry.resource_id
    if (
        resource.kind,
        resource.resource_id,
        resource.slug,
        resource.version,
        resource.component_class,
    ) != (
        kind,
        resource_id,
        entry.slug,
        entry.version,
        getattr(entry, "component_class", None),
    ):
        raise ProjectPackageError(
            "resource.yaml identity, kind, class or version does not "
            "match Project manifest"
        )


def _read_agent_versions(
    manifest: ProjectManifest, members: dict[str, bytes]
) -> dict[str, ImportedAgentVersion]:
    versions: dict[str, ImportedAgentVersion] = {}
    for entry in manifest.agents:
        prefix = f"{entry.path}/versions/"
        for path, body in members.items():
            if not path.startswith(prefix):
                continue
            payload = _parse_mapping(body, "Agent version snapshot")
            if set(payload) != {"version_id", "agent_id", "source", "source_hash"}:
                raise ProjectPackageError("Agent version snapshot fields are invalid")
            version_id = require_uuid7(payload["version_id"], "version_id")
            source = AgentSource.from_dict(payload["source"])
            if (
                path != f"{prefix}{version_id}.json"
                or payload["agent_id"] != entry.agent_id
                or source.agent_id != entry.agent_id
            ):
                raise ProjectPackageError(
                    "Agent version snapshot identity does not match its owner"
                )
            if payload["source_hash"] != source.source_hash:
                raise ProjectPackageError(
                    "Agent version snapshot digest does not match source"
                )
            if version_id in versions:
                raise ProjectPackageError("Agent version snapshot IDs must be unique")
            versions[version_id] = ImportedAgentVersion(version_id, source)
    return versions


def _validate_workflow_references(
    manifest: ProjectManifest,
    members: dict[str, bytes],
    snapshots: dict[str, ImportedAgentVersion],
) -> None:
    referenced: set[str] = set()
    for entry in manifest.workflows:
        source = WorkflowSource.from_dict(
            _parse_mapping(members[f"{entry.path}/workflow.vworkflow.yaml"], entry.slug)
        )
        for node in source.nodes:
            if node.agent_ref is None:
                continue
            agent_id, version_id = node.agent_ref.split("@", 1)
            snapshot = snapshots.get(version_id)
            if snapshot is None or snapshot.source.agent_id != agent_id:
                raise ProjectPackageError(
                    "Workflow AgentCall requires a bundled immutable Agent version"
                )
            if source.lock[node.agent_ref] != snapshot.source.source_hash:
                raise ProjectPackageError(
                    "Workflow AgentCall lock digest does not match its Agent version"
                )
            referenced.add(version_id)
        # An unused local reference must not survive import with an old identity.
        for reference in source.lock:
            if reference[0].isdigit() and reference not in {
                node.agent_ref for node in source.nodes
            }:
                raise ProjectPackageError(
                    "Workflow lock contains an unbound local resource reference"
                )
    if set(snapshots) != referenced:
        raise ProjectPackageError(
            "Project archive contains an unreferenced Agent version snapshot"
        )


def _remap_identities(
    manifest: ProjectManifest,
    sources: list[tuple[str, AgentSource]],
    extra_files: dict[str, bytes],
    snapshots: dict[str, ImportedAgentVersion],
) -> ProjectArchive:
    id_map = {old_id: new_uuid7() for old_id, _source in sources}
    for entries in (
        manifest.workflows,
        manifest.components,
        manifest.knowledge,
        manifest.assets,
    ):
        id_map.update({entry.resource_id: new_uuid7() for entry in entries})
    remapped_sources: list[AgentSource] = []
    parents: dict[str, str] = {}
    slug_map: dict[str, str] = {}
    occupied_names: set[str] = set()
    for old_id, source in sources:
        name = _unique_name(source.name, occupied_names)
        occupied_names.add(name)
        source_payload = source.to_dict()
        source_payload.update({"agent_id": id_map[old_id], "name": name})
        _remap_knowledge_locks(source_payload, id_map, manifest, extra_files)
        remapped_sources.append(AgentSource.from_dict(source_payload))
        slug_map[old_id] = source.slug
        entry = next(item for item in manifest.agents if item.agent_id == old_id)
        if entry.parent_agent_id is not None:
            parents[id_map[old_id]] = id_map[entry.parent_agent_id]
    version_map: dict[str, ImportedAgentVersion] = {}
    unique_versions: dict[tuple[str, str], ImportedAgentVersion] = {}
    for old_version, snapshot in snapshots.items():
        payload = snapshot.source.to_dict()
        payload["agent_id"] = id_map[snapshot.source.agent_id]
        _remap_knowledge_locks(payload, id_map, manifest, extra_files)
        source = AgentSource.from_dict(payload)
        fingerprint = (source.agent_id, source.source_hash)
        if fingerprint not in unique_versions:
            unique_versions[fingerprint] = ImportedAgentVersion(new_uuid7(), source)
        version_map[old_version] = unique_versions[fingerprint]
    rewritten_extras: dict[str, bytes] = {}
    for path, body in extra_files.items():
        if any(path.startswith(f"{entry.path}/versions/") for entry in manifest.agents):
            continue
        if path.endswith("/resource.yaml"):
            payload = _parse_mapping(body, "resource manifest")
            resource = ResourceManifest.from_dict(payload)
            if resource.resource_id in id_map:
                payload["resource_id"] = id_map[resource.resource_id]
                body = _encode_mapping(payload)
        if path.endswith("/workflow.vworkflow.yaml"):
            payload = WorkflowSource.from_dict(
                _parse_mapping(body, "Workflow")
            ).to_dict()
            payload["workflow_id"] = id_map[payload["workflow_id"]]
            for node in payload["nodes"]:
                if "agent_ref" not in node:
                    continue
                old_ref = node["agent_ref"]
                _old_agent, old_version = old_ref.split("@", 1)
                snapshot = version_map[old_version]
                new_ref = f"{snapshot.source.agent_id}@{snapshot.version_id}"
                node["agent_ref"] = new_ref
                payload["lock"].pop(old_ref, None)
                payload["lock"][new_ref] = snapshot.source.source_hash
            body = _encode_mapping(WorkflowSource.from_dict(payload).to_dict())
        rewritten_extras[_rewrite_extra_path(path, slug_map, manifest)] = body
    default_agent_id = (
        id_map[manifest.default_agent_id] if manifest.default_agent_id else None
    )
    updated_manifest = manifest.to_dict()
    updated_manifest["project_id"] = new_uuid7()
    updated_manifest["default_agent_id"] = default_agent_id
    for entry in updated_manifest["agents"]:
        entry["agent_id"] = id_map[entry["agent_id"]]
        if "parent_agent_id" in entry:
            entry["parent_agent_id"] = id_map[entry["parent_agent_id"]]
    for kind in ("workflows", "components", "knowledge", "assets"):
        for entry in updated_manifest.get(kind, []):
            entry["resource_id"] = id_map[entry["resource_id"]]
    return ProjectArchive(
        manifest=ProjectManifest.from_dict(updated_manifest),
        agent_versions=tuple(unique_versions.values()),
        sources=remapped_sources,
        parents=parents,
        extra_files=rewritten_extras,
        name=manifest.name,
        description=manifest.description,
        default_agent_id=default_agent_id,
    )


def _remap_knowledge_locks(
    payload: dict[str, Any],
    id_map: dict[str, str],
    manifest: ProjectManifest,
    members: dict[str, bytes],
) -> None:
    replacements: dict[str, str] = {}
    for reference, digest in list(payload["lock"].items()):
        if not re.match(r"^[0-9a-f]{8}-", reference):
            continue
        ref = ResourceRef.from_string(reference)
        entry = next(
            (
                entry
                for entry in manifest.knowledge
                if entry.resource_id == ref.resource_id
            ),
            None,
        )
        body = members.get(f"{entry.path}/document.md") if entry else None
        if (
            entry is None
            or body is None
            or entry.version != ref.version
            or file_hash(body.decode("utf-8")) != digest
        ):
            raise ProjectPackageError(
                "Agent local dependency requires a bundled Knowledge "
                "document matching its lock"
            )
        target = f"{id_map[ref.resource_id]}@{ref.version}"
        replacements[reference] = target
        payload["lock"].pop(reference)
        payload["lock"][target] = digest
    veyra = payload["extensions"]["veyra"]
    if "knowledge_refs" in veyra:
        veyra["knowledge_refs"] = [
            replacements.get(ref, ref) for ref in veyra["knowledge_refs"]
        ]
    for binding in (payload["ui"].get("bindings") or {}).values():
        binding["reference"] = replacements.get(
            binding["reference"], binding["reference"]
        )


def _encode_mapping(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


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
