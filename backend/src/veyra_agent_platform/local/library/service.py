"""Draft editing, recovery, and immutable Agent-version lifecycle."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any, Concatenate, ParamSpec, TypeVar

from veyra_agent_platform.contracts.agent import AgentSource, ComponentType
from veyra_agent_platform.contracts.canonical import file_hash, sha256_digest
from veyra_agent_platform.contracts.common import (
    SCHEMA_VERSION,
    ContractValidationError,
    IdempotencyKey,
    new_uuid7,
)
from veyra_agent_platform.contracts.resource import ResourceRef
from veyra_agent_platform.contracts.workflow import WorkflowSource
from veyra_agent_platform.local.projects.custom_components import (
    CustomComponentError,
    CustomComponentService,
)
from veyra_agent_platform.local.projects.service import (
    ProjectError,
    ProjectService,
    _etag,
    _utc_now,
)
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.storage.repositories import LocalRepository

from .dependencies import inspect_agent_dependencies
from .workflow_dependencies import resolve_workflow_calls


class DraftConflict(ProjectError):
    """The source on disk changed or a second Studio window won the edit."""


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _serialized(
    operation: Callable[Concatenate[LibraryService, _P], _R],
) -> Callable[Concatenate[LibraryService, _P], _R]:
    @wraps(operation)
    def guarded(self: LibraryService, /, *args: _P.args, **kwargs: _P.kwargs) -> _R:
        # Cover both file replacement and its SQLite commit, including other editors.
        with self.projects._writer_lock:
            return operation(self, *args, **kwargs)

    return guarded


class LibraryService:
    def __init__(
        self,
        repository: LocalRepository,
        projects: ProjectService,
        catalog: ResourceCatalog | None = None,
        custom_components: CustomComponentService | None = None,
    ) -> None:
        self.repository = repository
        self.projects = projects
        self.catalog = catalog
        self.custom_components = custom_components
        self.recover_pending_writes()

    def recover_pending_writes(self) -> None:
        """Roll back an interrupted file write before serving its stale database row."""
        for intent in self.repository.write_intents():
            agent = self.repository.agent(intent["agent_id"])
            if agent is not None:
                project = self.repository.project(agent["project_id"])
                if project is not None:
                    root = self.projects._existing_root(project["root_path"])
                    path = self.projects._safe_file(root, Path(agent["source_path"]))
                    if self.projects._read_text(path) == intent["intended_source_text"]:
                        self.projects.atomic_write(path, intent["previous_source_text"])
            with self.repository.transaction() as connection:
                self.repository.remove_write_intent(connection, intent["intent_id"])
        for intent in self.repository.workflow_write_intents():
            workflow = self.repository.workflow(intent["workflow_id"])
            if workflow is not None:
                project = self.repository.project(workflow["project_id"])
                if project is not None:
                    root = self.projects._existing_root(project["root_path"])
                    path = self.projects._safe_file(root, Path(workflow["source_path"]))
                    if self.projects._read_text(path) == intent["intended_source_text"]:
                        self.projects.atomic_write(path, intent["previous_source_text"])
            with self.repository.transaction() as connection:
                self.repository.remove_workflow_write_intent(
                    connection, intent["intent_id"]
                )

    @_serialized
    def draft(self, project_id: str, agent_id: str) -> dict[str, Any]:
        self._agent_in_project(project_id, agent_id)
        draft = self.repository.draft(agent_id)
        if draft is None:
            raise ProjectError("Agent has not been indexed")
        self._ensure_disk_matches_draft(project_id, agent_id, draft["source_file_hash"])
        return self._draft_payload(draft)

    @_serialized
    def reload_from_disk(self, project_id: str, agent_id: str) -> dict[str, Any]:
        """Explicitly accept an external source edit as the next mutable draft."""
        agent = self._agent_in_project(project_id, agent_id)
        source_path = self._source_path(project_id, agent)
        source_text = self.projects._read_text(source_path)
        source = AgentSource.from_dict(
            self.projects._parse_yaml(source_text, agent["slug"])
        )
        if source.agent_id != agent_id or source.slug != agent["slug"]:
            raise ProjectError("disk source identity must match its Project Agent")
        digest = file_hash(source_text)
        with self.repository.transaction() as connection:
            draft = connection.execute(
                "SELECT * FROM agent_drafts WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            if draft is None:
                raise ProjectError("Agent has not been indexed")
            revision = draft["revision"] + 1
            etag = _etag(revision, digest)
            connection.execute(
                """UPDATE agent_drafts SET revision = ?, source_json = ?,
                   source_file_hash = ?, etag = ? WHERE agent_id = ?""",
                (
                    revision,
                    json.dumps(source.to_dict(), sort_keys=True, separators=(",", ":")),
                    digest,
                    etag,
                    agent_id,
                ),
            )
            connection.execute(
                "UPDATE agents SET source_file_hash = ? WHERE agent_id = ?",
                (digest, agent_id),
            )
            self.projects._index_file(
                connection,
                project_id,
                self._project_root(project_id),
                source_path,
                source_text.encode("utf-8"),
                _utc_now(),
            )
        return self.draft(project_id, agent_id)

    @_serialized
    def replace_draft(
        self,
        *,
        project_id: str,
        agent_id: str,
        source: dict[str, Any],
        expected_revision: int,
        expected_etag: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        IdempotencyKey(SCHEMA_VERSION, idempotency_key)
        parsed = AgentSource.from_dict(source)
        agent = self._agent_in_project(project_id, agent_id)
        if parsed.agent_id != agent_id or parsed.slug != agent["slug"]:
            raise ProjectError("draft source identity must match its Project Agent")
        if isinstance(expected_revision, bool) or not isinstance(
            expected_revision, int
        ):
            raise ProjectError("expected_revision must be an integer")
        scope = f"draft:{project_id}:{agent_id}"
        request_digest = sha256_digest(
            {
                "source": parsed.to_dict(),
                "revision": expected_revision,
                "etag": expected_etag,
            }
        )
        source_path = self._source_path(project_id, agent)
        previous_text = self.projects._read_text(source_path)
        current_disk_hash = file_hash(previous_text)
        canonical_text = self.projects._canonical_source(parsed.to_dict())
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, request_digest
            )
            if replay is not None:
                return replay
            draft = connection.execute(
                "SELECT * FROM agent_drafts WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            if draft is None:
                raise ProjectError("Agent has not been indexed")
            if draft["source_file_hash"] != current_disk_hash:
                raise DraftConflict("source changed outside Studio; reload it")
            if expected_etag != draft["etag"]:
                raise DraftConflict("draft ETag does not match")
            if draft["revision"] != expected_revision:
                raise DraftConflict("draft revision does not match")
            self._validate_resource_bindings(project_id, parsed)
            self._validate_knowledge_ownership(project_id, parsed)
            intent_id = self.repository.create_write_intent(
                connection,
                agent_id=agent_id,
                previous_source_text=previous_text,
                intended_source_text=canonical_text,
            )
        try:
            self.projects.atomic_write(source_path, canonical_text)
            updated_hash = file_hash(canonical_text)
            next_revision = expected_revision + 1
            etag = _etag(next_revision, updated_hash)
            result = {
                "schema_version": SCHEMA_VERSION,
                "revision": next_revision,
                "etag": etag,
                "source": parsed.to_dict(),
            }
            with self.repository.transaction() as connection:
                if not self.repository.update_draft(
                    connection,
                    agent_id=agent_id,
                    expected_revision=expected_revision,
                    source=parsed.to_dict(),
                    source_file_hash=updated_hash,
                    etag=etag,
                ):
                    raise DraftConflict("draft changed concurrently")
                connection.execute(
                    "UPDATE agents SET source_file_hash = ? WHERE agent_id = ?",
                    (updated_hash, agent_id),
                )
                self.projects._index_file(
                    connection,
                    project_id,
                    self._project_root(project_id),
                    source_path,
                    canonical_text.encode("utf-8"),
                    _utc_now(),
                )
                self.repository.remember_response(
                    connection, scope, idempotency_key, request_digest, result
                )
                self.repository.remove_write_intent(connection, intent_id)
            return result
        except BaseException:
            self.projects.atomic_write(source_path, previous_text)
            with self.repository.transaction() as connection:
                self.repository.remove_write_intent(connection, intent_id)
            raise

    def _validate_knowledge_ownership(
        self, project_id: str, source: AgentSource
    ) -> None:
        if not source.knowledge_refs:
            return
        _, _, _, _, manifest = self.projects._project_manifest_state(project_id)
        owned_ids = {entry.resource_id for entry in manifest.knowledge}
        for reference in source.knowledge_refs:
            if ResourceRef.from_string(reference).resource_id not in owned_ids:
                raise ProjectError(
                    f"Knowledge {reference} does not belong to this Project.",
                    "knowledge_unbound",
                )

    def _validate_resource_bindings(self, project_id: str, source: AgentSource) -> None:
        tool_references = {
            node.uses
            for node in source.nodes
            if node.component_type is ComponentType.TOOL and node.uses
        }
        for binding in (source.ui.get("bindings") or {}).values():
            if (
                isinstance(binding, dict)
                and binding.get("kind") in {"tool", "mcp_tool"}
                and isinstance(binding.get("reference"), str)
            ):
                tool_references.add(binding["reference"])
        component_references = {
            node.uses
            for node in source.nodes
            if node.component_type is ComponentType.CUSTOM_COMPONENT and node.uses
        }
        bindings = {
            binding.reference: binding.content_hash
            for binding in self.projects.project_resource_bindings(project_id)
        }
        for reference in sorted(tool_references):
            if reference not in bindings:
                raise ProjectError(
                    f"Tool {reference} is not bound to this Project.",
                    "resource_unbound",
                )
            if source.lock[reference] != bindings[reference]:
                raise ProjectError(
                    f"Tool {reference} must lock the Project pinned content hash.",
                    "resource_lock_mismatch",
                )
        if source.is_loop:
            for reference in source.skill_refs:
                if reference not in bindings:
                    raise ProjectError(
                        f"Skill {reference} is not bound to this Project.",
                        "resource_unbound",
                    )
                if source.lock.get(reference) != bindings[reference]:
                    raise ProjectError(
                        f"Skill {reference} must lock the Project pinned content hash.",
                        "resource_lock_mismatch",
                    )
        for reference in sorted(component_references):
            component_ref = ResourceRef.from_string(reference, "custom_component.uses")
            if self.custom_components is None:
                raise ProjectError(
                    f"Custom Component {reference} is not available in this Project.",
                    "resource_unbound",
                )
            try:
                component = self.custom_components.get(
                    project_id, component_ref.resource_id, version=component_ref.version
                )
            except CustomComponentError as exc:
                raise ProjectError(
                    f"Custom Component {reference} is not available in this Project.",
                    "resource_unbound",
                ) from exc
            if component.get("reference") != reference:
                raise ProjectError(
                    f"Custom Component {reference} is not available in this Project.",
                    "resource_unbound",
                )
            if source.lock.get(reference) != component.get("content_hash"):
                raise ProjectError(
                    f"Custom Component {reference} must lock its published "
                    "content hash.",
                    "resource_lock_mismatch",
                )

    def validate(
        self,
        project_id: str,
        agent_id: str,
        *,
        resource_projection: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        draft = self.draft(project_id, agent_id)
        source = AgentSource.from_dict(draft["source"])
        result = {
            "schema_version": SCHEMA_VERSION,
            "valid": True,
            "source_hash": source.source_hash,
            "behavior_hash": source.behavior_hash,
            "lock_hash": source.lock_hash,
            "file_hash": draft["source_file_hash"],
        }
        if self.catalog is not None:
            result.update(
                inspect_agent_dependencies(
                    self.projects,
                    self.catalog,
                    project_id,
                    source,
                    resource_projection=resource_projection,
                    project_custom_components=(
                        self.custom_components.descriptors(project_id)
                        if self.custom_components is not None
                        else []
                    ),
                )
            )
        return result

    @_serialized
    def commit(
        self,
        *,
        project_id: str,
        agent_id: str,
        expected_revision: int,
        expected_etag: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        IdempotencyKey(SCHEMA_VERSION, idempotency_key)
        agent = self._agent_in_project(project_id, agent_id)
        scope = f"commit:{project_id}:{agent_id}"
        source_path = self._source_path(project_id, agent)
        if isinstance(expected_revision, bool) or not isinstance(
            expected_revision, int
        ):
            raise ProjectError("expected_revision must be an integer")
        request_digest = sha256_digest(
            {"expected_revision": expected_revision, "expected_etag": expected_etag}
        )
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, request_digest
            )
            if replay is not None:
                return replay
            draft = connection.execute(
                "SELECT * FROM agent_drafts WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            if draft is None:
                raise DraftConflict("source changed outside Studio; reload it")
            if draft["revision"] != expected_revision or draft["etag"] != expected_etag:
                raise DraftConflict("draft revision or ETag does not match")
            source_text = self.projects._read_text(source_path)
            current_file_hash = file_hash(source_text)
            if draft["source_file_hash"] != current_file_hash:
                raise DraftConflict("source changed outside Studio; reload it")
            source = AgentSource.from_dict(
                self.projects._parse_yaml(source_text, agent["slug"])
            )
            self._validate_resource_bindings(project_id, source)
            self._validate_knowledge_ownership(project_id, source)
            existing = self.repository.version_by_fingerprint(
                connection, agent_id, current_file_hash
            )
            if existing is None:
                version_id = new_uuid7()
                self.repository.insert_version(
                    connection,
                    {
                        "version_id": version_id,
                        "agent_id": agent_id,
                        "source_hash": source.source_hash,
                        "behavior_hash": source.behavior_hash,
                        "lock_hash": source.lock_hash,
                        "file_hash": current_file_hash,
                        "source": source.to_dict(),
                        "source_text": source_text,
                        "created_at": datetime.now(UTC)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "committed": True,
                    },
                )
            else:
                version_id = existing["version_id"]
            self.repository.mark_version_committed(connection, version_id)
            self.repository.attach_file_to_version(
                connection,
                version_id=version_id,
                project_id=project_id,
                relative_path=agent["source_path"],
            )
            result = {
                "schema_version": SCHEMA_VERSION,
                "version_id": version_id,
                "agent_id": agent_id,
                "source_hash": existing["source_hash"]
                if existing
                else source.source_hash,
                "behavior_hash": existing["behavior_hash"]
                if existing
                else source.behavior_hash,
                "lock_hash": existing["lock_hash"] if existing else source.lock_hash,
                "file_hash": current_file_hash,
            }
            self.repository.remember_response(
                connection, scope, idempotency_key, request_digest, result
            )
            return result

    @_serialized
    def workflow_draft(self, project_id: str, workflow_id: str) -> dict[str, Any]:
        self._workflow_in_project(project_id, workflow_id)
        draft = self.repository.workflow_draft(workflow_id)
        if draft is None:
            raise ProjectError("Workflow has not been indexed")
        self._ensure_workflow_disk_matches_draft(
            project_id, workflow_id, draft["source_file_hash"]
        )
        return self._draft_payload(draft)

    @_serialized
    def reload_workflow_from_disk(
        self, project_id: str, workflow_id: str
    ) -> dict[str, Any]:
        """Explicitly accept an external Workflow source edit as the next draft."""
        workflow = self._workflow_in_project(project_id, workflow_id)
        source_path = self._workflow_source_path(project_id, workflow)
        source_text = self.projects._read_text(source_path)
        source = WorkflowSource.from_dict(
            self.projects._parse_yaml(source_text, workflow["slug"])
        )
        if source.workflow_id != workflow_id or source.slug != workflow["slug"]:
            raise ProjectError("disk source identity must match its Project Workflow")
        digest = file_hash(source_text)
        with self.repository.transaction() as connection:
            draft = connection.execute(
                "SELECT * FROM workflow_drafts WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if draft is None:
                raise ProjectError("Workflow has not been indexed")
            revision = draft["revision"] + 1
            etag = _etag(revision, digest)
            connection.execute(
                """UPDATE workflow_drafts SET revision = ?, source_json = ?,
                   source_file_hash = ?, etag = ? WHERE workflow_id = ?""",
                (
                    revision,
                    json.dumps(source.to_dict(), sort_keys=True, separators=(",", ":")),
                    digest,
                    etag,
                    workflow_id,
                ),
            )
            connection.execute(
                "UPDATE workflows SET source_file_hash = ? WHERE workflow_id = ?",
                (digest, workflow_id),
            )
            self.projects._index_file(
                connection,
                project_id,
                self._project_root(project_id),
                source_path,
                source_text.encode("utf-8"),
                _utc_now(),
            )
        return self.workflow_draft(project_id, workflow_id)

    @_serialized
    def replace_workflow_draft(
        self,
        *,
        project_id: str,
        workflow_id: str,
        source: dict[str, Any],
        expected_revision: int,
        expected_etag: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        IdempotencyKey(SCHEMA_VERSION, idempotency_key)
        parsed = WorkflowSource.from_dict(source)
        workflow = self._workflow_in_project(project_id, workflow_id)
        if parsed.workflow_id != workflow_id or parsed.slug != workflow["slug"]:
            raise ProjectError("draft source identity must match its Project Workflow")
        if isinstance(expected_revision, bool) or not isinstance(
            expected_revision, int
        ):
            raise ProjectError("expected_revision must be an integer")
        scope = f"workflow-draft:{project_id}:{workflow_id}"
        request_digest = sha256_digest(
            {
                "source": parsed.to_dict(),
                "revision": expected_revision,
                "etag": expected_etag,
            }
        )
        source_path = self._workflow_source_path(project_id, workflow)
        previous_text = self.projects._read_text(source_path)
        current_disk_hash = file_hash(previous_text)
        canonical_text = self.projects._canonical_source(parsed.to_dict())
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, request_digest
            )
            if replay is not None:
                return replay
            draft = connection.execute(
                "SELECT * FROM workflow_drafts WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if draft is None:
                raise ProjectError("Workflow has not been indexed")
            if draft["source_file_hash"] != current_disk_hash:
                raise DraftConflict("source changed outside Studio; reload it")
            if expected_etag != draft["etag"]:
                raise DraftConflict("draft ETag does not match")
            if draft["revision"] != expected_revision:
                raise DraftConflict("draft revision does not match")
            intent_id = self.repository.create_workflow_write_intent(
                connection,
                workflow_id=workflow_id,
                previous_source_text=previous_text,
                intended_source_text=canonical_text,
            )
        try:
            self.projects.atomic_write(source_path, canonical_text)
            updated_hash = file_hash(canonical_text)
            next_revision = expected_revision + 1
            etag = _etag(next_revision, updated_hash)
            result = {
                "schema_version": SCHEMA_VERSION,
                "revision": next_revision,
                "etag": etag,
                "source": parsed.to_dict(),
            }
            with self.repository.transaction() as connection:
                if not self.repository.update_workflow_draft(
                    connection,
                    workflow_id=workflow_id,
                    expected_revision=expected_revision,
                    source=parsed.to_dict(),
                    source_file_hash=updated_hash,
                    etag=etag,
                ):
                    raise DraftConflict("draft changed concurrently")
                connection.execute(
                    "UPDATE workflows SET source_file_hash = ? WHERE workflow_id = ?",
                    (updated_hash, workflow_id),
                )
                self.projects._index_file(
                    connection,
                    project_id,
                    self._project_root(project_id),
                    source_path,
                    canonical_text.encode("utf-8"),
                    _utc_now(),
                )
                self.repository.remember_response(
                    connection, scope, idempotency_key, request_digest, result
                )
                self.repository.remove_workflow_write_intent(connection, intent_id)
            return result
        except BaseException:
            self.projects.atomic_write(source_path, previous_text)
            with self.repository.transaction() as connection:
                self.repository.remove_workflow_write_intent(connection, intent_id)
            raise

    def validate_workflow(self, project_id: str, workflow_id: str) -> dict[str, Any]:
        draft = self.workflow_draft(project_id, workflow_id)
        source = WorkflowSource.from_dict(draft["source"])
        resolve_workflow_calls(self.repository, project_id, source)
        return {
            "schema_version": SCHEMA_VERSION,
            "valid": True,
            "source_hash": source.source_hash,
            "behavior_hash": source.behavior_hash,
            "lock_hash": source.lock_hash,
            "file_hash": draft["source_file_hash"],
        }

    @_serialized
    def commit_workflow(
        self,
        *,
        project_id: str,
        workflow_id: str,
        expected_revision: int,
        expected_etag: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._save_workflow_version(
            project_id=project_id,
            workflow_id=workflow_id,
            expected_revision=expected_revision,
            expected_etag=expected_etag,
            committed=True,
            idempotency_key=idempotency_key,
        )

    @_serialized
    def snapshot_workflow_draft(
        self,
        *,
        project_id: str,
        workflow_id: str,
        expected_revision: int,
        expected_etag: str,
    ) -> dict[str, Any]:
        """Persist the exact Studio Test Run source without committing it."""
        return self._save_workflow_version(
            project_id=project_id,
            workflow_id=workflow_id,
            expected_revision=expected_revision,
            expected_etag=expected_etag,
            committed=False,
            idempotency_key=None,
        )

    def _save_workflow_version(
        self,
        *,
        project_id: str,
        workflow_id: str,
        expected_revision: int,
        expected_etag: str,
        committed: bool,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        if idempotency_key is not None:
            IdempotencyKey(SCHEMA_VERSION, idempotency_key)
        workflow = self._workflow_in_project(project_id, workflow_id)
        scope = f"workflow-commit:{project_id}:{workflow_id}"
        source_path = self._workflow_source_path(project_id, workflow)
        if isinstance(expected_revision, bool) or not isinstance(
            expected_revision, int
        ):
            raise ProjectError("expected_revision must be an integer")
        request_digest = sha256_digest(
            {"expected_revision": expected_revision, "expected_etag": expected_etag}
        )
        with self.repository.transaction() as connection:
            replay = (
                self.repository.idempotent_response(
                    connection, scope, idempotency_key, request_digest
                )
                if idempotency_key is not None
                else None
            )
            if replay is not None:
                replay_version = self.repository.workflow_version_for_workflow(
                    workflow_id, replay["version_id"]
                )
                if replay_version is None:
                    raise ProjectError(
                        "Committed Workflow version is unavailable",
                        "workflow_version_invalid",
                    )
                if committed and not self.repository.mark_workflow_version_committed(
                    connection,
                    workflow_id=workflow_id,
                    version_id=replay["version_id"],
                ):
                    raise ProjectError(
                        "Workflow version could not be committed",
                        "workflow_version_invalid",
                    )
                replay["committed"] = bool(committed or replay_version["committed"])
                return replay
            draft = connection.execute(
                "SELECT * FROM workflow_drafts WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if draft is None:
                raise DraftConflict("source changed outside Studio; reload it")
            if draft["revision"] != expected_revision or draft["etag"] != expected_etag:
                raise DraftConflict("draft revision or ETag does not match")
            source_text = self.projects._read_text(source_path)
            current_file_hash = file_hash(source_text)
            if draft["source_file_hash"] != current_file_hash:
                raise DraftConflict("source changed outside Studio; reload it")
            source = WorkflowSource.from_dict(
                self.projects._parse_yaml(source_text, workflow["slug"])
            )
            resolve_workflow_calls(
                self.repository, project_id, source, connection=connection
            )
            existing = self.repository.workflow_version_by_fingerprint(
                connection, workflow_id, current_file_hash
            )
            if existing is None:
                version_id = new_uuid7()
                self.repository.insert_workflow_version(
                    connection,
                    {
                        "version_id": version_id,
                        "workflow_id": workflow_id,
                        "source_hash": source.source_hash,
                        "behavior_hash": source.behavior_hash,
                        "lock_hash": source.lock_hash,
                        "file_hash": current_file_hash,
                        "source": source.to_dict(),
                        "source_text": source_text,
                        "created_at": datetime.now(UTC)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "committed": committed,
                    },
                )
            else:
                version_id = existing["version_id"]
            if committed and not self.repository.mark_workflow_version_committed(
                connection, workflow_id=workflow_id, version_id=version_id
            ):
                raise ProjectError(
                    "Workflow version could not be committed",
                    "workflow_version_invalid",
                )
            self.repository.attach_file_to_workflow_version(
                connection,
                version_id=version_id,
                project_id=project_id,
                relative_path=workflow["source_path"],
            )
            result = {
                "schema_version": SCHEMA_VERSION,
                "version_id": version_id,
                "workflow_id": workflow_id,
                "source_hash": existing["source_hash"]
                if existing
                else source.source_hash,
                "behavior_hash": existing["behavior_hash"]
                if existing
                else source.behavior_hash,
                "lock_hash": existing["lock_hash"] if existing else source.lock_hash,
                "file_hash": current_file_hash,
                "committed": bool(committed or (existing and existing["committed"])),
            }
            if idempotency_key is not None:
                self.repository.remember_response(
                    connection, scope, idempotency_key, request_digest, result
                )
            return result

    @_serialized
    def workflow_version_snapshot(
        self,
        project_id: str,
        workflow_id: str,
        version_id: str | None,
        *,
        committed_only: bool = True,
    ) -> dict[str, Any] | None:
        """Resolve and verify one immutable Workflow snapshot for Runtime use."""
        workflow = self._workflow_in_project(project_id, workflow_id)
        version = (
            self.repository.latest_committed_workflow_version(workflow_id)
            if version_id is None
            else self.repository.workflow_version_for_workflow(workflow_id, version_id)
        )
        if version is None:
            return None
        if committed_only and not bool(version["committed"]):
            raise ProjectError(
                "Workflow version has not been explicitly committed",
                "workflow_version_not_committed",
            )
        try:
            source = WorkflowSource.from_dict(json.loads(version["source_json"]))
            source_text = version["source_text"]
            source_from_text = WorkflowSource.from_dict(
                self.projects._parse_yaml(source_text, workflow["slug"])
            )
        except (ContractValidationError, TypeError, ValueError) as exc:
            raise ProjectError(
                "Workflow version source is invalid", "workflow_version_invalid"
            ) from exc
        if (
            source.workflow_id != workflow_id
            or source.slug != workflow["slug"]
            or source_from_text.to_dict() != source.to_dict()
            or source.source_hash != version["source_hash"]
            or source.behavior_hash != version["behavior_hash"]
            or source.lock_hash != version["lock_hash"]
            or file_hash(source_text) != version["file_hash"]
        ):
            raise ProjectError(
                "Workflow version source or hash does not match its snapshot",
                "workflow_version_invalid",
            )
        return dict(version)

    def versions(self, project_id: str, agent_id: str) -> dict[str, Any]:
        self._agent_in_project(project_id, agent_id)
        return {
            "schema_version": SCHEMA_VERSION,
            "versions": [
                self._version_payload(row, "agent_id")
                for row in self.repository.agent_versions(agent_id)
            ],
        }

    def workflow_versions(self, project_id: str, workflow_id: str) -> dict[str, Any]:
        self._workflow_in_project(project_id, workflow_id)
        return {
            "schema_version": SCHEMA_VERSION,
            "versions": [
                self._version_payload(row, "workflow_id")
                for row in self.repository.workflow_versions(workflow_id)
            ],
        }

    @staticmethod
    def _version_payload(row: Any, identity_field: str) -> dict[str, Any]:
        payload = {
            "version_id": row["version_id"],
            identity_field: row[identity_field],
            "source_hash": row["source_hash"],
            "behavior_hash": row["behavior_hash"],
            "lock_hash": row["lock_hash"],
            "file_hash": row["file_hash"],
            "created_at": row["created_at"],
            "source": json.loads(row["source_json"]),
        }
        keys = row.keys() if hasattr(row, "keys") else []
        if "committed" in keys:
            payload["committed"] = bool(row["committed"])
        return payload

    def export(self, project_id: str, agent_id: str) -> dict[str, Any]:
        agent = self._agent_in_project(project_id, agent_id)
        source_text = self.projects._read_text(self._source_path(project_id, agent))
        source = AgentSource.from_dict(
            self.projects._parse_yaml(source_text, agent["slug"])
        )
        share_source_text = self.projects._canonical_source(source.to_dict())
        result = {
            "schema_version": SCHEMA_VERSION,
            "kind": "agent",
            "agent_id": agent_id,
            "version": source.version,
            "name": source.name,
            "dependencies": sorted(source.lock),
            "source": source.to_dict(),
            "source_text": source_text,
            "file_hash": file_hash(source_text),
            "community_package": {
                "source_text": share_source_text,
                "file_hash": file_hash(share_source_text),
                "source_hash": source.source_hash,
                "behavior_hash": source.behavior_hash,
                "lock_hash": source.lock_hash,
                "dependencies": sorted(source.lock),
                "version": source.version,
                "slug": source.slug,
                "name": source.name,
                "description": source.description,
            },
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

    def _workflow_in_project(self, project_id: str, workflow_id: str) -> Any:
        workflow = self.repository.workflow(workflow_id)
        if workflow is None or workflow["project_id"] != project_id:
            raise ProjectError("unknown Project Workflow")
        return workflow

    def _workflow_source_path(self, project_id: str, workflow: Any) -> Path:
        return self.projects._safe_file(
            self._project_root(project_id), Path(workflow["source_path"])
        )

    def _ensure_workflow_disk_matches_draft(
        self, project_id: str, workflow_id: str, draft_hash: str
    ) -> None:
        workflow = self._workflow_in_project(project_id, workflow_id)
        current = file_hash(
            self.projects._read_text(self._workflow_source_path(project_id, workflow))
        )
        if current != draft_hash:
            raise DraftConflict("source changed outside Studio; reload it")

    def _agent_in_project(self, project_id: str, agent_id: str) -> Any:
        agent = self.repository.agent(agent_id)
        if agent is None or agent["project_id"] != project_id:
            raise ProjectError("unknown Project Agent")
        return agent

    def _source_path(self, project_id: str, agent: Any) -> Path:
        return self.projects._safe_file(
            self._project_root(project_id), Path(agent["source_path"])
        )

    def _project_root(self, project_id: str) -> Path:
        project = self.repository.project(project_id)
        if project is None:
            raise ProjectError("unknown Project")
        return self.projects._existing_root(project["root_path"])

    def _ensure_disk_matches_draft(
        self, project_id: str, agent_id: str, draft_hash: str
    ) -> None:
        agent = self._agent_in_project(project_id, agent_id)
        current = file_hash(
            self.projects._read_text(self._source_path(project_id, agent))
        )
        if current != draft_hash:
            raise DraftConflict("source changed outside Studio; reload it")

    @staticmethod
    def _draft_payload(draft: Any) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "draft_id": draft["draft_id"],
            "revision": draft["revision"],
            "etag": draft["etag"],
            "source_file_hash": draft["source_file_hash"],
            "source": json.loads(draft["source_json"]),
        }
