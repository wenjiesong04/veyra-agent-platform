"""Validate the safe, declarative ``.vplugin.zip`` archive format."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import yaml  # type: ignore[import-untyped]

from veyra_agent_platform.local.mcp import McpError, normalize_mcp_config

MAX_PLUGIN_ARCHIVE_BYTES = 5_000_000
MAX_PLUGIN_FILE_BYTES = 1_000_000
MAX_PLUGIN_TOTAL_BYTES = 4_000_000
MAX_PLUGIN_SKILLS = 16
MAX_PLUGIN_MCP_SERVERS = 16

_PLUGIN_ID = re.compile(r"^veyra\.plugin\.[a-z][a-z0-9_.-]{1,63}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_REFERENCE = re.compile(
    r"^veyra\.skill\.[a-z][a-z0-9_.-]{1,127}@[0-9]+\.[0-9]+\.[0-9]+$"
)
_SKILL_SLUG = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "plugin_id",
        "name",
        "description",
        "version",
        "license",
        "skills",
        "mcp_config",
    }
)
_SKILL_KEYS = frozenset({"path", "reference", "name", "description"})
_UNIX_SYMLINK_MODE = 0o120000


class PluginPackError(ValueError):
    """A Plugin Pack is unsafe or does not match the declarative contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PluginSkill:
    path: str
    reference: str
    name: str
    description: str
    instruction: str

    def to_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "reference": self.reference,
            "name": self.name,
            "description": self.description,
            "instruction": self.instruction,
        }


@dataclass(frozen=True)
class PluginPack:
    plugin_id: str
    name: str
    description: str
    version: str
    license: str | None
    skills: tuple[PluginSkill, ...]
    mcp_servers: tuple[dict[str, Any], ...]
    content_hash: str

    def metadata(self) -> dict[str, Any]:
        """Return safe metadata for application storage and API responses."""
        return {
            "schema_version": "1.0",
            "plugin_id": self.plugin_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "license": self.license,
            "skills": [skill.to_dict() for skill in self.skills],
            "mcp_servers": [dict(server) for server in self.mcp_servers],
            "content_hash": self.content_hash,
        }


def unpack_plugin_archive(filename: str | None, contents: bytes) -> PluginPack:
    """Read and validate a Plugin Pack without running anything in it."""
    if not isinstance(filename, str) or not filename.lower().endswith(
        (".vplugin.zip", ".zip")
    ):
        raise PluginPackError(
            "plugin_archive_invalid", "Plugin Pack must be a .vplugin.zip archive"
        )
    if not isinstance(contents, bytes) or len(contents) > MAX_PLUGIN_ARCHIVE_BYTES:
        raise PluginPackError(
            "plugin_archive_too_large", "Plugin Pack exceeds the import size limit"
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(contents))
    except zipfile.BadZipFile as exc:
        raise PluginPackError(
            "plugin_archive_invalid", "Plugin Pack is not a valid zip archive"
        ) from exc
    members = _read_members(archive)
    manifest = _manifest(members.get("plugin.vplugin.yaml"))
    plugin_id = _text(manifest.get("plugin_id"), "plugin_id", 128)
    if _PLUGIN_ID.fullmatch(plugin_id) is None:
        raise PluginPackError(
            "plugin_manifest_invalid", "plugin_id must be a safe veyra.plugin id"
        )
    version = _text(manifest.get("version"), "version", 32)
    if _VERSION.fullmatch(version) is None:
        raise PluginPackError(
            "plugin_manifest_invalid", "plugin version must be numeric dotted"
        )
    name = _text(manifest.get("name"), "name", 120)
    description = _text(manifest.get("description"), "description", 4_000)
    license_value = manifest.get("license")
    license_name = (
        None if license_value is None else _text(license_value, "license", 120)
    )
    skills = _skills(manifest.get("skills"), members, name)
    mcp_config = manifest.get("mcp_config")
    if mcp_config is None and "mcp.json" in members:
        mcp_config = "mcp.json"
    mcp_servers = _mcp_servers(mcp_config, members)
    if not skills and not mcp_servers:
        raise PluginPackError(
            "plugin_manifest_invalid", "Plugin Pack must contain a Skill or MCP server"
        )
    if len(mcp_servers) > MAX_PLUGIN_MCP_SERVERS:
        raise PluginPackError(
            "plugin_manifest_invalid", "Plugin Pack contains too many MCP servers"
        )
    return PluginPack(
        plugin_id=plugin_id,
        name=name,
        description=description,
        version=version,
        license=license_name,
        skills=skills,
        mcp_servers=tuple(mcp_servers),
        content_hash=hashlib.sha256(contents).hexdigest(),
    )


def _read_members(archive: zipfile.ZipFile) -> dict[str, bytes]:
    members: dict[str, bytes] = {}
    total = 0
    with archive:
        for info in archive.infolist():
            if info.is_dir() or info.filename.endswith("/"):
                continue
            if info.flag_bits & 0x1 or _is_symlink(info):
                raise PluginPackError(
                    "plugin_archive_invalid",
                    "Plugin Pack cannot contain encrypted files or links",
                )
            path = _member_path(info.filename)
            if path in members:
                raise PluginPackError(
                    "plugin_archive_invalid", "Plugin Pack contains duplicate paths"
                )
            if info.file_size > MAX_PLUGIN_FILE_BYTES:
                raise PluginPackError(
                    "plugin_file_too_large", "Plugin Pack contains an oversized file"
                )
            try:
                body = archive.read(info)
            except (RuntimeError, zipfile.BadZipFile) as exc:
                raise PluginPackError(
                    "plugin_archive_invalid", "Plugin Pack member could not be read"
                ) from exc
            try:
                body.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise PluginPackError(
                    "plugin_archive_invalid", "Plugin Pack files must be UTF-8"
                ) from exc
            total += len(body)
            if total > MAX_PLUGIN_TOTAL_BYTES:
                raise PluginPackError(
                    "plugin_archive_too_large",
                    "Plugin Pack exceeds the total size limit",
                )
            _allowed_member(path)
            members[path] = body
    return members


def _member_path(raw: str) -> str:
    if not raw or "\\" in raw or "\x00" in raw:
        raise PluginPackError(
            "plugin_archive_invalid", "Plugin Pack contains an unsafe path"
        )
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", "..", "~"} for part in path.parts):
        raise PluginPackError(
            "plugin_archive_invalid", "Plugin Pack path escapes its root"
        )
    return path.as_posix()


def _allowed_member(path: str) -> None:
    if path in {"plugin.vplugin.yaml", "mcp.json", "README.md"}:
        return
    parts = path.split("/")
    if (
        len(parts) == 3
        and parts[0] == "skills"
        and parts[2] == "SKILL.md"
        and _SKILL_SLUG.fullmatch(parts[1]) is not None
    ):
        return
    raise PluginPackError(
        "plugin_archive_invalid", f"Plugin Pack contains an unsupported file: {path}"
    )


def _manifest(body: bytes | None) -> dict[str, Any]:
    if body is None:
        raise PluginPackError(
            "plugin_manifest_missing", "Plugin Pack is missing plugin.vplugin.yaml"
        )
    try:
        payload = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        raise PluginPackError(
            "plugin_manifest_invalid", "plugin.vplugin.yaml is not valid YAML"
        ) from exc
    if not isinstance(payload, dict) or set(payload) - _MANIFEST_KEYS:
        raise PluginPackError(
            "plugin_manifest_invalid", "plugin.vplugin.yaml has unsupported fields"
        )
    if payload.get("schema_version") != "1.0":
        raise PluginPackError(
            "plugin_manifest_invalid", "Plugin Pack schema_version must be 1.0"
        )
    return payload


def _skills(
    value: object, members: Mapping[str, bytes], plugin_name: str
) -> tuple[PluginSkill, ...]:
    if not isinstance(value, list) or len(value) > MAX_PLUGIN_SKILLS:
        raise PluginPackError(
            "plugin_manifest_invalid", "Plugin Pack skills must be a bounded list"
        )
    parsed: list[PluginSkill] = []
    paths: set[str] = set()
    references: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) - _SKILL_KEYS:
            raise PluginPackError(
                "plugin_manifest_invalid", "Plugin Pack Skill metadata is invalid"
            )
        path = _text(item.get("path"), "skill.path", 160)
        _allowed_member(path)
        if not path.startswith("skills/") or path not in members:
            raise PluginPackError(
                "plugin_skill_missing", "Plugin Pack Skill file is missing"
            )
        reference = _text(item.get("reference"), "skill.reference", 180)
        if _REFERENCE.fullmatch(reference) is None:
            raise PluginPackError(
                "plugin_manifest_invalid",
                "Skill references must be versioned veyra.skill ids",
            )
        if path in paths or reference in references:
            raise PluginPackError(
                "plugin_manifest_invalid",
                "Plugin Pack Skill paths and references must be unique",
            )
        body = members[path].decode("utf-8").strip()
        if not body or len(body) > 20_000:
            raise PluginPackError(
                "plugin_skill_invalid",
                "Skill instructions must contain 1-20000 characters",
            )
        slug = path.split("/")[1]
        skill_name = _text(
            item.get("name") or slug.replace("-", " ").title(), "skill.name", 120
        )
        skill_description = _text(
            item.get("description") or f"Skill from {plugin_name}",
            "skill.description",
            1_000,
        )
        parsed.append(
            PluginSkill(
                path=path,
                reference=reference,
                name=skill_name,
                description=skill_description,
                instruction=body,
            )
        )
        paths.add(path)
        references.add(reference)
    return tuple(parsed)


def _mcp_servers(value: object, members: Mapping[str, bytes]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, str) or value != "mcp.json":
        raise PluginPackError(
            "plugin_mcp_invalid", "Plugin Pack mcp_config must point to mcp.json"
        )
    body = members.get(value)
    if body is None:
        raise PluginPackError("plugin_mcp_missing", "Plugin Pack mcp.json is missing")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise PluginPackError(
            "plugin_mcp_invalid", "Plugin Pack mcp.json is invalid"
        ) from exc
    try:
        return normalize_mcp_config(payload)
    except McpError as exc:
        raise PluginPackError("plugin_mcp_invalid", str(exc)) from exc


def _text(value: object, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise PluginPackError("plugin_manifest_invalid", f"{field} must be text")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > limit or "\x00" in cleaned:
        raise PluginPackError("plugin_manifest_invalid", f"{field} is invalid")
    return cleaned


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == _UNIX_SYMLINK_MODE
