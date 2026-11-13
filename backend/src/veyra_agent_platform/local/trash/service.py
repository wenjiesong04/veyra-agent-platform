"""Recoverable trash for Projects, Agents, Workflows, Knowledge, chats, and plugins."""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from veyra_agent_platform.contracts.agent import AgentSource, ProjectManifest
from veyra_agent_platform.contracts.common import (
    SCHEMA_VERSION,
    ContractValidationError,
)
from veyra_agent_platform.contracts.resource import ResourceManifest
from veyra_agent_platform.contracts.workflow import WorkflowSource
from veyra_agent_platform.local.builder.conversation_service import (
    BuilderConversationService,
)
from veyra_agent_platform.local.plugins.service import PluginService
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.storage.durability import fsync_directory

TRASH_RETENTION_DAYS = 30
TRASH_KINDS = (
    "project",
    "agent",
    "workflow",
    "knowledge",
    "conversation",
    "plugin",
)
TrashKind = Literal[
    "project", "agent", "workflow", "knowledge", "conversation", "plugin"
]


class TrashService:
    """Compose existing trash folders and conversation/plugin restore paths."""

    def __init__(
        self,
        projects: ProjectService,
        plugins: PluginService,
        conversations: BuilderConversationService,
    ) -> None:
        self.projects = projects
        self.plugins = plugins
        self.conversations = conversations

    def list_items(self) -> dict[str, Any]:
        items = [
            *self._project_items(),
            *self._agent_items(),
            *self._workflow_items(),
            *self._knowledge_items(),
            *self._conversation_items(),
            *self._plugin_items(),
        ]
        items.sort(key=lambda item: (item["removed_at"], item["id"]), reverse=True)
        return {
            "schema_version": SCHEMA_VERSION,
            "retention_days": TRASH_RETENTION_DAYS,
            "items": items,
        }

    def restore(self, kind: str, item_id: str, *, confirm: bool) -> dict[str, Any]:
        self._require_confirm(confirm, "restore")
        normalized = self._kind(kind)
        if normalized == "conversation":
            self.conversations.restore_trashed(item_id)
        elif normalized == "plugin":
            self.plugins.restore(item_id, confirm=True)
        elif normalized == "project":
            self._restore_project(item_id)
        elif normalized == "agent":
            self._restore_agent(item_id)
        elif normalized == "workflow":
            self._restore_workflow(item_id)
        else:
            self._restore_knowledge(item_id)
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": normalized,
            "id": item_id,
            "restored": True,
        }

    def purge(self, kind: str, item_id: str, *, confirm: bool) -> dict[str, Any]:
        self._require_confirm(confirm, "permanently delete")
        normalized = self._kind(kind)
        if normalized == "conversation":
            self.conversations.purge_trashed(item_id)
        elif normalized == "plugin":
            self.plugins.purge(item_id, confirm=True)
        elif normalized == "project":
            self._purge_directory(self._project_trash_path(item_id), "Project")
        elif normalized == "agent":
            self._purge_agent(item_id)
        elif normalized == "workflow":
            self._purge_workflow(item_id)
        else:
            self._purge_knowledge(item_id)
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": normalized,
            "id": item_id,
            "deleted": True,
        }

    def _project_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in self.projects.repository.trashed_projects():
            target = self._project_trash_path(row["project_id"])
            if not target.is_dir():
                continue
            items.append(
                self._item(
                    kind="project",
                    item_id=row["project_id"],
                    name=str(row["name"]),
                    removed_at=str(row["removed_at"]),
                    restorable=True,
                )
            )
        return items

    def _agent_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in self.projects.repository.trashed_agents():
            target = self._agent_trash_path(row["project_id"], row["agent_id"])
            if not target.is_dir():
                continue
            project = self.projects.repository.project_row(row["project_id"])
            active = self.projects.repository.project(row["project_id"]) is not None
            items.append(
                self._item(
                    kind="agent",
                    item_id=row["agent_id"],
                    name=self._source_name(
                        target / "agent.vagent.yaml", AgentSource, row["slug"]
                    ),
                    removed_at=str(row["removed_at"]),
                    project_id=row["project_id"],
                    project_name=None if project is None else str(project["name"]),
                    restorable=active,
                )
            )
        return items

    def _workflow_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in self.projects.repository.trashed_workflows():
            target = self._workflow_trash_path(row["project_id"], row["workflow_id"])
            if not target.is_dir():
                continue
            project = self.projects.repository.project_row(row["project_id"])
            active = self.projects.repository.project(row["project_id"]) is not None
            items.append(
                self._item(
                    kind="workflow",
                    item_id=row["workflow_id"],
                    name=self._source_name(
                        target / "workflow.vworkflow.yaml", WorkflowSource, row["slug"]
                    ),
                    removed_at=str(row["removed_at"]),
                    project_id=row["project_id"],
                    project_name=None if project is None else str(project["name"]),
                    restorable=active,
                )
            )
        return items

    def _knowledge_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        knowledge_root = self._trash_root() / "knowledge"
        if not knowledge_root.is_dir():
            return items
        for project_dir in sorted(knowledge_root.iterdir()):
            if project_dir.name.startswith(".") or not project_dir.is_dir():
                continue
            project = self.projects.repository.project_row(project_dir.name)
            active = self.projects.repository.project(project_dir.name) is not None
            for target in sorted(project_dir.iterdir()):
                if target.name.startswith(".") or not target.is_dir():
                    continue
                resource = self._knowledge_manifest(target)
                name = target.name if resource is None else resource.name
                items.append(
                    self._item(
                        kind="knowledge",
                        item_id=target.name,
                        name=name,
                        removed_at=self._mtime(target),
                        project_id=project_dir.name,
                        project_name=None if project is None else str(project["name"]),
                        restorable=active and resource is not None,
                    )
                )
        return items

    def _conversation_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in self.conversations.list_trashed():
            items.append(
                self._item(
                    kind="conversation",
                    item_id=row["id"],
                    name=row["name"],
                    removed_at=row["removed_at"],
                    project_id=row["project_id"],
                    project_name=row["project_name"],
                    restorable=(
                        row.get("project_removed_at") is None
                        and self.projects.repository.project(str(row["project_id"]))
                        is not None
                    ),
                )
            )
        return items

    def _plugin_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        listed = self.plugins.list_trash().get("plugins", [])
        trash_root = self.plugins.root / ".trash"
        for pack in listed:
            trash_id = str(pack["trash_id"])
            target = trash_root / trash_id
            items.append(
                self._item(
                    kind="plugin",
                    item_id=trash_id,
                    name=str(pack.get("name") or pack.get("plugin_id") or trash_id),
                    removed_at=self._mtime(target) if target.exists() else _utc_now(),
                    restorable=True,
                )
            )
        return items

    def _restore_project(self, project_id: str) -> None:
        with self.projects._writer_lock:
            row = self.projects.repository.project_row(project_id)
            if row is None or row["removed_at"] is None:
                raise ProjectError("unknown Project in trash", "trash_not_found")
            source = self._require_dir(self._project_trash_path(project_id), "Project")
            destination = self._stored_project_path(str(row["root_path"]))
            if destination.exists() or destination.is_symlink():
                raise ProjectError(
                    "Project restore destination already exists", "trash_conflict"
                )
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.replace(source, destination)
            fsync_directory(destination.parent)
            trash_parent = source.parent
            if trash_parent.is_dir():
                fsync_directory(trash_parent)
            if not self.projects.repository.restore_project(project_id):
                raise ProjectError("unknown Project in trash", "trash_not_found")
            self.projects.index(destination)

    def _restore_agent(self, agent_id: str) -> None:
        with self.projects._writer_lock:
            row = next(
                (
                    item
                    for item in self.projects.repository.trashed_agents()
                    if item["agent_id"] == agent_id
                ),
                None,
            )
            if row is None:
                raise ProjectError("unknown Agent in trash", "trash_not_found")
            _, root, manifest_path, previous_text, manifest = (
                self.projects._project_manifest_state(row["project_id"])
            )
            if any(entry.agent_id == agent_id for entry in manifest.agents):
                raise ProjectError(
                    "Agent already exists in the Project", "trash_conflict"
                )
            source = self._require_dir(
                self._agent_trash_path(row["project_id"], agent_id), "Agent"
            )
            destination = root / Path(row["source_path"]).parent
            if destination.exists() or destination.is_symlink():
                raise ProjectError(
                    "Agent restore destination already exists", "trash_conflict"
                )
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.replace(source, destination)
            fsync_directory(destination.parent)
            updated = manifest.to_dict()
            entry = {
                "agent_id": agent_id,
                "slug": row["slug"],
                "path": f"agents/{row['slug']}",
            }
            if row["parent_agent_id"]:
                entry["parent_agent_id"] = row["parent_agent_id"]
            updated["agents"] = [item.to_dict() for item in manifest.agents] + [entry]
            if updated.get("default_agent_id") is None:
                updated["default_agent_id"] = agent_id
            validated = ProjectManifest.from_dict(updated)
            try:
                self.projects.atomic_write(
                    manifest_path, self.projects._canonical_source(validated.to_dict())
                )
                if not self.projects.repository.restore_agent(agent_id):
                    raise ProjectError("unknown Agent in trash", "trash_not_found")
                self.projects.index(root)
            except BaseException:
                self.projects.atomic_write(manifest_path, previous_text)
                if destination.exists() and not source.exists():
                    os.replace(destination, source)
                raise

    def _restore_workflow(self, workflow_id: str) -> None:
        with self.projects._writer_lock:
            row = next(
                (
                    item
                    for item in self.projects.repository.trashed_workflows()
                    if item["workflow_id"] == workflow_id
                ),
                None,
            )
            if row is None:
                raise ProjectError("unknown Workflow in trash", "trash_not_found")
            _, root, manifest_path, previous_text, manifest = (
                self.projects._project_manifest_state(row["project_id"])
            )
            if any(entry.resource_id == workflow_id for entry in manifest.workflows):
                raise ProjectError(
                    "Workflow already exists in the Project", "trash_conflict"
                )
            source = self._require_dir(
                self._workflow_trash_path(row["project_id"], workflow_id), "Workflow"
            )
            destination = root / Path(row["source_path"]).parent
            if destination.exists() or destination.is_symlink():
                raise ProjectError(
                    "Workflow restore destination already exists", "trash_conflict"
                )
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.replace(source, destination)
            fsync_directory(destination.parent)
            source_file = destination / "workflow.vworkflow.yaml"
            workflow = WorkflowSource.from_dict(
                self.projects._parse_yaml(
                    self.projects._read_text(source_file), row["slug"]
                )
            )
            updated = manifest.to_dict()
            updated["workflows"] = [item.to_dict() for item in manifest.workflows] + [
                {
                    "kind": "workflow",
                    "resource_id": workflow.workflow_id,
                    "slug": workflow.slug,
                    "version": workflow.version,
                    "path": f"workflows/{workflow.slug}",
                }
            ]
            validated = ProjectManifest.from_dict(updated)
            try:
                self.projects.atomic_write(
                    manifest_path, self.projects._canonical_source(validated.to_dict())
                )
                if not self.projects.repository.restore_workflow(workflow_id):
                    raise ProjectError("unknown Workflow in trash", "trash_not_found")
                self.projects.index(root)
            except BaseException:
                self.projects.atomic_write(manifest_path, previous_text)
                if destination.exists() and not source.exists():
                    os.replace(destination, source)
                raise

    def _restore_knowledge(self, knowledge_id: str) -> None:
        with self.projects._writer_lock:
            target = self._find_knowledge_trash(knowledge_id)
            resource = self._knowledge_manifest(target)
            if resource is None:
                raise ProjectError("unknown Knowledge in trash", "trash_not_found")
            project_id = target.parent.name
            _, root, manifest_path, previous_text, manifest = (
                self.projects._project_manifest_state(project_id)
            )
            if any(entry.resource_id == knowledge_id for entry in manifest.knowledge):
                raise ProjectError(
                    "Knowledge already exists in the Project", "trash_conflict"
                )
            destination = root / "knowledge" / resource.slug
            if destination.exists() or destination.is_symlink():
                raise ProjectError(
                    "Knowledge restore destination already exists", "trash_conflict"
                )
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.replace(target, destination)
            fsync_directory(destination.parent)
            updated = manifest.to_dict()
            updated["knowledge"] = [item.to_dict() for item in manifest.knowledge] + [
                {
                    "kind": "knowledge",
                    "resource_id": resource.resource_id,
                    "slug": resource.slug,
                    "version": resource.version,
                    "path": f"knowledge/{resource.slug}",
                }
            ]
            validated = ProjectManifest.from_dict(updated)
            try:
                self.projects.atomic_write(
                    manifest_path, self.projects._canonical_source(validated.to_dict())
                )
                self.projects.index(root)
            except BaseException:
                self.projects.atomic_write(manifest_path, previous_text)
                if destination.exists() and not target.exists():
                    os.replace(destination, target)
                raise

    def _purge_agent(self, agent_id: str) -> None:
        row = next(
            (
                item
                for item in self.projects.repository.trashed_agents()
                if item["agent_id"] == agent_id
            ),
            None,
        )
        if row is None:
            raise ProjectError("unknown Agent in trash", "trash_not_found")
        self._purge_directory(
            self._agent_trash_path(row["project_id"], agent_id), "Agent"
        )

    def _purge_workflow(self, workflow_id: str) -> None:
        row = next(
            (
                item
                for item in self.projects.repository.trashed_workflows()
                if item["workflow_id"] == workflow_id
            ),
            None,
        )
        if row is None:
            raise ProjectError("unknown Workflow in trash", "trash_not_found")
        self._purge_directory(
            self._workflow_trash_path(row["project_id"], workflow_id), "Workflow"
        )

    def _purge_knowledge(self, knowledge_id: str) -> None:
        self._purge_directory(self._find_knowledge_trash(knowledge_id), "Knowledge")

    def _purge_directory(self, target: Path, label: str) -> None:
        source = self._require_dir(target, label)
        shutil.rmtree(source)

    def _find_knowledge_trash(self, knowledge_id: str) -> Path:
        knowledge_root = self._trash_root() / "knowledge"
        if knowledge_root.is_dir():
            for project_dir in knowledge_root.iterdir():
                candidate = project_dir / knowledge_id
                if candidate.is_dir() and not candidate.is_symlink():
                    return candidate
        raise ProjectError("unknown Knowledge in trash", "trash_not_found")

    def _stored_project_path(self, stored: str) -> Path:
        raw = Path(stored)
        if not raw.is_absolute():
            if len(raw.parts) != 1 or raw.name in {".", ".."} or ".." in raw.parts:
                raise ProjectError("unknown Project in trash", "trash_not_found")
            return self.projects._managed_storage_root() / raw.name
        return raw.expanduser().absolute()

    def _project_trash_path(self, project_id: str) -> Path:
        return self._trash_root() / "projects" / project_id

    def _agent_trash_path(self, project_id: str, agent_id: str) -> Path:
        return self._trash_root() / "agents" / project_id / agent_id

    def _workflow_trash_path(self, project_id: str, workflow_id: str) -> Path:
        return self._trash_root() / "workflows" / project_id / workflow_id

    def _trash_root(self) -> Path:
        storage_root = Path(self.projects.project_storage_root).expanduser().absolute()
        return storage_root.parent / "trash"

    def _require_dir(self, target: Path, label: str) -> Path:
        if target.is_symlink() or not target.is_dir():
            raise ProjectError(f"unknown {label} in trash", "trash_not_found")
        trash_root = self._trash_root().resolve()
        try:
            resolved = target.resolve(strict=True)
        except OSError as exc:
            raise ProjectError(f"unknown {label} in trash", "trash_not_found") from exc
        if trash_root not in resolved.parents and resolved != trash_root:
            raise ProjectError(f"unknown {label} in trash", "trash_not_found")
        return target

    def _knowledge_manifest(self, target: Path) -> ResourceManifest | None:
        path = target / "resource.yaml"
        if not path.is_file() or path.is_symlink():
            return None
        try:
            return ResourceManifest.from_dict(
                self.projects._parse_yaml(self.projects._read_text(path), "knowledge")
            )
        except (ProjectError, ContractValidationError):
            return None

    def _source_name(
        self,
        path: Path,
        loader: type[AgentSource] | type[WorkflowSource],
        fallback: str,
    ) -> str:
        if not path.is_file() or path.is_symlink():
            return fallback
        try:
            parsed = loader.from_dict(
                self.projects._parse_yaml(self.projects._read_text(path), fallback)
            )
        except (ProjectError, ContractValidationError, TypeError, ValueError):
            return fallback
        name = getattr(parsed, "name", None)
        return str(name) if name else fallback

    @staticmethod
    def _item(
        *,
        kind: TrashKind,
        item_id: str,
        name: str,
        removed_at: str,
        restorable: bool,
        project_id: str | None = None,
        project_name: str | None = None,
    ) -> dict[str, Any]:
        return {
            "kind": kind,
            "id": item_id,
            "name": name,
            "project_id": project_id,
            "project_name": project_name,
            "removed_at": removed_at,
            "expires_at": _expires_at(removed_at),
            "restorable": restorable,
        }

    @staticmethod
    def _mtime(path: Path) -> str:
        try:
            return (
                datetime.fromtimestamp(path.stat().st_mtime, UTC)
                .isoformat()
                .replace("+00:00", "Z")
            )
        except OSError:
            return _utc_now()

    @staticmethod
    def _kind(kind: str) -> TrashKind:
        if kind not in TRASH_KINDS:
            raise ProjectError("unknown trash kind", "trash_not_found")
        return kind  # type: ignore[return-value]

    @staticmethod
    def _require_confirm(confirm: bool, action: str) -> None:
        if not confirm:
            raise ProjectError(
                f"Explicit confirmation is required to {action} a trash item",
                "trash_confirmation_required",
            )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _expires_at(removed_at: str) -> str:
    try:
        moment = datetime.fromisoformat(removed_at.replace("Z", "+00:00"))
    except ValueError:
        moment = datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return (
        (moment + timedelta(days=TRASH_RETENTION_DAYS))
        .isoformat()
        .replace("+00:00", "Z")
    )
