"""Safe managed creation and bounded indexing of Project directories."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from veyra_agent_platform.contracts.agent import (
    AgentSource,
    ProjectAgentDirectory,
    ProjectManifest,
)
from veyra_agent_platform.contracts.canonical import file_hash, sha256_digest
from veyra_agent_platform.contracts.common import new_uuid7
from veyra_agent_platform.local.storage.objects import write_object
from veyra_agent_platform.local.storage.repositories import LocalRepository
from veyra_agent_platform.local.templates import (
    STARTER_TEMPLATE_ID,
    AgentTemplateCatalog,
    AgentTemplateError,
)

MAX_INDEXED_FILE_BYTES = 1_000_000
MAX_INDEXED_TOTAL_BYTES = 10_000_000
MAX_AGENT_IMPORT_BYTES = 1_000_000
_EXCLUDED_DIRECTORIES = {".git", "node_modules", "build", "cache", "runtime"}
_FORBIDDEN_SECRET_NAMES = {".env", "id_rsa", "credentials.json"}
_FORBIDDEN_SECRET_SUFFIXES = {".key", ".pem", ".p12", ".token"}


class ProjectError(ValueError):
    """A selected Project is unsafe, invalid, or unavailable."""


class ProjectService:
    """Keep source files authoritative; SQLite is a bounded, rebuildable index."""

    def __init__(
        self,
        repository: LocalRepository,
        object_root: Path,
        templates: AgentTemplateCatalog | None = None,
        project_storage_root: Path | None = None,
    ) -> None:
        self.repository = repository
        self.object_root = object_root
        self.templates = templates or AgentTemplateCatalog()
        self.project_storage_root = (
            project_storage_root or object_root.parent / "projects"
        )
        self._writer_lock = threading.RLock()

    def create(
        self,
        *,
        root_path: str | Path,
        name: str | None,
        description: str = "",
        sources: list[dict[str, Any]] | None = None,
        template_selections: list[dict[str, str]] | None = None,
        require_new_root: bool = False,
    ) -> dict[str, Any]:
        with self._writer_lock:
            return self._create(
                root_path=root_path,
                name=name,
                description=description,
                sources=sources,
                template_selections=template_selections,
                require_new_root=require_new_root,
            )

    def _create(
        self,
        *,
        root_path: str | Path,
        name: str | None,
        description: str = "",
        sources: list[dict[str, Any]] | None = None,
        template_selections: list[dict[str, str]] | None = None,
        require_new_root: bool = False,
    ) -> dict[str, Any]:
        root = self._new_root(root_path, require_new_root=require_new_root)
        root_preexisted = root.exists()
        root_mode = root.stat().st_mode & 0o777 if root_preexisted else None
        allocated_name = self._allocate_name(name)
        selected_sources = [AgentSource.from_dict(source) for source in (sources or [])]
        selected_sources.extend(
            self._instantiate_template(selection)
            for selection in (template_selections or [])
        )
        forked_sources = [self._fork_template(source) for source in selected_sources]
        if len({source.slug for source in forked_sources}) != len(forked_sources):
            raise ProjectError("Project Agent slugs must be unique")
        manifest = self._manifest(allocated_name, description, forked_sources)
        staging = root.parent / f".{root.name}.veyra-staging-{new_uuid7()}"
        installed = False
        try:
            staging.mkdir(mode=0o700)
            (staging / "agents").mkdir()
            (staging / "resources").mkdir()
            (staging / "tests").mkdir()
            for source in forked_sources:
                agent_root = staging / "agents" / source.slug
                agent_root.mkdir(parents=True)
                (agent_root / "tests").mkdir()
                self.atomic_write(
                    agent_root / "agent.vagent.yaml",
                    self._canonical_source(source.to_dict()),
                )
                self.atomic_write(agent_root / "README.md", f"# {source.name}\n")
            self.atomic_write(
                staging / "project.vproject.yaml", self._canonical_source(manifest)
            )
            self._fsync_tree(staging)
            if root_preexisted and any(root.iterdir()):
                raise ProjectError("selected Project directory is not empty")
            if not root_preexisted and root.exists():
                raise ProjectError("selected Project directory already exists")
            os.replace(staging, root)
            installed = True
            self._fsync_directory(root.parent)
            return self.index(root)
        except BaseException as exc:
            rollback_errors: list[BaseException] = []
            if installed and root.exists():
                try:
                    shutil.rmtree(root)
                    if root_preexisted:
                        root.mkdir(mode=root_mode or 0o700)
                    self._fsync_directory(root.parent)
                except BaseException as rollback_exc:
                    rollback_errors.append(rollback_exc)
            if staging.exists():
                try:
                    shutil.rmtree(staging)
                except BaseException as rollback_exc:
                    rollback_errors.append(rollback_exc)
            for rollback_note in rollback_errors:
                exc.add_note(f"rollback failed: {rollback_note}")
            raise

    def create_managed(
        self,
        *,
        name: str | None,
        description: str = "",
        sources: list[dict[str, Any]] | None = None,
        template_selections: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Create a Project under the application-managed storage root only."""
        storage_root = self._managed_storage_root()
        target = storage_root / f"project-{new_uuid7()}"
        return self.create(
            root_path=target,
            name=name,
            description=description,
            sources=sources,
            template_selections=template_selections,
            require_new_root=True,
        )

    def _allocate_name(
        self, requested_name: str | None, *, exclude_project_id: str | None = None
    ) -> str:
        """Allocate a display name among active Projects under the writer lock."""
        if requested_name is None:
            base = "New project"
        elif not isinstance(requested_name, str):
            raise ProjectError("Project name must be a string")
        else:
            base = requested_name
        base = unicodedata.normalize("NFC", base).strip() or "New project"
        occupied = {
            _name_key(row["name"])
            for row in self.repository.projects()
            if row["project_id"] != exclude_project_id
        }
        candidate = base
        suffix = 1
        while _name_key(candidate) in occupied:
            candidate = f"{base}({suffix})"
            suffix += 1
        return candidate

    def _managed_storage_root(self) -> Path:
        """Create and validate a managed root without traversing symlinks."""
        root = Path(self.project_storage_root).expanduser().absolute()
        current = root
        while True:
            if current.exists() and current.is_symlink():
                raise ProjectError("managed Project storage root must not be a symlink")
            if current == current.parent:
                break
            current = current.parent
        try:
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectError("managed Project storage root is unavailable") from exc
        if not root.is_dir() or root.is_symlink():
            raise ProjectError("managed Project storage root must be a directory")
        return root

    def _is_managed_root(self, root_path: Path) -> bool:
        """Recognize only immediate, non-symlink children allocated by this service."""
        storage_root = self._managed_storage_root()
        candidate = Path(root_path).expanduser().absolute()
        if candidate.parent != storage_root or not candidate.name.startswith(
            "project-"
        ):
            return False
        root = self._existing_root(candidate)
        return root.parent == storage_root and root.name.startswith("project-")

    def _trash_target(self, project_id: str) -> Path:
        storage_root = self._managed_storage_root()
        trash_root = storage_root.parent / "trash" / "projects"
        current = trash_root
        while True:
            if current.exists() and current.is_symlink():
                raise ProjectError("managed Project trash path must not be a symlink")
            if current == current.parent:
                break
            current = current.parent
        try:
            trash_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectError("managed Project trash path is unavailable") from exc
        if not trash_root.is_dir() or trash_root.is_symlink():
            raise ProjectError("managed Project trash path must be a directory")
        target = trash_root / project_id
        if target.exists() or target.is_symlink():
            raise ProjectError(
                "managed Project trash target already exists or is unsafe"
            )
        return target

    @staticmethod
    def _removal_summary(
        project_id: str, disposition: str, removed_at: str
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "project_id": project_id,
            "disposition": disposition,
            "removed_at": removed_at,
        }

    def create_agent(
        self,
        *,
        project_id: str,
        mode: str,
        template_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create one blank or catalog-based Agent inside an existing Project."""
        with self._writer_lock:
            if mode == "blank":
                source = self._starter_source()
                return self._install_prepared_source(
                    project_id=project_id,
                    source=source,
                    name=name,
                    description=description,
                    slug="new-agent",
                    default_name="New Agent",
                )
            if mode == "template":
                if template_id is None:
                    raise ProjectError("template_id is required for template mode")
                source = self._template_source(template_id)
                return self._install_prepared_source(
                    project_id=project_id,
                    source=source,
                    name=name,
                    description=description,
                )
            raise ProjectError("Agent creation mode is unknown")

    def create_agent_from_source(
        self, *, project_id: str, source: AgentSource
    ) -> dict[str, Any]:
        """Install a previously validated Factory source as a new Agent Draft."""
        with self._writer_lock:
            return self._install_prepared_source(project_id=project_id, source=source)

    def import_agent(
        self,
        *,
        project_id: str,
        filename: str | None,
        contents: bytes,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Safely validate and install one portable Agent source file."""
        if not isinstance(filename, str) or not filename.lower().endswith(
            (".vagent.yaml", ".yaml", ".yml")
        ):
            raise ProjectError("import must be a .vagent.yaml, .yaml, or .yml file")
        if not isinstance(contents, bytes) or len(contents) > MAX_AGENT_IMPORT_BYTES:
            raise ProjectError("Agent import exceeds the 1 MiB size limit")
        try:
            source_text = contents.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProjectError("Agent import must be UTF-8") from exc
        source = AgentSource.from_dict(self._parse_yaml(source_text, "Agent import"))
        with self._writer_lock:
            return self._install_prepared_source(
                project_id=project_id,
                source=source,
                name=name,
                description=description,
            )

    def add_agent(
        self, *, project_id: str, template_selection: dict[str, str]
    ) -> dict[str, Any]:
        """Install a legacy catalog selection through the common source installer."""
        with self._writer_lock:
            source = self._instantiate_template(template_selection)
            return self._install_prepared_source(project_id=project_id, source=source)

    def _install_prepared_source(
        self,
        *,
        project_id: str,
        source: AgentSource,
        name: str | None = None,
        description: str | None = None,
        slug: str | None = None,
        default_name: str | None = None,
    ) -> dict[str, Any]:
        """Allocate project-local identity before atomically installing one source."""
        project = self.repository.project(project_id)
        if project is None:
            raise ProjectError("unknown Project")
        root = self._existing_root(project["root_path"])
        manifest_path = self._safe_file(root, Path("project.vproject.yaml"))
        previous_manifest_text = self._read_text(manifest_path)
        manifest = ProjectManifest.from_dict(
            self._parse_yaml(previous_manifest_text, "Project manifest")
        )
        if manifest.project_id != project_id:
            raise ProjectError("Project manifest identity does not match its index")

        source = self._allocate_agent_identity(
            root=root,
            manifest=manifest,
            source=source,
            name=name,
            description=description,
            slug=slug,
            default_name=default_name,
        )
        return self._install_source(
            project_id=project_id,
            root=root,
            manifest_path=manifest_path,
            previous_manifest_text=previous_manifest_text,
            manifest=manifest,
            source=source,
        )

    def _install_source(
        self,
        *,
        project_id: str,
        root: Path,
        manifest_path: Path,
        previous_manifest_text: str,
        manifest: ProjectManifest,
        source: AgentSource,
    ) -> dict[str, Any]:
        """Install source, manifest, and SQLite index with filesystem rollback."""
        existing_ids = {entry.agent_id for entry in manifest.agents}
        existing_slugs = {entry.slug for entry in manifest.agents}
        if source.agent_id in existing_ids or self.repository.agent(source.agent_id):
            raise ProjectError("duplicate Agent ID; use explicit Fork/import")
        if source.slug in existing_slugs:
            raise ProjectError("Project Agent slugs must be unique")

        agents_root = self._safe_directory(root, Path("agents"))
        target = agents_root / source.slug
        if target.exists() or target.is_symlink():
            raise ProjectError("Project Agent path already exists")
        staging = agents_root / f".{source.slug}.veyra-staging-{new_uuid7()}"
        updated_manifest = manifest.to_dict()
        updated_manifest["agents"].append(
            {
                "agent_id": source.agent_id,
                "slug": source.slug,
                "path": f"agents/{source.slug}",
            }
        )
        if not manifest.agents:
            updated_manifest["default_agent_id"] = source.agent_id
        ProjectManifest.from_dict(updated_manifest)

        installed = False
        manifest_replaced = False
        try:
            staging.mkdir(mode=0o700)
            (staging / "tests").mkdir()
            self.atomic_write(
                staging / "agent.vagent.yaml",
                self._canonical_source(source.to_dict()),
            )
            self.atomic_write(staging / "README.md", f"# {source.name}\n")
            self._fsync_tree(staging)
            if target.exists():
                raise ProjectError("Project Agent path already exists")
            os.replace(staging, target)
            installed = True
            self._fsync_directory(agents_root)
            self.atomic_write(manifest_path, self._canonical_source(updated_manifest))
            manifest_replaced = True
            self.index(root)
            return self.agent_summary(project_id, source.agent_id)
        except BaseException as exc:
            rollback_errors: list[BaseException] = []
            if manifest_replaced:
                try:
                    self.atomic_write(manifest_path, previous_manifest_text)
                except BaseException as rollback_exc:
                    rollback_errors.append(rollback_exc)
            if installed and target.exists():
                try:
                    shutil.rmtree(target)
                    self._fsync_directory(agents_root)
                except BaseException as rollback_exc:
                    rollback_errors.append(rollback_exc)
            if staging.exists():
                try:
                    shutil.rmtree(staging)
                except BaseException as rollback_exc:
                    rollback_errors.append(rollback_exc)
            for rollback_note in rollback_errors:
                exc.add_note(f"rollback failed: {rollback_note}")
            raise

    def index(self, root_path: str | Path) -> dict[str, Any]:
        with self._writer_lock:
            return self._index(root_path)

    def _index(self, root_path: str | Path) -> dict[str, Any]:
        root = self._existing_root(root_path)
        self._scan_for_forbidden_names(root)
        manifest_path = self._safe_file(root, Path("project.vproject.yaml"))
        original_manifest_text = self._read_text(manifest_path)
        manifest_text = original_manifest_text
        manifest = ProjectManifest.from_dict(
            self._parse_yaml(manifest_text, "Project manifest")
        )
        allocated_name = self._allocate_name(
            manifest.name, exclude_project_id=manifest.project_id
        )
        manifest_replaced = False
        if allocated_name != manifest.name:
            updated = manifest.to_dict()
            updated["name"] = allocated_name
            manifest = ProjectManifest.from_dict(updated)
            manifest_text = self._canonical_source(manifest.to_dict())
            self.atomic_write(manifest_path, manifest_text)
            manifest_replaced = True
        try:
            return self._index_manifest(root, manifest_path, manifest_text, manifest)
        except BaseException as exc:
            if manifest_replaced:
                try:
                    self.atomic_write(manifest_path, original_manifest_text)
                except BaseException as rollback_exc:
                    exc.add_note(f"rollback failed: {rollback_exc}")
            raise

    def _index_manifest(
        self,
        root: Path,
        manifest_path: Path,
        manifest_text: str,
        manifest: ProjectManifest,
    ) -> dict[str, Any]:
        records, indexed_files = self._collect_allowed_files(
            root, manifest, manifest_path
        )
        now = _utc_now()
        root_text = str(root)
        with self.repository.transaction() as connection:
            bound_project = connection.execute(
                "SELECT * FROM projects WHERE project_id = ?", (manifest.project_id,)
            ).fetchone()
            bound_root = connection.execute(
                "SELECT * FROM projects WHERE root_path = ?", (root_text,)
            ).fetchone()
            if bound_project is not None and bound_project["root_path"] != root_text:
                raise ProjectError("duplicate Project ID; use explicit Fork/import")
            if (
                bound_root is not None
                and bound_root["project_id"] != manifest.project_id
            ):
                raise ProjectError("selected root is already bound to another Project")
            manifest_hash = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
            if bound_project is None:
                self.repository.upsert_project(
                    connection,
                    project_id=manifest.project_id,
                    root_path=root_text,
                    name=manifest.name,
                    description=manifest.description,
                    manifest_hash=manifest_hash,
                    indexed_at=now,
                )
            else:
                connection.execute(
                    """UPDATE projects
                       SET name = ?, description = ?, manifest_hash = ?, indexed_at = ?
                       WHERE project_id = ?""",
                    (
                        manifest.name,
                        manifest.description,
                        manifest_hash,
                        now,
                        manifest.project_id,
                    ),
                )
                connection.execute(
                    "UPDATE projects SET removed_at = NULL WHERE project_id = ?",
                    (manifest.project_id,),
                )
            manifest_agent_ids = {source.agent_id for source, _, _ in records}
            existing_agents = connection.execute(
                """SELECT * FROM agents
                   WHERE project_id = ? AND removed_at IS NULL""",
                (manifest.project_id,),
            ).fetchall()
            stale_agents = {
                row["agent_id"]
                for row in existing_agents
                if row["agent_id"] not in manifest_agent_ids
            }
            for agent_id in stale_agents:
                if (
                    connection.execute(
                        "SELECT 1 FROM agent_versions WHERE agent_id = ?", (agent_id,)
                    ).fetchone()
                    is not None
                ):
                    raise ProjectError("cannot remove an Agent with immutable versions")
            self.repository.delete_agents(connection, stale_agents)
            self.repository.reconcile_files(
                connection,
                manifest.project_id,
                {path.relative_to(root).as_posix() for path in indexed_files},
            )
            for source, source_path, source_text in records:
                current_hash = file_hash(source_text)
                existing = connection.execute(
                    "SELECT * FROM agents WHERE agent_id = ?", (source.agent_id,)
                ).fetchone()
                relative = source_path.relative_to(root).as_posix()
                if (
                    existing is not None
                    and existing["project_id"] != manifest.project_id
                ):
                    raise ProjectError("duplicate Agent ID; use explicit Fork/import")
                if existing is None:
                    self.repository.upsert_agent(
                        connection,
                        agent_id=source.agent_id,
                        project_id=manifest.project_id,
                        slug=source.slug,
                        source_path=relative,
                        source_file_hash=current_hash,
                        indexed_at=now,
                    )
                else:
                    self.repository.refresh_agent(
                        connection,
                        agent_id=source.agent_id,
                        slug=source.slug,
                        source_path=relative,
                        source_file_hash=current_hash,
                        indexed_at=now,
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
            for path in indexed_files:
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
        root = self._existing_root(project["root_path"])
        manifest_path = self._safe_file(root, Path("project.vproject.yaml"))
        manifest = ProjectManifest.from_dict(
            self._parse_yaml(self._read_text(manifest_path), "Project manifest")
        )
        if manifest.project_id != project_id:
            raise ProjectError("Project manifest identity does not match its index")
        entries = sorted(
            manifest.agents,
            key=lambda entry: (
                entry.agent_id != manifest.default_agent_id,
                entry.slug,
            ),
        )
        agents: list[dict[str, Any]] = []
        for entry in entries:
            row = self.repository.agent(entry.agent_id)
            if row is None:
                raise ProjectError("Project Agent is missing from its local index")
            source_path = self._safe_file(root, Path(entry.path) / "agent.vagent.yaml")
            source_text = self._read_text(source_path)
            source = AgentSource.from_dict(self._parse_yaml(source_text, entry.slug))
            if source.agent_id != entry.agent_id or source.slug != entry.slug:
                raise ProjectError("Project Agent identity does not match source")
            agents.append(
                {
                    "agent_id": source.agent_id,
                    "slug": source.slug,
                    "name": source.name,
                    "description": source.description,
                    "pinned": source.agent_id == manifest.default_agent_id,
                    "source_path": row["source_path"],
                    "source_file_hash": file_hash(source_text),
                }
            )
        return {
            "schema_version": "1.0",
            "project_id": project["project_id"],
            "root_path": project["root_path"],
            "name": project["name"],
            "description": project["description"],
            "pinned": project["pinned_at"] is not None,
            "pinned_at": project["pinned_at"],
            "manifest_hash": project["manifest_hash"],
            "default_agent_id": manifest.default_agent_id,
            "agents": agents,
            "agent_count": len(agents),
            "indexed_at": project["indexed_at"],
        }

    def pin_agent(self, project_id: str, agent_id: str) -> dict[str, Any]:
        """Make one listed Agent the Project default and first sidebar entry."""
        with self._writer_lock:
            _, root, manifest_path, previous_text, manifest = (
                self._project_manifest_state(project_id)
            )
            selected = next(
                (entry for entry in manifest.agents if entry.agent_id == agent_id),
                None,
            )
            if selected is None:
                raise ProjectError("unknown Agent in Project")
            updated = manifest.to_dict()
            updated["default_agent_id"] = agent_id
            updated["agents"] = [
                selected.to_dict(),
                *[
                    entry.to_dict()
                    for entry in manifest.agents
                    if entry.agent_id != agent_id
                ],
            ]
            validated = ProjectManifest.from_dict(updated)
            try:
                self.atomic_write(
                    manifest_path, self._canonical_source(validated.to_dict())
                )
                return self.index(root)
            except BaseException as exc:
                try:
                    self.atomic_write(manifest_path, previous_text)
                except BaseException as rollback_exc:
                    exc.add_note(f"rollback failed: {rollback_exc}")
                raise

    def _project_manifest_state(
        self, project_id: str
    ) -> tuple[Any, Path, Path, str, ProjectManifest]:
        """Load one active Project and its authoritative, identity-bound manifest."""
        project = self.repository.project(project_id)
        if project is None:
            raise ProjectError("unknown Project")
        root = self._existing_root(project["root_path"])
        manifest_path = self._safe_file(root, Path("project.vproject.yaml"))
        manifest_text = self._read_text(manifest_path)
        manifest = ProjectManifest.from_dict(
            self._parse_yaml(manifest_text, "Project manifest")
        )
        if manifest.project_id != project_id:
            raise ProjectError("Project manifest identity does not match its index")
        return project, root, manifest_path, manifest_text, manifest

    def _agent_trash_target(self, project_id: str, agent_id: str) -> Path:
        """Allocate one non-symlink application trash target for an Agent source."""
        storage_root = self._managed_storage_root()
        trash_root = storage_root.parent / "trash" / "agents" / project_id
        current = trash_root
        while True:
            if current.exists() and current.is_symlink():
                raise ProjectError("managed Agent trash path must not be a symlink")
            if current == current.parent:
                break
            current = current.parent
        try:
            trash_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectError("managed Agent trash path is unavailable") from exc
        if not trash_root.is_dir() or trash_root.is_symlink():
            raise ProjectError("managed Agent trash path must be a directory")
        target = trash_root / agent_id
        if target.exists() or target.is_symlink():
            raise ProjectError("managed Agent trash target already exists or is unsafe")
        return target

    def remove_agent(self, project_id: str, agent_id: str) -> dict[str, Any]:
        """Move an Agent source directory to application trash and retain history."""
        with self._writer_lock:
            _, root, manifest_path, previous_text, manifest = (
                self._project_manifest_state(project_id)
            )
            selected = next(
                (entry for entry in manifest.agents if entry.agent_id == agent_id),
                None,
            )
            if selected is None:
                raise ProjectError("unknown Agent in Project")
            remaining = [
                entry for entry in manifest.agents if entry.agent_id != agent_id
            ]
            updated = manifest.to_dict()
            updated["agents"] = [entry.to_dict() for entry in remaining]
            updated["default_agent_id"] = (
                remaining[0].agent_id
                if manifest.default_agent_id == agent_id and remaining
                else manifest.default_agent_id
                if manifest.default_agent_id != agent_id
                else None
            )
            validated = ProjectManifest.from_dict(updated)
            source = self._safe_directory(root, Path(selected.path))
            target = self._agent_trash_target(project_id, agent_id)
            removed_at = _utc_now()
            moved = False
            marked = False
            try:
                os.replace(source, target)
                moved = True
                self._fsync_directory(source.parent)
                self._fsync_directory(target.parent)
                self.atomic_write(
                    manifest_path, self._canonical_source(validated.to_dict())
                )
                if not self.repository.remove_agent(agent_id, removed_at):
                    raise ProjectError("unknown Agent in Project")
                marked = True
                project = self.index(root)
                return {
                    "schema_version": "1.0",
                    "project_id": project_id,
                    "agent_id": agent_id,
                    "disposition": "trashed",
                    "removed_at": removed_at,
                    "project": project,
                }
            except BaseException as exc:
                rollback_errors: list[BaseException] = []
                if marked:
                    try:
                        self.repository.restore_agent(agent_id)
                    except BaseException as rollback_exc:
                        rollback_errors.append(rollback_exc)
                try:
                    self.atomic_write(manifest_path, previous_text)
                except BaseException as rollback_exc:
                    rollback_errors.append(rollback_exc)
                if moved and target.exists():
                    try:
                        os.replace(target, source)
                        self._fsync_directory(source.parent)
                        self._fsync_directory(target.parent)
                    except BaseException as rollback_exc:
                        rollback_errors.append(rollback_exc)
                for rollback_error in rollback_errors:
                    exc.add_note(f"rollback failed: {rollback_error}")
                raise

    def set_pinned(self, project_id: str, *, pinned: bool) -> dict[str, Any]:
        with self._writer_lock:
            if self.repository.project(project_id) is None:
                raise ProjectError("unknown Project")
            self.repository.set_project_pinned(
                project_id, _utc_now() if pinned else None
            )
            return self.project_summary(project_id)

    def edit(
        self,
        project_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        pinned: bool | None = None,
    ) -> dict[str, Any]:
        """Apply portable metadata changes before re-indexing their source manifest."""
        with self._writer_lock:
            project = self.repository.project(project_id)
            if project is None:
                raise ProjectError("unknown Project")
            if name is None and description is None:
                if pinned is None:
                    raise ProjectError("at least one Project field is required")
                return self.set_pinned(project_id, pinned=pinned)

            root = self._existing_root(project["root_path"])
            manifest_path = self._safe_file(root, Path("project.vproject.yaml"))
            previous_text = self._read_text(manifest_path)
            manifest = ProjectManifest.from_dict(
                self._parse_yaml(previous_text, "Project manifest")
            )
            if manifest.project_id != project_id:
                raise ProjectError("Project manifest identity does not match its index")
            updated = manifest.to_dict()
            if name is not None:
                updated["name"] = self._allocate_name(
                    name, exclude_project_id=project_id
                )
            if description is not None:
                updated["description"] = description
            validated = ProjectManifest.from_dict(updated)
            try:
                self.atomic_write(
                    manifest_path, self._canonical_source(validated.to_dict())
                )
                result = self.index(root)
            except BaseException as exc:
                try:
                    self.atomic_write(manifest_path, previous_text)
                except BaseException as rollback_exc:
                    exc.add_note(f"rollback failed: {rollback_exc}")
                raise
            if pinned is not None:
                result = self.set_pinned(project_id, pinned=pinned)
            return result

    def remove(self, project_id: str) -> dict[str, Any]:
        """Soft-remove a Project, moving only application-managed roots to trash."""
        with self._writer_lock:
            project = self.repository.project(project_id)
            if project is None:
                raise ProjectError("unknown Project")
            removed_at = _utc_now()
            root = Path(project["root_path"])
            if not self._is_managed_root(root):
                if not self.repository.remove_project(project_id, removed_at):
                    raise ProjectError("unknown Project")
                return self._removal_summary(project_id, "unlinked", removed_at)

            source = self._existing_root(root)
            target = self._trash_target(project_id)
            moved = False
            try:
                os.replace(source, target)
                moved = True
                self._fsync_directory(source.parent)
                self._fsync_directory(target.parent)
                if not self.repository.remove_project(project_id, removed_at):
                    raise ProjectError("unknown Project")
            except BaseException as exc:
                if moved:
                    try:
                        os.replace(target, source)
                        self._fsync_directory(source.parent)
                        self._fsync_directory(target.parent)
                    except BaseException as rollback_exc:
                        exc.add_note(f"rollback failed: {rollback_exc}")
                raise
            return self._removal_summary(project_id, "trashed", removed_at)

    def agent_summary(self, project_id: str, agent_id: str) -> dict[str, Any]:
        """Return an Agent summary parsed from its authoritative source file."""
        project = self.repository.project(project_id)
        agent = self.repository.agent(agent_id)
        if project is None:
            raise ProjectError("unknown Project")
        if agent is None or agent["project_id"] != project_id:
            raise ProjectError("unknown Agent in Project")
        root = self._existing_root(project["root_path"])
        source_path = self._safe_file(root, Path(agent["source_path"]))
        source_text = self._read_text(source_path)
        source = AgentSource.from_dict(self._parse_yaml(source_text, agent["slug"]))
        if source.agent_id != agent_id or source.slug != agent["slug"]:
            raise ProjectError("Project Agent identity does not match source")
        return {
            "schema_version": "1.0",
            "project_id": project_id,
            "agent_id": source.agent_id,
            "slug": source.slug,
            "name": source.name,
            "description": source.description,
            "source_path": agent["source_path"],
            "source_file_hash": file_hash(source_text),
            "node_count": len(source.nodes),
            "transition_count": len(source.transitions),
            "component_types": sorted(
                {node.component_type.value for node in source.nodes}
            ),
        }

    def template_metadata(self) -> list[dict[str, str]]:
        return self.templates.metadata()

    def _starter_source(self) -> AgentSource:
        return self._template_source(STARTER_TEMPLATE_ID)

    def _template_source(self, template_id: str) -> AgentSource:
        try:
            return self.templates.source(template_id)
        except AgentTemplateError as exc:
            raise ProjectError(str(exc)) from exc

    def _instantiate_template(self, selection: dict[str, str]) -> AgentSource:
        try:
            return self.templates.instantiate(**selection)
        except (AgentTemplateError, TypeError) as exc:
            raise ProjectError(str(exc)) from exc

    def _allocate_agent_identity(
        self,
        *,
        root: Path,
        manifest: ProjectManifest,
        source: AgentSource,
        name: str | None,
        description: str | None,
        slug: str | None,
        default_name: str | None,
    ) -> AgentSource:
        """Fork a source and reserve a safe display name and directory slug."""
        occupied_names = {
            self._agent_source(root, entry).name for entry in manifest.agents
        }
        name_override = _nonblank_optional_text(name)
        description_override = _nonblank_optional_text(description)
        base_name = name_override or default_name or source.name
        allocated_name = self._allocate_agent_name(base_name, occupied_names)
        allocated_slug = self._allocate_agent_slug(
            slug or source.slug, {entry.slug for entry in manifest.agents}
        )
        prepared = source.to_dict()
        prepared.update(
            {
                "agent_id": new_uuid7(),
                "name": allocated_name,
                "slug": allocated_slug,
                "description": description_override or source.description,
            }
        )
        return AgentSource.from_dict(prepared)

    def _agent_source(self, root: Path, entry: ProjectAgentDirectory) -> AgentSource:
        source_path = self._safe_file(root, Path(entry.path) / "agent.vagent.yaml")
        source = AgentSource.from_dict(
            self._parse_yaml(self._read_text(source_path), entry.slug)
        )
        if source.agent_id != entry.agent_id or source.slug != entry.slug:
            raise ProjectError("Project manifest Agent identity does not match source")
        return source

    @staticmethod
    def _allocate_agent_name(base: str, occupied: set[str]) -> str:
        if not isinstance(base, str):
            raise ProjectError("Agent name must be a string")
        normalized = unicodedata.normalize("NFC", base).strip()
        if not normalized:
            raise ProjectError("Agent name must not be empty")
        occupied_keys = {_name_key(value) for value in occupied}
        candidate = normalized
        suffix = 1
        while _name_key(candidate) in occupied_keys:
            candidate = f"{normalized}({suffix})"
            suffix += 1
        return candidate

    @staticmethod
    def _allocate_agent_slug(base: str, occupied: set[str]) -> str:
        if not isinstance(base, str) or not base:
            raise ProjectError("Agent slug must be a non-empty string")
        candidate = base
        suffix = 1
        while candidate in occupied:
            suffix_text = f"-{suffix}"
            candidate = f"{base[: 63 - len(suffix_text)]}{suffix_text}"
            suffix += 1
        return candidate

    def _collect_allowed_files(
        self, root: Path, manifest: ProjectManifest, manifest_path: Path
    ) -> tuple[list[tuple[AgentSource, Path, str]], list[Path]]:
        files = [manifest_path]
        records: list[tuple[AgentSource, Path, str]] = []
        for entry in manifest.agents:
            agent_dir = self._safe_directory(root, Path(entry.path))
            source_path = self._safe_file(root, Path(entry.path) / "agent.vagent.yaml")
            readme_path = self._safe_file(root, Path(entry.path) / "README.md")
            test_dir = self._safe_directory(root, Path(entry.path) / "tests")
            source_text = self._read_text(source_path)
            source = AgentSource.from_dict(self._parse_yaml(source_text, entry.slug))
            if source.agent_id != entry.agent_id or source.slug != entry.slug:
                raise ProjectError(
                    "Project manifest Agent identity does not match source"
                )
            records.append((source, source_path, source_text))
            files.extend([source_path, readme_path])
            files.extend(self._files_below(test_dir))
            if agent_dir.is_symlink():
                raise ProjectError("Project path or symlink escapes its root")
        files.extend(self._files_below(self._safe_directory(root, Path("resources"))))
        files.extend(self._files_below(self._safe_directory(root, Path("tests"))))
        unique = sorted(set(files))
        total = 0
        for path in unique:
            if path.is_symlink():
                raise ProjectError("Project files may not be symlinks")
            size = path.stat().st_size
            if size > MAX_INDEXED_FILE_BYTES:
                raise ProjectError("Project file exceeds the indexing size limit")
            total += size
        if total > MAX_INDEXED_TOTAL_BYTES:
            raise ProjectError("Project exceeds the indexing total size limit")
        return records, unique

    def _files_below(self, directory: Path) -> list[Path]:
        files: list[Path] = []
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise ProjectError("Project files may not be symlinks")
            if path.is_file():
                files.append(path)
        return files

    def _scan_for_forbidden_names(self, root: Path) -> None:
        for _, child_directories, filenames in os.walk(root, followlinks=False):
            child_directories[:] = [
                name for name in child_directories if name not in _EXCLUDED_DIRECTORIES
            ]
            for name in filenames:
                if (
                    name in _FORBIDDEN_SECRET_NAMES
                    or Path(name).suffix.lower() in _FORBIDDEN_SECRET_SUFFIXES
                ):
                    raise ProjectError(
                        "secrets must not be stored in a Project directory"
                    )

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
        descriptor, temporary_name = tempfile.mkstemp(prefix=".veyra-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, path)
            ProjectService._fsync_directory(path.parent)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @classmethod
    def _fsync_tree(cls, root: Path) -> None:
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_file():
                with path.open("rb") as stream:
                    os.fsync(stream.fileno())
            elif path.is_dir():
                cls._fsync_directory(path)
        cls._fsync_directory(root)

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
    def _new_root(value: str | Path, *, require_new_root: bool = False) -> Path:
        root = Path(value).expanduser().absolute()
        if root.is_symlink():
            if require_new_root:
                raise ProjectError("Project directory already exists")
            raise ProjectError("selected Project directory is absent or a symlink")
        if root.exists():
            if require_new_root:
                raise ProjectError("Project directory already exists")
            if not root.is_dir() or root.is_symlink():
                raise ProjectError("selected Project directory is absent or a symlink")
            if any(root.iterdir()):
                raise ProjectError("selected Project directory is not empty")
        current = root.parent
        while True:
            if current.exists() and current.is_symlink():
                raise ProjectError("Project ancestor must not be a symlink")
            if current == current.parent:
                break
            current = current.parent
        return root

    @staticmethod
    def _existing_root(value: str | Path) -> Path:
        root = Path(value).expanduser().absolute()
        if not root.is_dir() or root.is_symlink():
            raise ProjectError("selected Project directory is absent or a symlink")
        return root.resolve(strict=True)

    @staticmethod
    def _safe_file(root: Path, relative: Path) -> Path:
        path = ProjectService._safe_path(root, relative)
        if not path.is_file():
            raise ProjectError("required Project file is absent")
        return path

    @staticmethod
    def _safe_directory(root: Path, relative: Path) -> Path:
        path = ProjectService._safe_path(root, relative)
        if not path.is_dir():
            raise ProjectError("required Project directory is absent")
        return path

    @staticmethod
    def _safe_path(root: Path, relative: Path) -> Path:
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

    @staticmethod
    def _fork_template(source: AgentSource) -> AgentSource:
        forked = source.to_dict()
        forked["agent_id"] = new_uuid7()
        return AgentSource.from_dict(forked)

    @staticmethod
    def _manifest(
        name: str, description: str, sources: list[AgentSource]
    ) -> dict[str, Any]:
        manifest = {
            "schema_version": "1.0",
            "project_version": "1",
            "project_id": new_uuid7(),
            "name": name,
            "description": description,
            "agents": [
                {
                    "agent_id": source.agent_id,
                    "slug": source.slug,
                    "path": f"agents/{source.slug}",
                }
                for source in sources
            ],
            "default_agent_id": sources[0].agent_id if sources else None,
            "resource_policy": {
                "max_concurrent_runs": 1,
                "max_nodes_per_run": 128,
                "max_run_seconds": 3600,
            },
        }
        return ProjectManifest.from_dict(manifest).to_dict()


def _walk_existing_parts(root: Path, relative: Path) -> list[Path]:
    current = root
    parts: list[Path] = []
    for segment in relative.parts:
        current = current / segment
        parts.append(current)
    return parts


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _name_key(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip().casefold()


def _nonblank_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProjectError("Agent override must be a string")
    return None if not value.strip() else value


def _etag(revision: int, current_file_hash: str) -> str:
    return (
        '"'
        + sha256_digest({"revision": revision, "file_hash": current_file_hash})
        + '"'
    )
