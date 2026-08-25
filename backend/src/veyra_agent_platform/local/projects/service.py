"""Safe creation and indexing of user-selected Project directories."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from veyra_agent_platform.contracts.agent import AgentSource, ProjectManifest
from veyra_agent_platform.contracts.canonical import file_hash, sha256_digest
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.storage.objects import write_object
from veyra_agent_platform.local.storage.repositories import LocalRepository


class ProjectError(ValueError):
    """A selected Project is unsafe, invalid, or unavailable."""


class ProjectService:
    """Treat portable files as truth and SQLite as a reconstructable index."""

    def __init__(self, repository: LocalRepository, object_root: Path) -> None:
        self.repository = repository
        self.object_root = object_root

    def create(
        self, *, root_path: str | Path, name: str, sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        root = self._new_root(root_path)
        parsed_sources = [AgentSource.from_dict(source) for source in sources]
        if not parsed_sources:
            raise ProjectError("a Project needs at least one Agent source")
        if len({source.agent_id for source in parsed_sources}) != len(parsed_sources):
            raise ProjectError("Project Agent IDs must be unique")
        if len({source.slug for source in parsed_sources}) != len(parsed_sources):
            raise ProjectError("Project Agent slugs must be unique")
        if not isinstance(name, str) or not name.strip():
            raise ProjectError("Project name must be non-empty")
        manifest = {
            "schema_version": "1.0",
            "project_version": "1",
            "project_id": new_uuid7(),
            "name": name.strip(),
            "agents": [
                {
                    "agent_id": source.agent_id,
                    "slug": source.slug,
                    "path": f"agents/{source.slug}",
                }
                for source in parsed_sources
            ],
            "default_agent_id": parsed_sources[0].agent_id,
            "resource_policy": {
                "max_concurrent_runs": 1,
                "max_nodes_per_run": 128,
                "max_run_seconds": 3600,
            },
        }
        ProjectManifest.from_dict(manifest)
        root.mkdir(parents=True, exist_ok=False)
        try:
            (root / "resources").mkdir()
            (root / "tests").mkdir()
            for source in parsed_sources:
                agent_root = root / "agents" / source.slug
                agent_root.mkdir(parents=True)
                self.atomic_write(
                    agent_root / "agent.vagent.yaml",
                    self._canonical_source(source.to_dict()),
                )
            self.atomic_write(
                root / "project.vproject.yaml", self._canonical_source(manifest)
            )
        except BaseException:
            # A partially created user location must not be silently removed.
            # It is small and visible, so callers can safely repair or discard it.
            raise
        return self.index(root)

    def index(self, root_path: str | Path) -> dict[str, Any]:
        root = self._existing_root(root_path)
        manifest_path = self._safe_child(root, Path("project.vproject.yaml"))
        manifest_text = self._read_text(manifest_path)
        manifest = ProjectManifest.from_dict(
            self._parse_yaml(manifest_text, "manifest")
        )
        source_records: list[tuple[AgentSource, Path, str]] = []
        for entry in manifest.agents:
            source_path = self._safe_child(root, Path(entry.path) / "agent.vagent.yaml")
            source_text = self._read_text(source_path)
            source = AgentSource.from_dict(self._parse_yaml(source_text, entry.slug))
            if source.agent_id != entry.agent_id or source.slug != entry.slug:
                raise ProjectError(
                    "Project manifest Agent identity does not match source"
                )
            source_records.append((source, source_path, source_text))

        now = _utc_now()
        root_text = str(root)
        with self.repository.transaction() as connection:
            self.repository.upsert_project(
                connection,
                project_id=manifest.project_id,
                root_path=root_text,
                name=manifest.name,
                manifest_hash=hashlib.sha256(manifest_text.encode("utf-8")).hexdigest(),
                indexed_at=now,
            )
            self._index_file(
                connection,
                manifest.project_id,
                root,
                manifest_path,
                manifest_text.encode("utf-8"),
                now,
            )
            for source, source_path, source_text in source_records:
                current_hash = file_hash(source_text)
                relative = source_path.relative_to(root).as_posix()
                self.repository.upsert_agent(
                    connection,
                    agent_id=source.agent_id,
                    project_id=manifest.project_id,
                    slug=source.slug,
                    source_path=relative,
                    source_file_hash=current_hash,
                    indexed_at=now,
                )
                self._index_file(
                    connection,
                    manifest.project_id,
                    root,
                    source_path,
                    source_text.encode("utf-8"),
                    now,
                )
                if self.repository.draft(source.agent_id) is None:
                    self.repository.insert_draft(
                        connection,
                        agent_id=source.agent_id,
                        draft_id=new_uuid7(),
                        revision=0,
                        source=source.to_dict(),
                        source_file_hash=current_hash,
                        etag=_etag(0, current_hash),
                    )
            for path in root.rglob("*"):
                if path.is_symlink():
                    raise ProjectError("Project directories may not contain symlinks")
                if path.is_file():
                    if path.name == ".env" or path.suffix.lower() in {".key", ".pem"}:
                        raise ProjectError(
                            "secrets must not be stored in a Project directory"
                        )
                    self._index_file(
                        connection,
                        manifest.project_id,
                        root,
                        path,
                        path.read_bytes(),
                        now,
                    )
        return self.project_summary(manifest.project_id)

    def project_summary(self, project_id: str) -> dict[str, Any]:
        project = self.repository.project(project_id)
        if project is None:
            raise ProjectError("unknown Project")
        return {
            "project_id": project["project_id"],
            "root_path": project["root_path"],
            "name": project["name"],
            "manifest_hash": project["manifest_hash"],
            "agents": [
                {
                    "agent_id": agent["agent_id"],
                    "slug": agent["slug"],
                    "source_path": agent["source_path"],
                    "source_file_hash": agent["source_file_hash"],
                }
                for agent in self.repository.agents(project_id)
            ],
        }

    def _index_file(
        self,
        connection: Any,
        project_id: str,
        root: Path,
        path: Path,
        contents: bytes,
        now: str,
    ) -> None:
        digest, object_path = write_object(self.object_root, contents)
        self.repository.add_blob_and_file(
            connection,
            project_id=project_id,
            relative_path=path.relative_to(root).as_posix(),
            digest=digest,
            byte_length=len(contents),
            object_path=str(object_path),
            observed_at=now,
        )

    @staticmethod
    def atomic_write(path: Path, contents: str) -> None:
        """Write inside a checked Project directory with fsync then replace."""
        descriptor, temporary_name = tempfile.mkstemp(prefix=".veyra-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, path)
            descriptor_dir = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor_dir)
            finally:
                os.close(descriptor_dir)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    @staticmethod
    def _canonical_source(value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"

    @staticmethod
    def _parse_yaml(source_text: str, name: str) -> dict[str, Any]:
        try:
            parsed = yaml.safe_load(source_text)
        except yaml.YAMLError as exc:
            raise ProjectError(f"invalid {name} YAML") from exc
        if not isinstance(parsed, dict):
            raise ProjectError(f"{name} must contain an object")
        return parsed

    @staticmethod
    def _read_text(path: Path) -> str:
        if not path.is_file() or path.is_symlink():
            raise ProjectError("required Project file is absent or unsafe")
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ProjectError("Project source must be UTF-8") from exc

    @staticmethod
    def _new_root(value: str | Path) -> Path:
        root = Path(value).expanduser().absolute()
        if root.exists():
            raise ProjectError("selected Project directory already exists")
        if root.parent.is_symlink():
            raise ProjectError("Project parent must not be a symlink")
        return root

    @staticmethod
    def _existing_root(value: str | Path) -> Path:
        root = Path(value).expanduser().absolute()
        if not root.is_dir() or root.is_symlink():
            raise ProjectError("selected Project directory is absent or a symlink")
        return root.resolve(strict=True)

    @staticmethod
    def _safe_child(root: Path, relative: Path) -> Path:
        if relative.is_absolute() or ".." in relative.parts:
            raise ProjectError("Project relative path escapes its root")
        candidate = root / relative
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ProjectError("required Project path is absent") from exc
        if not resolved.is_relative_to(root) or any(
            part.is_symlink() for part in _walk_existing_parts(root, relative)
        ):
            raise ProjectError("Project path or symlink escapes its root")
        return candidate


def _walk_existing_parts(root: Path, relative: Path) -> list[Path]:
    current = root
    parts: list[Path] = []
    for segment in relative.parts:
        current = current / segment
        parts.append(current)
    return parts


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _etag(revision: int, current_file_hash: str) -> str:
    return (
        '"'
        + sha256_digest({"revision": revision, "file_hash": current_file_hash})
        + '"'
    )
