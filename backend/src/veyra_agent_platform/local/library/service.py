"""Draft editing, recovery, and immutable Agent-version lifecycle."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.canonical import file_hash, sha256_digest
from veyra_agent_platform.contracts.common import (
    SCHEMA_VERSION,
    IdempotencyKey,
    new_uuid7,
)
from veyra_agent_platform.local.projects.service import (
    ProjectError,
    ProjectService,
    _etag,
    _utc_now,
)
from veyra_agent_platform.local.storage.repositories import LocalRepository


class DraftConflict(ProjectError):
    """The source on disk changed or a second Studio window won the edit."""


class LibraryService:
    def __init__(self, repository: LocalRepository, projects: ProjectService) -> None:
        self.repository = repository
        self.projects = projects
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

    def draft(self, project_id: str, agent_id: str) -> dict[str, Any]:
        self._agent_in_project(project_id, agent_id)
        draft = self.repository.draft(agent_id)
        if draft is None:
            raise ProjectError("Agent has not been indexed")
        self._ensure_disk_matches_draft(project_id, agent_id, draft["source_file_hash"])
        return self._draft_payload(draft)

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

    def validate(self, project_id: str, agent_id: str) -> dict[str, Any]:
        draft = self.draft(project_id, agent_id)
        source = AgentSource.from_dict(draft["source"])
        return {
            "schema_version": SCHEMA_VERSION,
            "valid": True,
            "source_hash": source.source_hash,
            "behavior_hash": source.behavior_hash,
            "lock_hash": source.lock_hash,
            "file_hash": draft["source_file_hash"],
        }

    def commit(
        self,
        *,
        project_id: str,
        agent_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        IdempotencyKey(SCHEMA_VERSION, idempotency_key)
        agent = self._agent_in_project(project_id, agent_id)
        scope = f"commit:{project_id}:{agent_id}"
        source_path = self._source_path(project_id, agent)
        source_text = self.projects._read_text(source_path)
        source = AgentSource.from_dict(
            self.projects._parse_yaml(source_text, agent["slug"])
        )
        current_file_hash = file_hash(source_text)
        request_digest = sha256_digest({"file_hash": current_file_hash})
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, request_digest
            )
            if replay is not None:
                return replay
            draft = connection.execute(
                "SELECT * FROM agent_drafts WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            if draft is None or draft["source_file_hash"] != current_file_hash:
                raise DraftConflict("source changed outside Studio; reload it")
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
                    },
                )
            else:
                version_id = existing["version_id"]
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
                "source_hash": source.source_hash,
                "behavior_hash": source.behavior_hash,
                "lock_hash": source.lock_hash,
                "file_hash": current_file_hash,
            }
            self.repository.remember_response(
                connection, scope, idempotency_key, request_digest, result
            )
            return result

    def export(self, project_id: str, agent_id: str) -> dict[str, Any]:
        agent = self._agent_in_project(project_id, agent_id)
        source_text = self.projects._read_text(self._source_path(project_id, agent))
        source = AgentSource.from_dict(
            self.projects._parse_yaml(source_text, agent["slug"])
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "agent_id": agent_id,
            "source": source.to_dict(),
            "source_text": source_text,
            "file_hash": file_hash(source_text),
        }

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
