"""Discover and safely materialize portable Project Artifacts."""

from __future__ import annotations

import json
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.project_artifact import (
    ProjectArtifactEnvelope,
)
from veyra_agent_platform.contracts.workflow import WorkflowSource
from veyra_agent_platform.local.projects.custom_components import (
    CustomComponentService,
)
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.storage.project_sync import now_text
from veyra_agent_platform.local.storage.repositories import LocalRepository


class ProjectArtifactSyncError(ValueError):
    """A portable Artifact could not be discovered or materialized safely."""


class ProjectArtifactSyncService:
    def __init__(
        self,
        repository: LocalRepository,
        projects: ProjectService,
        custom_components: CustomComponentService,
    ) -> None:
        self.repository = repository
        self.projects = projects
        self.custom_components = custom_components

    def manifest(self, project_id: str) -> dict[str, Any]:
        payloads = self._discover(project_id)
        current = set(payloads)
        for key, payload in payloads.items():
            kind, artifact_id = key
            self._observe(
                project_id,
                kind,
                artifact_id,
                sha256_digest(payload),
                deleted=False,
            )
        for row in self.repository.artifact_sync_states(project_id):
            key = (row["artifact_kind"], row["artifact_id"])
            if key not in current and not row["deleted"]:
                self._observe(
                    project_id,
                    key[0],
                    key[1],
                    sha256_digest({}),
                    deleted=True,
                )
        return {
            "schema_version": "1.0",
            "project_id": project_id,
            "artifacts": [
                {
                    "artifact_kind": row["artifact_kind"],
                    "artifact_id": row["artifact_id"],
                    "content_hash": row["local_content_hash"],
                    "revision": row["local_revision"],
                    "cloud_revision": row["cloud_revision"],
                    "deleted": bool(row["deleted"]),
                    "state": row["state"],
                }
                for row in self.repository.artifact_sync_states(project_id)
            ],
        }

    def get(
        self, project_id: str, artifact_kind: str, artifact_id: str
    ) -> ProjectArtifactEnvelope:
        payloads = self._discover(project_id)
        key = (artifact_kind, artifact_id)
        if key in payloads:
            row = self._observe(
                project_id,
                artifact_kind,
                artifact_id,
                sha256_digest(payloads[key]),
                deleted=False,
            )
            return ProjectArtifactEnvelope.build(
                project_id=project_id,
                artifact_kind=artifact_kind,  # type: ignore[arg-type]
                artifact_id=artifact_id,
                payload=payloads[key],
                revision=row["local_revision"],
                immutable=artifact_kind in {"agent_version", "custom_component"},
            )
        row = next(
            (
                item
                for item in self.repository.artifact_sync_states(project_id)
                if item["artifact_kind"] == artifact_kind
                and item["artifact_id"] == artifact_id
                and item["deleted"]
            ),
            None,
        )
        if row is None:
            raise ProjectArtifactSyncError("Artifact is not present in this Project")
        return ProjectArtifactEnvelope.build(
            project_id=project_id,
            artifact_kind=artifact_kind,  # type: ignore[arg-type]
            artifact_id=artifact_id,
            payload={},
            revision=row["local_revision"],
            deleted=True,
            immutable=False,
        )

    def materialize(self, envelope: ProjectArtifactEnvelope) -> dict[str, Any]:
        try:
            if envelope.deleted:
                result = {"status": "tombstone", "artifact_id": envelope.artifact_id}
            elif envelope.artifact_kind == "agent":
                source_payload = envelope.payload.get("source")
                if not isinstance(source_payload, dict):
                    raise ProjectArtifactSyncError("Agent Artifact source is invalid")
                source = AgentSource.from_dict(source_payload)
                result = self.projects.install_synced_agent(
                    project_id=envelope.project_id,
                    source=source,
                    parent_agent_id=envelope.payload.get("parent_agent_id"),
                )
            elif envelope.artifact_kind == "agent_version":
                result = self.projects.install_synced_agent_version(
                    project_id=envelope.project_id, payload=envelope.payload
                )
            elif envelope.artifact_kind == "workflow":
                result = self.projects.install_synced_workflow(
                    project_id=envelope.project_id,
                    source=WorkflowSource.from_dict(envelope.payload),
                )
            elif envelope.artifact_kind == "custom_component":
                result = self.custom_components.install_synced_definition(
                    envelope.project_id, envelope.payload
                )
            elif envelope.artifact_kind == "knowledge_metadata":
                result = self.projects.install_synced_knowledge_metadata(
                    project_id=envelope.project_id, payload=envelope.payload
                )
            else:
                raise ProjectArtifactSyncError("Artifact kind is not supported")
        except (ProjectError, ValueError) as error:
            raise ProjectArtifactSyncError(str(error)) from error
        self.repository.update_artifact_sync_state(
            project_id=envelope.project_id,
            artifact_kind=envelope.artifact_kind,
            artifact_id=envelope.artifact_id,
            local_content_hash=envelope.content_hash,
            deleted=envelope.deleted,
            state="synced",
            cloud_revision=envelope.revision,
            last_synced_hash=envelope.content_hash,
            last_synced_at=now_text(),
            error_code=None,
        )
        return {"schema_version": "1.0", "status": "materialized", "result": result}

    def record(
        self,
        project_id: str,
        *,
        artifact_kind: str,
        artifact_id: str,
        state: str,
        cloud_revision: int | None,
        last_synced_hash: str | None,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        row = self.repository.artifact_sync_state(
            project_id, artifact_kind, artifact_id
        )
        if row is None:
            raise ProjectArtifactSyncError("Artifact sync state is unknown")
        updated = self.repository.update_artifact_sync_state(
            project_id=project_id,
            artifact_kind=artifact_kind,
            artifact_id=artifact_id,
            local_content_hash=row["local_content_hash"],
            deleted=bool(row["deleted"]),
            state=state,
            cloud_revision=cloud_revision,
            last_synced_hash=last_synced_hash,
            last_synced_at=now_text() if state == "synced" else row["last_synced_at"],
            error_code=error_code,
        )
        return {
            "schema_version": "1.0",
            "project_id": updated["project_id"],
            "artifact_kind": updated["artifact_kind"],
            "artifact_id": updated["artifact_id"],
            "local_revision": updated["local_revision"],
            "cloud_revision": updated["cloud_revision"],
            "local_content_hash": updated["local_content_hash"],
            "last_synced_hash": updated["last_synced_hash"],
            "state": updated["state"],
            "deleted": bool(updated["deleted"]),
            "last_synced_at": updated["last_synced_at"],
            "error_code": updated["error_code"],
        }

    def _discover(self, project_id: str) -> dict[tuple[str, str], dict[str, Any]]:
        _, root, _, _, manifest = self.projects._project_manifest_state(project_id)
        payloads: dict[tuple[str, str], dict[str, Any]] = {}
        for agent_entry in manifest.agents:
            source = self.projects._agent_source(root, agent_entry)
            payloads[("agent", agent_entry.agent_id)] = {
                "source": source.to_dict(),
                "parent_agent_id": agent_entry.parent_agent_id,
            }
        for version in self.repository.project_agent_versions(project_id):
            payloads[("agent_version", version["version_id"])] = {
                "version_id": version["version_id"],
                "agent_id": version["agent_id"],
                "source": json.loads(version["source_json"]),
                "source_hash": version["source_hash"],
                "behavior_hash": version["behavior_hash"],
                "lock_hash": version["lock_hash"],
                "created_at": version["created_at"],
            }
        for workflow_entry in manifest.workflows:
            workflow_source = self.projects._workflow_source(root, workflow_entry)
            payloads[("workflow", workflow_entry.resource_id)] = (
                workflow_source.to_dict()
            )
        components = self.custom_components.list(project_id)["components"]
        for component in components:
            for version in component["versions"]:
                public = self.custom_components.get(
                    project_id, component["component_id"], version=version["version"]
                )
                payloads[("custom_component", public["reference"])] = {
                    key: value
                    for key, value in public.items()
                    if key not in {"reference", "deprecated", "content_hash"}
                }
        for knowledge_entry in manifest.knowledge:
            listing = self.projects._knowledge_listing(root, knowledge_entry)
            processing = listing.get("processing") or {}
            payload: dict[str, Any] = {
                "knowledge_id": knowledge_entry.resource_id,
                "slug": listing["slug"],
                "name": listing["name"],
                "description": listing["description"],
                "version": listing["version"],
                "source_type": processing.get("origin", "project_document"),
                "source_filename": processing.get("filename", "document.md"),
                "content_hash": listing["source_file_hash"],
                "source_state": "metadata_only",
            }
            if isinstance(listing.get("source_ref"), dict):
                payload["source_ref"] = listing["source_ref"]
            payloads[("knowledge_metadata", knowledge_entry.resource_id)] = payload
        return payloads

    def _observe(
        self,
        project_id: str,
        artifact_kind: str,
        artifact_id: str,
        content_hash: str,
        *,
        deleted: bool,
    ) -> Any:
        row = self.repository.artifact_sync_state(
            project_id, artifact_kind, artifact_id
        )
        changed = row is not None and row["local_content_hash"] != content_hash
        if row is None:
            state = "local_only"
        elif changed and row["state"] != "conflict":
            state = "pending_push"
        else:
            state = row["state"]
        return self.repository.update_artifact_sync_state(
            project_id=project_id,
            artifact_kind=artifact_kind,
            artifact_id=artifact_id,
            local_content_hash=content_hash,
            deleted=deleted,
            state=state,
            cloud_revision=None if row is None else row["cloud_revision"],
            last_synced_hash=None if row is None else row["last_synced_hash"],
            last_synced_at=None if row is None else row["last_synced_at"],
            error_code=None if row is None else row["error_code"],
            increment_local_revision=changed,
        )
