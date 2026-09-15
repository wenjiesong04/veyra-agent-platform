"""Safe managed creation and bounded indexing of Project directories."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import unicodedata
from collections.abc import Mapping
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
from veyra_agent_platform.contracts.resource import (
    ProjectResourceBinding,
    ResourceKind,
    ResourceManifest,
)
from veyra_agent_platform.contracts.workflow import WorkflowSource
from veyra_agent_platform.local.projects.layout import (
    INDEXED_ROOT_DIRECTORIES,
    agent_resource_manifest,
    blank_knowledge_document,
    blank_workflow_source,
    ensure_project_layout,
    knowledge_resource_manifest,
    resource_yaml_path,
    workflow_resource_manifest,
)
from veyra_agent_platform.local.projects.origins import CommunityAgentOrigin
from veyra_agent_platform.local.projects.packaging import (
    MAX_PROJECT_ARCHIVE_BYTES,
    ProjectArchive,
    ProjectPackageError,
    pack_project_files,
    unpack_project_archive,
)
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
_UNSAFE_FOLDER_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ProjectError(ValueError):
    """A selected Project is unsafe, invalid, or unavailable."""

    def __init__(self, message: str, code: str = "project_invalid") -> None:
        super().__init__(message)
        self.code = code


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
        fork_identities: bool = True,
        parents: dict[str, str] | None = None,
        extra_files: dict[str, bytes] | None = None,
        default_agent_id: str | None = None,
        imported_bundle: ProjectArchive | None = None,
    ) -> dict[str, Any]:
        with self._writer_lock:
            return self._create(
                root_path=root_path,
                name=name,
                description=description,
                sources=sources,
                template_selections=template_selections,
                require_new_root=require_new_root,
                fork_identities=fork_identities,
                parents=parents,
                extra_files=extra_files,
                default_agent_id=default_agent_id,
                imported_bundle=imported_bundle,
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
        fork_identities: bool = True,
        parents: dict[str, str] | None = None,
        extra_files: dict[str, bytes] | None = None,
        default_agent_id: str | None = None,
        imported_bundle: ProjectArchive | None = None,
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
        forked_sources = (
            [self._fork_template(source) for source in selected_sources]
            if fork_identities
            else selected_sources
        )
        if len({source.slug for source in forked_sources}) != len(forked_sources):
            raise ProjectError("Project Agent slugs must be unique")
        manifest = self._manifest(
            allocated_name,
            description,
            forked_sources,
            parents=parents,
            default_agent_id=None if fork_identities else default_agent_id,
        )
        if imported_bundle is not None:
            manifest = imported_bundle.manifest.to_dict()
            manifest["name"] = allocated_name
        staging = root.parent / f".{root.name}.veyra-staging-{new_uuid7()}"
        installed = False
        try:
            staging.mkdir(mode=0o700)
            ensure_project_layout(staging)
            for source in forked_sources:
                agent_root = staging / "agents" / source.slug
                agent_root.mkdir(parents=True, exist_ok=True)
                (agent_root / "tests").mkdir()
                self.atomic_write(
                    agent_root / "agent.vagent.yaml",
                    self._canonical_source(source.to_dict()),
                )
                self.atomic_write(
                    agent_root / "resource.yaml",
                    self._canonical_source(agent_resource_manifest(source)),
                )
                self.atomic_write(agent_root / "README.md", f"# {source.name}\n")
            self._write_extra_files(staging, extra_files or {})
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
            if imported_bundle is not None:
                manifest_path = root / "project.vproject.yaml"
                return self._index_manifest(
                    root,
                    manifest_path,
                    self._read_text(manifest_path),
                    ProjectManifest.from_dict(manifest),
                    imported_bundle=imported_bundle,
                )
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
        fork_identities: bool = True,
        parents: dict[str, str] | None = None,
        extra_files: dict[str, bytes] | None = None,
        default_agent_id: str | None = None,
        imported_bundle: ProjectArchive | None = None,
    ) -> dict[str, Any]:
        """Create a Project under the application-managed storage root only."""
        with self._writer_lock:
            requested = None if name is None else self._folder_name_from_display(name)
            allocated = self._allocate_name(requested)
            target = self._allocate_managed_folder(allocated)
            if target.name != allocated:
                allocated = self._allocate_name(target.name)
                target = self._allocate_managed_folder(allocated)
            return self._create(
                root_path=target,
                name=allocated,
                description=description,
                sources=sources,
                template_selections=template_selections,
                require_new_root=True,
                fork_identities=fork_identities,
                parents=parents,
                extra_files=extra_files,
                default_agent_id=default_agent_id,
                imported_bundle=imported_bundle,
            )

    def reconcile_managed_storage(self) -> None:
        """Keep managed folders named after the Project and stored relatively."""
        with self._writer_lock:
            for row in list(self.repository.projects()):
                try:
                    root = self._existing_root(row["root_path"])
                except ProjectError:
                    continue
                if not self._is_managed_root(root):
                    continue
                aligned = self._align_managed_folder(
                    row["project_id"], row["name"], root
                )
                stored = self._stored_root_text(aligned)
                if stored != row["root_path"]:
                    self._rewrite_stored_root(row["project_id"], stored)

    def _folder_name_from_display(self, name: str) -> str:
        cleaned = unicodedata.normalize("NFC", name).strip()
        cleaned = _UNSAFE_FOLDER_CHARS.sub("", cleaned).rstrip(" .")
        return cleaned[:255] or "New project"

    def _allocate_managed_folder(
        self, display_name: str, *, occupy: Path | None = None
    ) -> Path:
        storage = self._managed_storage_root()
        base = self._folder_name_from_display(display_name)
        occupy_resolved = occupy.resolve() if occupy is not None else None
        suffix = 0
        while True:
            folder = base if suffix == 0 else f"{base}({suffix})"
            candidate = storage / folder
            if occupy_resolved is not None:
                try:
                    if occupy is not None and candidate.resolve() == occupy_resolved:
                        return occupy
                except OSError:
                    pass
            if not candidate.exists() and not candidate.is_symlink():
                return candidate
            suffix += 1

    def _align_managed_folder(
        self, project_id: str, display_name: str, root: Path
    ) -> Path:
        desired = self._allocate_managed_folder(display_name, occupy=root)
        if desired == root:
            return root
        try:
            os.replace(root, desired)
        except OSError as exc:
            raise ProjectError("managed Project folder could not be renamed") from exc
        self._fsync_directory(desired.parent)
        self._rewrite_stored_root(project_id, desired.name)
        return desired

    def _stored_root_text(self, root: Path) -> str:
        """Persist a storage-root-relative folder name for managed Projects."""
        resolved = root.expanduser().absolute()
        if self._is_managed_root(resolved):
            return resolved.name
        return str(resolved.resolve(strict=False))

    def _rewrite_stored_root(self, project_id: str, stored: str) -> None:
        with self.repository.transaction() as connection:
            connection.execute(
                "UPDATE projects SET root_path = ? WHERE project_id = ?",
                (stored, project_id),
            )

    def _same_stored_root(self, stored: str, root: Path) -> bool:
        try:
            return self._existing_root(stored) == root.resolve(strict=True)
        except ProjectError:
            return stored == self._stored_root_text(root)

    def export_archive(self, project_id: str) -> tuple[bytes, str]:
        """Pack indexed Project source files into a portable zip archive."""
        _, root, manifest_path, _, manifest = self._project_manifest_state(project_id)
        _records, files = self._collect_allowed_files(root, manifest, manifest_path)
        try:
            snapshots: dict[str, bytes] = {}
            for entry in manifest.workflows:
                workflow = self._workflow_source(root, entry)
                for node in workflow.nodes:
                    if not node.agent_ref:
                        continue
                    agent_id, version_id = node.agent_ref.split("@", 1)
                    owner = next(
                        (item for item in manifest.agents if item.agent_id == agent_id),
                        None,
                    )
                    version = self.repository.version(version_id)
                    if (
                        owner is None
                        or version is None
                        or version["agent_id"] != agent_id
                    ):
                        raise ProjectPackageError(
                            "Workflow requires a committed Project Agent version"
                        )
                    snapshots[f"{owner.path}/versions/{version_id}.json"] = (
                        self._canonical_source(
                            {
                                "version_id": version_id,
                                "agent_id": agent_id,
                                "source": json.loads(version["source_json"]),
                                "source_hash": version["source_hash"],
                            }
                        ).encode("utf-8")
                    )
            payload = pack_project_files(root, files, extra_files=snapshots)
        except ProjectPackageError as exc:
            raise _package_error(exc) from exc
        return payload, _archive_filename(manifest.name)

    def import_archive(
        self, *, filename: str | None, contents: bytes
    ) -> dict[str, Any]:
        """Install a portable Project archive as a new managed Project with new IDs."""
        try:
            bundle = unpack_project_archive(filename, contents)
        except ProjectPackageError as exc:
            raise _package_error(exc) from exc
        return self.create_managed(
            name=bundle.name,
            description=bundle.description,
            sources=[source.to_dict() for source in bundle.sources],
            fork_identities=False,
            parents=bundle.parents,
            extra_files=bundle.extra_files,
            default_agent_id=bundle.default_agent_id,
            imported_bundle=bundle,
        )

    def import_archive_from_path(self, path: str | Path) -> dict[str, Any]:
        """Install a native-selected zip without copying bytes through the browser."""
        archive = Path(path).expanduser()
        if archive.is_symlink() or not archive.is_file():
            raise ProjectError(
                "selected archive is absent or unsafe", "project_package_invalid"
            )
        if not archive.name.lower().endswith(".zip"):
            raise ProjectError(
                "selected archive is not a zip file", "project_package_invalid"
            )
        with archive.open("rb") as handle:
            contents = handle.read(MAX_PROJECT_ARCHIVE_BYTES + 1)
        return self.import_archive(filename=archive.name, contents=contents)

    def list_files(self, project_id: str) -> dict[str, Any]:
        """List indexed Project source files without exposing runtime state."""
        _, root, manifest_path, _, manifest = self._project_manifest_state(project_id)
        _records, files = self._collect_allowed_files(root, manifest, manifest_path)
        listed: list[dict[str, Any]] = []
        for path in files:
            relative = path.relative_to(root).as_posix()
            kind, agent_id = _file_kind(relative, manifest)
            item: dict[str, Any] = {
                "path": relative,
                "kind": kind,
                "byte_length": path.stat().st_size,
            }
            if agent_id is not None:
                item["agent_id"] = agent_id
            listed.append(item)
        return {
            "schema_version": "1.0",
            "project_id": project_id,
            "files": listed,
        }

    def file_content(self, project_id: str, relative_path: str) -> dict[str, Any]:
        """Return UTF-8 text for one indexed Project source file."""
        listing = self.list_files(project_id)
        selected = next(
            (item for item in listing["files"] if item["path"] == relative_path),
            None,
        )
        if selected is None:
            raise ProjectError("unknown Project file")
        project = self.repository.project(project_id)
        if project is None:
            raise ProjectError("unknown Project")
        root = self._existing_root(project["root_path"])
        path = self._safe_file(root, Path(relative_path))
        return {
            **selected,
            "schema_version": "1.0",
            "project_id": project_id,
            "text": self._read_text(path),
        }

    def project_resource_bindings(
        self, project_id: str
    ) -> tuple[ProjectResourceBinding, ...]:
        """Return the portable Catalog selections declared by one Project."""
        _, _, _, _, manifest = self._project_manifest_state(project_id)
        return manifest.resources

    def project_resource_usage(
        self, project_id: str, *, include_versions: bool = False
    ) -> dict[str, list[dict[str, str]]]:
        """Find Catalog references used by Agent and Workflow source definitions."""
        _, root, _, _, manifest = self._project_manifest_state(project_id)
        usage: dict[str, list[dict[str, str]]] = {}

        def record(source: Any, kind: str, resource_id: str) -> None:
            references = set(source.lock)
            for node in source.nodes:
                uses = getattr(node, "uses", None)
                if uses:
                    references.add(uses)
            for binding in (source.ui.get("bindings") or {}).values():
                if isinstance(binding, Mapping) and binding.get("reference"):
                    references.add(binding["reference"])
            for reference in references:
                usage.setdefault(reference, []).append(
                    {"kind": kind, "resource_id": resource_id, "name": source.name}
                )

        for agent_entry in manifest.agents:
            record(self._agent_source(root, agent_entry), "agent", agent_entry.agent_id)
        if include_versions:
            for version in self.repository.project_agent_versions(project_id):
                record(
                    AgentSource.from_dict(json.loads(version["source_json"])),
                    "agent",
                    version["agent_id"],
                )
        for workflow_entry in manifest.workflows:
            record(
                self._workflow_source(root, workflow_entry),
                "workflow",
                workflow_entry.resource_id,
            )
            if include_versions:
                for version in self.repository.workflow_versions(
                    workflow_entry.resource_id
                ):
                    record(
                        WorkflowSource.from_dict(json.loads(version["source_json"])),
                        "workflow",
                        workflow_entry.resource_id,
                    )
        return usage

    def replace_project_resource_bindings(
        self, project_id: str, bindings: tuple[ProjectResourceBinding, ...]
    ) -> dict[str, Any]:
        """Atomically replace the portable resource selection in the manifest."""
        with self._writer_lock:
            _, root, manifest_path, previous_text, manifest = (
                self._project_manifest_state(project_id)
            )
            updated = manifest.to_dict()
            updated["resources"] = [binding.to_dict() for binding in bindings]
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
        """Recognize only immediate, non-symlink children of managed storage."""
        storage_root = self._managed_storage_root()
        candidate = Path(root_path)
        if not candidate.is_absolute():
            if (
                len(candidate.parts) != 1
                or candidate.name in {".", ".."}
                or ".." in candidate.parts
            ):
                return False
            candidate = storage_root / candidate
        candidate = candidate.expanduser().absolute()
        try:
            storage_resolved = storage_root.resolve()
            root = self._existing_root(candidate)
        except (OSError, ProjectError):
            return False
        return root.parent == storage_resolved

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
        parent_agent_id: str | None = None,
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
                    parent_agent_id=parent_agent_id,
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
                    parent_agent_id=parent_agent_id,
                )
            raise ProjectError("Agent creation mode is unknown")

    def create_workflow(
        self,
        *,
        project_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a blank Start → Output Workflow inside an existing Project."""
        with self._writer_lock:
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
            occupied_names = {
                self._workflow_source(root, entry).name for entry in manifest.workflows
            }
            allocated_name = self._allocate_agent_name(
                _nonblank_optional_text(name) or "New Workflow", occupied_names
            )
            allocated_slug = self._allocate_agent_slug(
                "new-workflow", {entry.slug for entry in manifest.workflows}
            )
            source = blank_workflow_source(
                slug=allocated_slug,
                name=allocated_name,
                description=_nonblank_optional_text(description)
                or "A blank Workflow that orchestrates Agents.",
            )
            return self._install_workflow(
                project_id=project_id,
                root=root,
                manifest_path=manifest_path,
                previous_manifest_text=previous_manifest_text,
                manifest=manifest,
                source=source,
            )

    def create_agent_from_source(
        self,
        *,
        project_id: str,
        source: AgentSource,
        name: str | None = None,
        description: str | None = None,
        parent_agent_id: str | None = None,
        extra_files: dict[str, bytes] | None = None,
    ) -> dict[str, Any]:
        """Install a previously validated Factory source as a new Agent Draft."""
        with self._writer_lock:
            return self._install_prepared_source(
                project_id=project_id,
                source=source,
                name=name,
                description=description,
                parent_agent_id=parent_agent_id,
                extra_files=extra_files,
            )

    def import_agent(
        self,
        *,
        project_id: str,
        filename: str | None,
        contents: bytes,
        name: str | None = None,
        description: str | None = None,
        parent_agent_id: str | None = None,
        community_origin: CommunityAgentOrigin | None = None,
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
        if community_origin is not None and (
            community_origin.slug != source.slug
            or community_origin.version != source.version
            or community_origin.source_hash != source.source_hash
        ):
            raise ProjectError(
                "Community Agent origin does not match the imported source",
                "community_origin_mismatch",
            )
        with self._writer_lock:
            return self._install_prepared_source(
                project_id=project_id,
                source=source,
                name=name,
                description=description,
                parent_agent_id=parent_agent_id,
                community_origin=community_origin,
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
        parent_agent_id: str | None = None,
        community_origin: CommunityAgentOrigin | None = None,
        extra_files: dict[str, bytes] | None = None,
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
        if parent_agent_id is not None and not any(
            entry.agent_id == parent_agent_id for entry in manifest.agents
        ):
            raise ProjectError("parent Agent was not found in this Project")

        source = self._allocate_agent_identity(
            root=root,
            manifest=manifest,
            source=source,
            name=name,
            description=description,
            slug=slug,
            default_name=default_name,
        )
        result = self._install_source(
            project_id=project_id,
            root=root,
            manifest_path=manifest_path,
            previous_manifest_text=previous_manifest_text,
            manifest=manifest,
            source=source,
            parent_agent_id=parent_agent_id,
            extra_files=extra_files,
        )
        if community_origin is None:
            return result
        with self.repository.transaction() as connection:
            self.repository.upsert_agent_origin(
                connection,
                local_agent_id=source.agent_id,
                owner_handle=community_origin.owner_handle,
                remote_slug=community_origin.slug,
                remote_version=community_origin.version,
                remote_source_hash=community_origin.source_hash,
                imported_at=_utc_now(),
            )
        return self.agent_summary(project_id, source.agent_id)

    def _install_source(
        self,
        *,
        project_id: str,
        root: Path,
        manifest_path: Path,
        previous_manifest_text: str,
        manifest: ProjectManifest,
        source: AgentSource,
        parent_agent_id: str | None = None,
        extra_files: dict[str, bytes] | None = None,
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
                "version": source.version,
                **(
                    {"parent_agent_id": parent_agent_id}
                    if parent_agent_id is not None
                    else {}
                ),
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
            self.atomic_write(
                staging / "resource.yaml",
                self._canonical_source(agent_resource_manifest(source)),
            )
            self.atomic_write(staging / "README.md", f"# {source.name}\n")
            if extra_files:
                self._write_extra_files(staging, extra_files)
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

    def index(
        self, root_path: str | Path, *, allow_relocate: bool = False
    ) -> dict[str, Any]:
        with self._writer_lock:
            return self._index(root_path, allow_relocate=allow_relocate)

    def _index(
        self, root_path: str | Path, *, allow_relocate: bool = False
    ) -> dict[str, Any]:
        root = self._existing_root(root_path)
        manifest_path = self._require_project_manifest(root)
        ensure_project_layout(root)
        self._scan_for_forbidden_names(root)
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
            return self._index_manifest(
                root,
                manifest_path,
                manifest_text,
                manifest,
                allow_relocate=allow_relocate,
            )
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
        *,
        imported_bundle: ProjectArchive | None = None,
        allow_relocate: bool = False,
    ) -> dict[str, Any]:
        records, indexed_files = self._collect_allowed_files(
            root, manifest, manifest_path
        )
        now = _utc_now()
        root_text = self._stored_root_text(root)
        absolute_text = str(root.resolve(strict=True))
        with self.repository.transaction() as connection:
            bound_project = connection.execute(
                "SELECT * FROM projects WHERE project_id = ?", (manifest.project_id,)
            ).fetchone()
            bound_root = connection.execute(
                "SELECT * FROM projects WHERE root_path IN (?, ?)",
                (root_text, absolute_text),
            ).fetchone()
            if bound_project is not None and not self._same_stored_root(
                bound_project["root_path"], root
            ):
                current_managed = False
                try:
                    current_managed = self._is_managed_root(
                        self._existing_root(bound_project["root_path"])
                    )
                except ProjectError:
                    current_managed = False
                if not allow_relocate or current_managed:
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
                       SET root_path = ?,
                           name = ?,
                           description = ?,
                           manifest_hash = ?,
                           indexed_at = ?
                       WHERE project_id = ?""",
                    (
                        root_text,
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
                manifest_entry = next(
                    entry
                    for entry in manifest.agents
                    if entry.agent_id == source.agent_id
                )
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
                        parent_agent_id=manifest_entry.parent_agent_id,
                    )
                else:
                    self.repository.refresh_agent(
                        connection,
                        agent_id=source.agent_id,
                        slug=source.slug,
                        source_path=relative,
                        source_file_hash=current_hash,
                        indexed_at=now,
                        parent_agent_id=manifest_entry.parent_agent_id,
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
            if imported_bundle is not None:
                for snapshot in imported_bundle.agent_versions:
                    text = self._canonical_source(snapshot.source.to_dict())
                    self.repository.insert_version(
                        connection,
                        {
                            "version_id": snapshot.version_id,
                            "agent_id": snapshot.source.agent_id,
                            "source": snapshot.source.to_dict(),
                            "source_text": text,
                            "source_hash": snapshot.source.source_hash,
                            "behavior_hash": snapshot.source.behavior_hash,
                            "lock_hash": snapshot.source.lock_hash,
                            "file_hash": file_hash(text),
                            "created_at": now,
                        },
                    )
            self._index_workflows(connection, root, manifest, now)
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
            agent_record: dict[str, Any] = {
                "agent_id": source.agent_id,
                "slug": source.slug,
                "name": source.name,
                "description": source.description,
                "version": source.version,
                "pinned": source.agent_id == manifest.default_agent_id,
                "parent_agent_id": entry.parent_agent_id,
                "source_path": row["source_path"],
                "source_file_hash": file_hash(source_text),
            }
            origin = self.repository.agent_origin(source.agent_id)
            if origin is not None:
                agent_record["community_origin"] = {
                    "owner_handle": origin["owner_handle"],
                    "slug": origin["remote_slug"],
                    "version": origin["remote_version"],
                    "source_hash": origin["remote_source_hash"],
                    "imported_at": origin["imported_at"],
                }
            agents.append(agent_record)
        workflows: list[dict[str, Any]] = []
        for workflow_entry in sorted(manifest.workflows, key=lambda item: item.slug):
            row = self.repository.workflow(workflow_entry.resource_id)
            if row is None:
                raise ProjectError("Project Workflow is missing from its local index")
            source_path = self._safe_file(
                root, Path(workflow_entry.path) / "workflow.vworkflow.yaml"
            )
            source_text = self._read_text(source_path)
            workflow_source = WorkflowSource.from_dict(
                self._parse_yaml(source_text, workflow_entry.slug)
            )
            if (
                workflow_source.workflow_id != workflow_entry.resource_id
                or workflow_source.slug != workflow_entry.slug
            ):
                raise ProjectError(
                    "Project Workflow identity does not match workflow_source"
                )
            workflows.append(
                {
                    "workflow_id": workflow_source.workflow_id,
                    "slug": workflow_source.slug,
                    "name": workflow_source.name,
                    "description": workflow_source.description,
                    "version": workflow_source.version,
                    "source_path": row["source_path"],
                    "source_file_hash": file_hash(source_text),
                }
            )
        knowledge = [
            self._knowledge_listing(root, entry)
            for entry in sorted(manifest.knowledge, key=lambda item: item.slug)
        ]
        return {
            "schema_version": "1.0",
            "project_id": project["project_id"],
            "root_path": str(root),
            "name": project["name"],
            "description": project["description"],
            "pinned": project["pinned_at"] is not None,
            "pinned_at": project["pinned_at"],
            "manifest_hash": project["manifest_hash"],
            "default_agent_id": manifest.default_agent_id,
            "agents": agents,
            "agent_count": len(agents),
            "workflows": workflows,
            "workflow_count": len(workflows),
            "knowledge": knowledge,
            "knowledge_count": len(knowledge),
            "component_count": len(manifest.components),
            "asset_count": len(manifest.assets),
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
                    self._folder_name_from_display(name),
                    exclude_project_id=project_id,
                )
            if description is not None:
                updated["description"] = description
            validated = ProjectManifest.from_dict(updated)
            try:
                self.atomic_write(
                    manifest_path, self._canonical_source(validated.to_dict())
                )
                if self._is_managed_root(root):
                    root = self._align_managed_folder(project_id, validated.name, root)
                    manifest_path = root / "project.vproject.yaml"
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

    def _install_workflow(
        self,
        *,
        project_id: str,
        root: Path,
        manifest_path: Path,
        previous_manifest_text: str,
        manifest: ProjectManifest,
        source: WorkflowSource,
    ) -> dict[str, Any]:
        existing_ids = {entry.resource_id for entry in manifest.workflows}
        existing_slugs = {entry.slug for entry in manifest.workflows}
        if source.workflow_id in existing_ids or self.repository.workflow(
            source.workflow_id
        ):
            raise ProjectError("duplicate Workflow ID; use explicit Fork/import")
        if source.slug in existing_slugs:
            raise ProjectError("Project Workflow slugs must be unique")
        ensure_project_layout(root)
        workflows_root = self._safe_directory(root, Path("workflows"))
        target = workflows_root / source.slug
        if target.exists() or target.is_symlink():
            raise ProjectError("Project Workflow path already exists")
        staging = workflows_root / f".{source.slug}.veyra-staging-{new_uuid7()}"
        updated_manifest = manifest.to_dict()
        updated_manifest.setdefault("workflows", []).append(
            {
                "kind": "workflow",
                "resource_id": source.workflow_id,
                "slug": source.slug,
                "version": source.version,
                "path": f"workflows/{source.slug}",
            }
        )
        ProjectManifest.from_dict(updated_manifest)
        installed = False
        manifest_replaced = False
        try:
            staging.mkdir(mode=0o700)
            self.atomic_write(
                staging / "workflow.vworkflow.yaml",
                self._canonical_source(source.to_dict()),
            )
            self.atomic_write(
                staging / "resource.yaml",
                self._canonical_source(workflow_resource_manifest(source)),
            )
            self.atomic_write(staging / "README.md", f"# {source.name}\n")
            self._fsync_tree(staging)
            if target.exists():
                raise ProjectError("Project Workflow path already exists")
            os.replace(staging, target)
            installed = True
            self._fsync_directory(workflows_root)
            self.atomic_write(manifest_path, self._canonical_source(updated_manifest))
            manifest_replaced = True
            self.index(root)
            return self.workflow_summary(project_id, source.workflow_id)
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
                    self._fsync_directory(workflows_root)
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

    def _index_workflows(
        self,
        connection: Any,
        root: Path,
        manifest: ProjectManifest,
        now: str,
    ) -> None:
        manifest_ids = {entry.resource_id for entry in manifest.workflows}
        existing = connection.execute(
            """SELECT * FROM workflows
               WHERE project_id = ? AND removed_at IS NULL""",
            (manifest.project_id,),
        ).fetchall()
        stale = {
            row["workflow_id"]
            for row in existing
            if row["workflow_id"] not in manifest_ids
        }
        for workflow_id in stale:
            if (
                connection.execute(
                    "SELECT 1 FROM workflow_versions WHERE workflow_id = ?",
                    (workflow_id,),
                ).fetchone()
                is not None
            ):
                raise ProjectError("cannot remove a Workflow with immutable versions")
        self.repository.delete_workflows(connection, stale)
        for entry in manifest.workflows:
            source_path = self._safe_file(
                root, Path(entry.path) / "workflow.vworkflow.yaml"
            )
            source_text = self._read_text(source_path)
            source = WorkflowSource.from_dict(self._parse_yaml(source_text, entry.slug))
            if source.workflow_id != entry.resource_id or source.slug != entry.slug:
                raise ProjectError(
                    "Project manifest Workflow identity does not match source"
                )
            current_hash = file_hash(source_text)
            existing_row = connection.execute(
                "SELECT * FROM workflows WHERE workflow_id = ?",
                (source.workflow_id,),
            ).fetchone()
            relative = source_path.relative_to(root).as_posix()
            if (
                existing_row is not None
                and existing_row["project_id"] != manifest.project_id
            ):
                raise ProjectError("duplicate Workflow ID; use explicit Fork/import")
            if existing_row is None:
                self.repository.upsert_workflow(
                    connection,
                    workflow_id=source.workflow_id,
                    project_id=manifest.project_id,
                    slug=source.slug,
                    source_path=relative,
                    source_file_hash=current_hash,
                    indexed_at=now,
                )
            else:
                self.repository.refresh_workflow(
                    connection,
                    workflow_id=source.workflow_id,
                    slug=source.slug,
                    source_path=relative,
                    source_file_hash=current_hash,
                    indexed_at=now,
                )
            if self.repository.workflow_draft(source.workflow_id) is None:
                self.repository.insert_workflow_draft(
                    connection,
                    workflow_id=source.workflow_id,
                    draft_id=new_uuid7(),
                    revision=0,
                    source=source.to_dict(),
                    source_file_hash=current_hash,
                    etag=_etag(0, current_hash),
                )

    def _workflow_source(self, root: Path, entry: Any) -> WorkflowSource:
        source_path = self._safe_file(
            root, Path(entry.path) / "workflow.vworkflow.yaml"
        )
        source = WorkflowSource.from_dict(
            self._parse_yaml(self._read_text(source_path), entry.slug)
        )
        if source.workflow_id != entry.resource_id or source.slug != entry.slug:
            raise ProjectError(
                "Project manifest Workflow identity does not match source"
            )
        return source

    def remove_workflow(self, project_id: str, workflow_id: str) -> dict[str, Any]:
        """Move a Workflow source directory to application trash."""
        with self._writer_lock:
            _, root, manifest_path, previous_text, manifest = (
                self._project_manifest_state(project_id)
            )
            selected = next(
                (
                    entry
                    for entry in manifest.workflows
                    if entry.resource_id == workflow_id
                ),
                None,
            )
            if selected is None:
                raise ProjectError("unknown Workflow in Project")
            remaining = [
                entry
                for entry in manifest.workflows
                if entry.resource_id != workflow_id
            ]
            updated = manifest.to_dict()
            updated["workflows"] = [entry.to_dict() for entry in remaining]
            validated = ProjectManifest.from_dict(updated)
            source = self._safe_directory(root, Path(selected.path))
            target = self._workflow_trash_target(project_id, workflow_id)
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
                if not self.repository.remove_workflow(workflow_id, removed_at):
                    raise ProjectError("unknown Workflow in Project")
                marked = True
                project = self.index(root)
                return {
                    "schema_version": "1.0",
                    "project_id": project_id,
                    "workflow_id": workflow_id,
                    "disposition": "trashed",
                    "removed_at": removed_at,
                    "project": project,
                }
            except BaseException as exc:
                rollback_errors: list[BaseException] = []
                if marked:
                    try:
                        self.repository.restore_workflow(workflow_id)
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

    def _workflow_trash_target(self, project_id: str, workflow_id: str) -> Path:
        storage_root = self._managed_storage_root()
        trash_root = storage_root.parent / "trash" / "workflows" / project_id
        current = trash_root
        while True:
            if current.exists() and current.is_symlink():
                raise ProjectError("managed Workflow trash path must not be a symlink")
            if current == current.parent:
                break
            current = current.parent
        try:
            trash_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectError("managed Workflow trash path is unavailable") from exc
        if not trash_root.is_dir() or trash_root.is_symlink():
            raise ProjectError("managed Workflow trash path must be a directory")
        target = trash_root / workflow_id
        if target.exists() or target.is_symlink():
            raise ProjectError(
                "managed Workflow trash target already exists or is unsafe"
            )
        return target

    def workflow_summary(self, project_id: str, workflow_id: str) -> dict[str, Any]:
        project = self.repository.project(project_id)
        workflow = self.repository.workflow(workflow_id)
        if project is None:
            raise ProjectError("unknown Project")
        if workflow is None or workflow["project_id"] != project_id:
            raise ProjectError("unknown Workflow in Project")
        root = self._existing_root(project["root_path"])
        source_path = self._safe_file(root, Path(workflow["source_path"]))
        source_text = self._read_text(source_path)
        source = WorkflowSource.from_dict(
            self._parse_yaml(source_text, workflow["slug"])
        )
        if source.workflow_id != workflow_id or source.slug != workflow["slug"]:
            raise ProjectError("Project Workflow identity does not match source")
        return {
            "schema_version": "1.0",
            "project_id": project_id,
            "workflow_id": source.workflow_id,
            "slug": source.slug,
            "name": source.name,
            "description": source.description,
            "version": source.version,
            "source_path": workflow["source_path"],
            "source_file_hash": file_hash(source_text),
            "node_count": len(source.nodes),
            "transition_count": len(source.transitions),
        }

    def create_knowledge(
        self,
        *,
        project_id: str,
        name: str | None = None,
        description: str | None = None,
        text: str | None = None,
    ) -> dict[str, Any]:
        """Create a Knowledge document inside an existing Project."""
        with self._writer_lock:
            _, root, manifest_path, previous_manifest_text, manifest = (
                self._project_manifest_state(project_id)
            )
            occupied_names = {
                self._knowledge_manifest(root, entry).name
                for entry in manifest.knowledge
            }
            allocated_name = self._allocate_agent_name(
                _nonblank_optional_text(name) or "New Knowledge", occupied_names
            )
            allocated_slug = self._allocate_agent_slug(
                "new-knowledge", {entry.slug for entry in manifest.knowledge}
            )
            document = (
                text
                if isinstance(text, str) and text
                else blank_knowledge_document(allocated_name)
            )
            return self._install_knowledge(
                project_id=project_id,
                root=root,
                manifest_path=manifest_path,
                previous_manifest_text=previous_manifest_text,
                manifest=manifest,
                resource_id=new_uuid7(),
                slug=allocated_slug,
                name=allocated_name,
                description=_nonblank_optional_text(description)
                or "A Knowledge document.",
                text=document,
            )

    def _install_knowledge(
        self,
        *,
        project_id: str,
        root: Path,
        manifest_path: Path,
        previous_manifest_text: str,
        manifest: ProjectManifest,
        resource_id: str,
        slug: str,
        name: str,
        description: str,
        text: str,
    ) -> dict[str, Any]:
        existing_ids = {entry.resource_id for entry in manifest.knowledge}
        existing_slugs = {entry.slug for entry in manifest.knowledge}
        if resource_id in existing_ids:
            raise ProjectError("duplicate Knowledge ID; use explicit Fork/import")
        if slug in existing_slugs:
            raise ProjectError("Project Knowledge slugs must be unique")
        ensure_project_layout(root)
        knowledge_root = self._safe_directory(root, Path("knowledge"))
        target = knowledge_root / slug
        if target.exists() or target.is_symlink():
            raise ProjectError("Project Knowledge path already exists")
        staging = knowledge_root / f".{slug}.veyra-staging-{new_uuid7()}"
        updated_manifest = manifest.to_dict()
        updated_manifest.setdefault("knowledge", []).append(
            {
                "kind": "knowledge",
                "resource_id": resource_id,
                "slug": slug,
                "version": "1.0.0",
                "path": f"knowledge/{slug}",
            }
        )
        ProjectManifest.from_dict(updated_manifest)
        installed = False
        manifest_replaced = False
        try:
            staging.mkdir(mode=0o700)
            self.atomic_write(
                staging / "resource.yaml",
                self._canonical_source(
                    knowledge_resource_manifest(
                        resource_id=resource_id,
                        slug=slug,
                        name=name,
                        description=description,
                    )
                ),
            )
            self.atomic_write(staging / "document.md", document_text(text))
            self.atomic_write(staging / "README.md", f"# {name}\n")
            self._fsync_tree(staging)
            if target.exists():
                raise ProjectError("Project Knowledge path already exists")
            os.replace(staging, target)
            installed = True
            self._fsync_directory(knowledge_root)
            self.atomic_write(manifest_path, self._canonical_source(updated_manifest))
            manifest_replaced = True
            self.index(root)
            return self.knowledge_summary(project_id, resource_id)
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
                    self._fsync_directory(knowledge_root)
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

    def knowledge_summary(self, project_id: str, knowledge_id: str) -> dict[str, Any]:
        _, root, _, _, manifest = self._project_manifest_state(project_id)
        entry = next(
            (item for item in manifest.knowledge if item.resource_id == knowledge_id),
            None,
        )
        if entry is None:
            raise ProjectError("unknown Knowledge in Project")
        listing = self._knowledge_listing(root, entry)
        document_path = self._safe_file(root, Path(listing["source_path"]))
        return {
            **listing,
            "schema_version": "1.0",
            "project_id": project_id,
            "text": self._read_text(document_path),
        }

    def replace_knowledge(
        self,
        *,
        project_id: str,
        knowledge_id: str,
        name: str | None = None,
        description: str | None = None,
        text: str | None = None,
    ) -> dict[str, Any]:
        """Update Knowledge metadata and/or document text on disk."""
        if name is None and description is None and text is None:
            raise ProjectError("at least one Knowledge field is required")
        with self._writer_lock:
            _, root, _, _, manifest = self._project_manifest_state(project_id)
            entry = next(
                (
                    item
                    for item in manifest.knowledge
                    if item.resource_id == knowledge_id
                ),
                None,
            )
            if entry is None:
                raise ProjectError("unknown Knowledge in Project")
            current = self._knowledge_manifest(root, entry)
            next_name = _nonblank_optional_text(name) or current.name
            next_description = (
                _nonblank_optional_text(description) or current.description
            )
            document_path = self._safe_file(root, Path(entry.path) / "document.md")
            resource_path = self._safe_file(root, Path(entry.path) / "resource.yaml")
            next_text = (
                document_text(text)
                if isinstance(text, str)
                else self._read_text(document_path)
            )
            occupied = {
                self._knowledge_manifest(root, item).name
                for item in manifest.knowledge
                if item.resource_id != knowledge_id
            }
            if _name_key(next_name) in {_name_key(value) for value in occupied}:
                raise ProjectError("Project Knowledge names must be unique")
            self.atomic_write(
                resource_path,
                self._canonical_source(
                    knowledge_resource_manifest(
                        resource_id=current.resource_id,
                        slug=current.slug,
                        name=next_name,
                        description=next_description,
                        version=current.version,
                    )
                ),
            )
            self.atomic_write(document_path, next_text)
            self.index(root)
            return self.knowledge_summary(project_id, knowledge_id)

    def remove_knowledge(self, project_id: str, knowledge_id: str) -> dict[str, Any]:
        """Move a Knowledge directory to application trash."""
        with self._writer_lock:
            _, root, manifest_path, previous_text, manifest = (
                self._project_manifest_state(project_id)
            )
            selected = next(
                (
                    entry
                    for entry in manifest.knowledge
                    if entry.resource_id == knowledge_id
                ),
                None,
            )
            if selected is None:
                raise ProjectError("unknown Knowledge in Project")
            remaining = [
                entry
                for entry in manifest.knowledge
                if entry.resource_id != knowledge_id
            ]
            updated = manifest.to_dict()
            updated["knowledge"] = [entry.to_dict() for entry in remaining]
            validated = ProjectManifest.from_dict(updated)
            source = self._safe_directory(root, Path(selected.path))
            target = self._knowledge_trash_target(project_id, knowledge_id)
            removed_at = _utc_now()
            moved = False
            try:
                os.replace(source, target)
                moved = True
                self._fsync_directory(source.parent)
                self._fsync_directory(target.parent)
                self.atomic_write(
                    manifest_path, self._canonical_source(validated.to_dict())
                )
                project = self.index(root)
                return {
                    "schema_version": "1.0",
                    "project_id": project_id,
                    "knowledge_id": knowledge_id,
                    "disposition": "trashed",
                    "removed_at": removed_at,
                    "project": project,
                }
            except BaseException as exc:
                rollback_errors: list[BaseException] = []
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

    def _knowledge_listing(self, root: Path, entry: Any) -> dict[str, Any]:
        resource = self._knowledge_manifest(root, entry)
        if resource.resource_id != entry.resource_id or resource.slug != entry.slug:
            raise ProjectError("Project Knowledge identity does not match source")
        document_path = self._safe_file(root, Path(entry.path) / "document.md")
        document_text_value = self._read_text(document_path)
        return {
            "knowledge_id": resource.resource_id,
            "slug": resource.slug,
            "name": resource.name,
            "description": resource.description,
            "version": resource.version,
            "source_path": document_path.relative_to(root).as_posix(),
            "source_file_hash": file_hash(document_text_value),
        }

    def _knowledge_manifest(self, root: Path, entry: Any) -> ResourceManifest:
        resource_path = self._safe_file(root, Path(entry.path) / "resource.yaml")
        return ResourceManifest.from_dict(
            self._parse_yaml(self._read_text(resource_path), entry.slug)
        )

    def _knowledge_trash_target(self, project_id: str, knowledge_id: str) -> Path:
        storage_root = self._managed_storage_root()
        trash_root = storage_root.parent / "trash" / "knowledge" / project_id
        current = trash_root
        while True:
            if current.exists() and current.is_symlink():
                raise ProjectError("managed Knowledge trash path must not be a symlink")
            if current == current.parent:
                break
            current = current.parent
        try:
            trash_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectError("managed Knowledge trash path is unavailable") from exc
        if not trash_root.is_dir() or trash_root.is_symlink():
            raise ProjectError("managed Knowledge trash path must be a directory")
        target = trash_root / knowledge_id
        if target.exists() or target.is_symlink():
            raise ProjectError(
                "managed Knowledge trash target already exists or is unsafe"
            )
        return target

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
        result = {
            "schema_version": "1.0",
            "project_id": project_id,
            "agent_id": source.agent_id,
            "slug": source.slug,
            "name": source.name,
            "description": source.description,
            "parent_agent_id": agent["parent_agent_id"],
            "source_path": agent["source_path"],
            "source_file_hash": file_hash(source_text),
            "node_count": len(source.nodes),
            "transition_count": len(source.transitions),
            "component_types": sorted(
                {node.component_type.value for node in source.nodes}
            ),
        }
        origin = self.repository.agent_origin(agent_id)
        if origin is not None:
            result["community_origin"] = {
                "owner_handle": origin["owner_handle"],
                "slug": origin["remote_slug"],
                "version": origin["remote_version"],
                "source_hash": origin["remote_source_hash"],
                "imported_at": origin["imported_at"],
            }
        return result

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
        ensure_project_layout(root)
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
            resource_path = self._agent_resource_file(root, entry.path, source)
            records.append((source, source_path, source_text))
            files.extend([source_path, readme_path, resource_path])
            files.extend(self._files_below(test_dir))
            if agent_dir.is_symlink():
                raise ProjectError("Project path or symlink escapes its root")
        for relative in INDEXED_ROOT_DIRECTORIES:
            files.extend(self._files_below(self._safe_directory(root, relative)))
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

    def _agent_resource_file(
        self, root: Path, entry_path: str, source: AgentSource
    ) -> Path:
        relative = Path(resource_yaml_path(entry_path))
        expected = agent_resource_manifest(source)
        candidate = root / relative
        if candidate.is_file():
            current = ResourceManifest.from_dict(
                self._parse_yaml(self._read_text(candidate), "resource manifest")
            )
            if (
                current.kind is not ResourceKind.AGENT
                or current.resource_id != source.agent_id
                or current.slug != source.slug
            ):
                raise ProjectError("Agent resource.yaml identity does not match source")
            return self._safe_file(root, relative)
        self.atomic_write(candidate, self._canonical_source(expected))
        return self._safe_file(root, relative)

    def _write_extra_files(self, staging: Path, extra_files: dict[str, bytes]) -> None:
        staging_resolved = staging.resolve()
        for relative, payload in extra_files.items():
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ProjectError("Project relative path escapes its root")
            if path.name in {"agent.vagent.yaml", "project.vproject.yaml"}:
                raise ProjectError("Project archive contains a disallowed path")
            if path.name == "resource.yaml" and path.parts[:1] == ("agents",):
                raise ProjectError("Project archive contains a disallowed path")
            current = staging
            for part in path.parts[:-1]:
                current = current / part
                if current.exists() and (current.is_symlink() or not current.is_dir()):
                    raise ProjectError("Project path or symlink escapes its root")
                if not current.exists():
                    current.mkdir(mode=0o700)
            target = staging / path
            if target.exists() and (target.is_symlink() or not target.is_file()):
                raise ProjectError("Project files may not be symlinks")
            if not target.parent.resolve().is_relative_to(staging_resolved):
                raise ProjectError("Project path or symlink escapes its root")
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ProjectError("Project source must be UTF-8") from exc
            self.atomic_write(target, text)

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

    def _existing_root(self, value: str | Path) -> Path:
        raw = Path(value)
        if not raw.is_absolute():
            if len(raw.parts) != 1 or raw.name in {".", ".."} or ".." in raw.parts:
                raise ProjectError("selected Project directory is absent or a symlink")
            raw = self._managed_storage_root() / raw
        root = raw.expanduser().absolute()
        if not root.is_dir() or root.is_symlink():
            raise ProjectError("selected Project directory is absent or a symlink")
        return root.resolve(strict=True)

    def _require_project_manifest(self, root: Path) -> Path:
        """Reject ordinary folders before mutating them to look like a Project."""
        relative = Path("project.vproject.yaml")
        if not (root / relative).exists():
            raise ProjectError(
                "selected folder is not a Veyra Project",
                "not_a_project",
            )
        return self._safe_file(root, relative)

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
        name: str,
        description: str,
        sources: list[AgentSource],
        parents: dict[str, str] | None = None,
        default_agent_id: str | None = None,
    ) -> dict[str, Any]:
        parent_map = parents or {}
        agents: list[dict[str, Any]] = []
        for source in sources:
            entry: dict[str, Any] = {
                "agent_id": source.agent_id,
                "slug": source.slug,
                "path": f"agents/{source.slug}",
                "version": source.version,
            }
            parent_id = parent_map.get(source.agent_id)
            if parent_id is not None:
                entry["parent_agent_id"] = parent_id
            agents.append(entry)
        if default_agent_id is None:
            resolved_default = sources[0].agent_id if sources else None
        else:
            resolved_default = default_agent_id
        manifest = {
            "schema_version": "1.0",
            "project_version": "1",
            "project_id": new_uuid7(),
            "name": name,
            "description": description,
            "agents": agents,
            "default_agent_id": resolved_default,
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


def document_text(value: str) -> str:
    if not isinstance(value, str):
        raise ProjectError("Knowledge document must be a string")
    return value


def _etag(revision: int, current_file_hash: str) -> str:
    return (
        '"'
        + sha256_digest({"revision": revision, "file_hash": current_file_hash})
        + '"'
    )


def _package_error(exc: ProjectPackageError) -> ProjectError:
    return ProjectError(str(exc), exc.code)


def _archive_filename(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip())[:80].strip(".-")
    return f"{slug or 'project'}.vproject.zip"


def _file_kind(relative: str, manifest: ProjectManifest) -> tuple[str, str | None]:
    if relative == "project.vproject.yaml":
        return "manifest", None
    for entry in manifest.agents:
        if relative == f"{entry.path}/agent.vagent.yaml":
            return "agent_source", entry.agent_id
        if relative == resource_yaml_path(entry.path):
            return "resource_manifest", entry.agent_id
        if relative == f"{entry.path}/README.md":
            return "readme", entry.agent_id
        if relative.startswith(f"{entry.path}/tests/"):
            return "test", entry.agent_id
    for owned_entry in manifest.workflows:
        if relative.startswith(f"{owned_entry.path}/"):
            return "workflow", owned_entry.resource_id
    for owned_entry in manifest.components:
        if relative.startswith(f"{owned_entry.path}/"):
            return "component", owned_entry.resource_id
    for owned_entry in manifest.knowledge:
        if relative.startswith(f"{owned_entry.path}/"):
            return "knowledge", owned_entry.resource_id
    for owned_entry in manifest.assets:
        if relative.startswith(f"{owned_entry.path}/"):
            return "asset", owned_entry.resource_id
    if relative.startswith("knowledge/"):
        return "knowledge", None
    if relative.startswith("assets/"):
        return "asset", None
    if relative.startswith("resources/"):
        return "resource", None
    if relative.startswith("tests/"):
        return "project_test", None
    return "file", None
