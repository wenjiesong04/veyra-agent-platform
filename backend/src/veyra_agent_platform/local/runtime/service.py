"""Closed, deterministic executor for the initial V1 flow components."""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource, ComponentType, FlowNode
from veyra_agent_platform.contracts.canonical import file_hash, sha256_digest
from veyra_agent_platform.contracts.common import (
    SCHEMA_VERSION,
    IdempotencyKey,
    new_uuid7,
)
from veyra_agent_platform.contracts.workflow import WorkflowSource
from veyra_agent_platform.local.library.dependencies import (
    inspect_agent_dependencies,
)
from veyra_agent_platform.local.library.knowledge_context import read_knowledge_context
from veyra_agent_platform.local.library.service import LibraryService
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.resources import ResourceCatalog, ResourceCatalogError
from veyra_agent_platform.local.resources.project import (
    ProjectResourceError,
    ProjectResourceService,
)
from veyra_agent_platform.local.resources.readiness import ResourceReadiness
from veyra_agent_platform.local.storage.repositories import LocalRepository

from .client import RuntimeModelClient, RuntimeProviderError
from .config import RuntimeSettings
from .conversations import AgentConversationService
from .profiles import RuntimeApiProfile, RuntimeProfileStore
from .tools import ToolAuthorization, ToolRuntime, ToolRuntimeError

_TOKEN = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")
_COMPARE = re.compile(
    r"^([a-z][a-z0-9_]*)(?:\s*)(==|!=)(?:\s*)('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|true|false|[0-9]+)$"
)


class _RunAbandoned(Exception):
    """The run left the running state before the executor could finish."""


class RuntimeError(ProjectError):
    """A typed terminal runtime failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.events: list[tuple[str | None, str, dict[str, Any]]] = []
        self.tool_calls: tuple[_ToolCallRecord, ...] = ()


@dataclass(frozen=True)
class _ToolCallRecord:
    node_id: str
    tool_reference: str
    authorization: str
    decision_code: str
    decision_reason: str
    input_digest: str
    receipt: dict[str, Any] | None


@dataclass(frozen=True)
class _ExecutionPause:
    node_id: str
    prompt: str
    values: dict[str, Any]
    events: list[tuple[str | None, str, dict[str, Any]]]
    tool_calls: tuple[_ToolCallRecord, ...]


@dataclass(frozen=True)
class _ExecutionOutcome:
    events: list[tuple[str | None, str, dict[str, Any]]]
    tool_calls: tuple[_ToolCallRecord, ...]
    result: dict[str, Any] | None
    verified: bool
    pause: _ExecutionPause | None


class RuntimeService:
    def __init__(
        self,
        repository: LocalRepository,
        projects: ProjectService,
        library: LibraryService,
        model: RuntimeModelClient | None = None,
        tools: ToolRuntime | None = None,
        profiles: RuntimeProfileStore | None = None,
        conversations: AgentConversationService | None = None,
        project_resources: ProjectResourceService | None = None,
        resource_readiness: ResourceReadiness | None = None,
    ) -> None:
        self.repository, self.projects, self.library = repository, projects, library
        self.model = model or RuntimeModelClient(RuntimeSettings())
        self.tools = tools or ToolRuntime(ResourceCatalog())
        self.project_resources = project_resources or ProjectResourceService(
            projects, self.tools.catalog
        )
        self.resource_readiness = resource_readiness or ResourceReadiness(
            self.tools.catalog, self.model, self.tools._adapters.keys(), self.tools.mcp
        )
        self.profiles = profiles or RuntimeProfileStore(repository)
        self.conversations = conversations
        self.repository.interrupt_orphan_runs()

    def status(self) -> dict[str, Any]:
        return self.model.status()

    def validate_profile(self, profile: RuntimeApiProfile) -> dict[str, Any]:
        """Validate a supplied profile without persisting it or running a prompt."""
        settings = self.model.settings.model_copy(
            update={
                "model_base_url": profile.base_url,
                "model_id": profile.model_id,
                "model_api_key_env": profile.api_key_env,
            }
        )
        client = RuntimeModelClient(
            settings,
            transport=self.model.transport,
            secret_store=self.model.secret_store,
        )
        try:
            client.validate()
        except RuntimeProviderError as exc:
            return {
                "schema_version": SCHEMA_VERSION,
                "valid": False,
                "configured": exc.code != "runtime_not_configured",
                "model_available": False,
                "provider": profile.provider,
                "base_url": profile.base_url,
                "model_id": profile.model_id,
                "api_key_env": profile.api_key_env,
                "code": exc.code,
                "message": str(exc),
            }
        return {
            "schema_version": SCHEMA_VERSION,
            "valid": True,
            "configured": True,
            "model_available": True,
            "provider": profile.provider,
            "base_url": profile.base_url,
            "model_id": profile.model_id,
            "api_key_env": profile.api_key_env,
            "code": "validated",
            "message": (
                "Runtime model credentials and model availability were verified."
            ),
        }

    def readiness(self, project_id: str, agent_id: str) -> dict[str, Any]:
        """Return a no-effect startup preflight for one effective Agent Runtime."""
        agent = self.library._agent_in_project(project_id, agent_id)
        source_path = self.library._source_path(project_id, agent)
        source_text = self.projects._read_text(source_path)
        source = AgentSource.from_dict(
            self.projects._parse_yaml(source_text, agent["slug"])
        )
        return self.readiness_for_source(project_id, agent_id, source)

    def readiness_for_source(
        self, project_id: str, agent_id: str, source: AgentSource
    ) -> dict[str, Any]:
        """Preflight a current draft or an immutable Agent snapshot.

        Workflow AgentCall nodes execute pinned snapshots.  Keeping this
        source-based variant separate from ``readiness`` prevents a Workflow
        preflight from accidentally inspecting an Agent's newer mutable draft.
        It is deliberately non-mutating and never calls the model provider.
        """
        if source.agent_id != agent_id:
            raise RuntimeError(
                "source_identity_invalid",
                "source identity does not match requested Agent",
            )
        dependencies = inspect_agent_dependencies(
            self.projects, self.tools.catalog, project_id, source
        )
        model = self._model_for(project_id, agent_id)
        model_status = model.status()
        requires_model = any(
            node.component_type in {ComponentType.AGENT, ComponentType.MODEL}
            for node in source.nodes
        )
        model_ready = not requires_model or bool(model_status["configured"])
        model_detail = (
            "No model node is present in this Agent."
            if not requires_model
            else (
                "Effective Runtime model credentials are available."
                if model_ready
                else "Effective Runtime model credentials are not configured."
            )
        )
        _, profile_source = self.profiles.effective(project_id, agent_id)
        tool_checks = self._tool_readiness(project_id, source)
        tools_ready = all(item["ready"] for item in tool_checks)
        checks = [
            {
                "id": "dependencies",
                "ready": bool(dependencies["runtime_ready"]),
                "code": "ready"
                if dependencies["runtime_ready"]
                else "dependency_attention",
                "detail": (
                    "All Agent dependencies are resolved."
                    if dependencies["runtime_ready"]
                    else "One or more Agent dependencies need attention."
                ),
            },
            {
                "id": "model",
                "ready": model_ready,
                "code": "ready" if model_ready else "runtime_not_configured",
                "detail": model_detail,
            },
            {
                "id": "tools",
                "ready": tools_ready,
                "code": "ready" if tools_ready else "tool_runtime_unavailable",
                "detail": (
                    "Tool Runtime authorization preflight passed."
                    if tools_ready
                    else "One or more Tools cannot pass Runtime authorization."
                ),
            },
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": project_id,
            "agent_id": agent_id,
            "ready": all(item["ready"] for item in checks),
            "profile_source": profile_source,
            "model": {
                "required": requires_model,
                "configured": bool(model_status["configured"]),
                "model_id": model_status["model_id"],
                "model_base_url": model_status["model_base_url"],
                "model_api_key_env": model_status["model_api_key_env"],
            },
            "dependency_summary": dependencies["dependency_summary"],
            "dependencies": dependencies["dependencies"],
            "tool_checks": tool_checks,
            "checks": checks,
        }

    def _authorize_tool(
        self,
        project_id: str,
        source: AgentSource,
        node: FlowNode,
        values: dict[str, Any],
    ) -> ToolAuthorization:
        if node.uses is None:
            return self.tools.authorize(source=source, node=node, values=values)
        try:
            resource = self.project_resources.resolve_pin(
                project_id, node.uses, source.lock.get(node.uses)
            )
        except ProjectResourceError as exc:
            return self.tools._denied(node.uses, exc.code, str(exc), values)
        return self.tools.authorize(
            source=source,
            node=node,
            values=values,
            resource=self.resource_readiness.project(resource),
        )

    def _tool_readiness(
        self, project_id: str, source: AgentSource
    ) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        for node in source.nodes:
            if node.component_type is not ComponentType.TOOL:
                continue
            authorization = self._authorize_tool(project_id, source, node, {})
            ready = authorization.decision == "allowed"
            code = authorization.code
            detail = authorization.reason
            checks.append(
                {
                    "node_id": node.id,
                    "reference": node.uses or "tool_reference_missing",
                    "ready": ready,
                    "code": code,
                    "detail": detail,
                }
            )
        return checks

    def components(self) -> dict[str, Any]:
        from veyra_agent_platform.local.components import component_registry

        return {"schema_version": SCHEMA_VERSION, "components": component_registry()}

    def run(
        self,
        project_id: str,
        agent_id: str,
        inputs: dict[str, Any],
        idempotency_key: str,
        conversation_id: str | None = None,
        append_user: bool = True,
    ) -> dict[str, Any]:
        IdempotencyKey(SCHEMA_VERSION, idempotency_key)
        agent = self.library._agent_in_project(project_id, agent_id)
        source_path = self.library._source_path(project_id, agent)
        source_text = self.projects._read_text(source_path)
        source = AgentSource.from_dict(
            self.projects._parse_yaml(source_text, agent["slug"])
        )
        if source.agent_id != agent_id:
            raise RuntimeError(
                "source_identity_invalid",
                "source identity does not match requested Agent",
            )
        self._validate_inputs(source, inputs)
        fingerprint = file_hash(source_text)
        scope = f"run:{project_id}:{agent_id}"
        digest = sha256_digest(
            {
                "file_hash": fingerprint,
                "inputs": inputs,
                "conversation_id": conversation_id,
            }
        )
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, digest
            )
            if replay is not None:
                return replay
            draft = connection.execute(
                "SELECT source_file_hash FROM agent_drafts WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
            if draft is None or draft["source_file_hash"] != fingerprint:
                raise RuntimeError(
                    "source_changed",
                    "source changed outside Studio; reload it before running",
                )
            version = self.repository.version_by_fingerprint(
                connection, agent_id, fingerprint
            )
            if version is None:
                version_id = new_uuid7()
                self.repository.insert_version(
                    connection,
                    {
                        "version_id": version_id,
                        "agent_id": agent_id,
                        "source_hash": source.source_hash,
                        "behavior_hash": source.behavior_hash,
                        "lock_hash": source.lock_hash,
                        "file_hash": fingerprint,
                        "source": source.to_dict(),
                        "source_text": source_text,
                        "created_at": _now(),
                    },
                )
                self.repository.attach_file_to_version(
                    connection,
                    version_id=version_id,
                    project_id=project_id,
                    relative_path=agent["source_path"],
                )
            else:
                version_id = version["version_id"]
            run_id = new_uuid7()
            conversation_context = ""
            resolved_conversation_id = conversation_id
            if self.conversations is not None and (conversation_id or append_user):
                resolved_conversation_id, conversation_context = (
                    self.conversations.prepare_turn(
                        connection,
                        project_id=project_id,
                        agent_id=agent_id,
                        conversation_id=conversation_id,
                        inputs=inputs,
                        run_id=run_id,
                        append_user=append_user,
                    )
                )
            elif conversation_id:
                raise RuntimeError(
                    "conversation_unavailable",
                    "Agent conversation service is unavailable",
                )
            self.repository.create_run(
                connection,
                run_id=run_id,
                project_id=project_id,
                agent_id=agent_id,
                version_id=version_id,
                created_at=_now(),
                inputs=inputs,
                conversation_id=resolved_conversation_id,
            )
            self.repository.add_run_events(
                connection,
                run_id,
                [(None, "run.created", {}), (None, "run.started", {})],
            )
            started = self._row_payload(
                connection.execute(
                    "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
            )
            self.repository.remember_response(
                connection, scope, idempotency_key, digest, started
            )
        self._schedule_execution(
            run_id,
            lambda: self._complete_execution(
                project_id,
                run_id,
                source,
                inputs,
                start_node=None,
                approved=False,
                conversation_id=resolved_conversation_id,
                conversation_context=conversation_context,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            ),
        )
        return started

    def run_version(
        self,
        project_id: str,
        agent_id: str,
        version_id: str,
        inputs: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Execute a pinned snapshot without inspecting or changing its draft."""
        IdempotencyKey(SCHEMA_VERSION, idempotency_key)
        self.library._agent_in_project(project_id, agent_id)
        version = self.repository.version(version_id)
        if version is None or version["agent_id"] != agent_id:
            raise RuntimeError(
                "agent_version_not_found", "Committed Agent version not found"
            )
        source = AgentSource.from_dict(json.loads(version["source_json"]))
        if source.agent_id != agent_id or source.source_hash != version["source_hash"]:
            raise RuntimeError(
                "agent_version_invalid", "Agent version integrity check failed"
            )
        self._validate_inputs(source, inputs)
        scope = f"run-version:{project_id}:{agent_id}:{version_id}"
        digest = sha256_digest({"version_id": version_id, "inputs": inputs})
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, digest
            )
            if replay is not None:
                return replay
            run_id = new_uuid7()
            self.repository.create_run(
                connection,
                run_id=run_id,
                project_id=project_id,
                agent_id=agent_id,
                version_id=version_id,
                created_at=_now(),
                inputs=inputs,
            )
            self.repository.add_run_events(
                connection,
                run_id,
                [(None, "run.created", {}), (None, "run.started", {})],
            )
            started = self._row_payload(
                connection.execute(
                    "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
            )
            self.repository.remember_response(
                connection, scope, idempotency_key, digest, started
            )
        self._schedule_execution(
            run_id,
            lambda: self._complete_execution(
                project_id,
                run_id,
                source,
                inputs,
                start_node=None,
                approved=False,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            ),
        )
        return started

    def command(
        self,
        project_id: str,
        agent_id: str,
        run_id: str,
        command: str,
        idempotency_key: str,
        *,
        checkpoint_id: str | None = None,
    ) -> dict[str, Any]:
        IdempotencyKey(SCHEMA_VERSION, idempotency_key)
        self.library._agent_in_project(project_id, agent_id)
        row = self.repository.run(run_id)
        if (
            row is None
            or row["agent_id"] != agent_id
            or row["project_id"] != project_id
        ):
            raise ProjectError("unknown Agent run")
        if command not in {"approve", "reject", "stop", "resume", "retry"}:
            raise RuntimeError("command_invalid", "Unsupported run command")
        scope = f"run-command:{run_id}"
        digest = sha256_digest({"command": command})
        if checkpoint_id is not None:
            if command != "resume":
                raise RuntimeError(
                    "command_invalid", "Only Resume accepts a checkpoint"
                )
            digest = sha256_digest({"command": command, "checkpoint_id": checkpoint_id})
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, digest
            )
            if replay is not None:
                return replay
        if command == "retry":
            return self._retry_run(
                row, scope=scope, idempotency_key=idempotency_key, digest=digest
            )
        if command == "stop":
            return self._stop_run(
                row, scope=scope, idempotency_key=idempotency_key, digest=digest
            )
        if command == "resume":
            return self._resume_run(
                row,
                checkpoint_id=checkpoint_id,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            )
        return self._resolve_approval(
            row,
            decision="approved" if command == "approve" else "rejected",
            scope=scope,
            idempotency_key=idempotency_key,
            digest=digest,
        )

    def runs(self, project_id: str, agent_id: str) -> dict[str, Any]:
        self.library._agent_in_project(project_id, agent_id)
        return {
            "schema_version": SCHEMA_VERSION,
            "runs": [self._row_payload(row) for row in self.repository.runs(agent_id)],
        }

    def run_detail(self, project_id: str, agent_id: str, run_id: str) -> dict[str, Any]:
        self.library._agent_in_project(project_id, agent_id)
        row = self.repository.run(run_id)
        if (
            row is None
            or row["agent_id"] != agent_id
            or row["project_id"] != project_id
        ):
            raise ProjectError("unknown Agent run")
        payload = self._row_payload(row)
        payload["events"] = self.repository.run_events(run_id)
        return payload

    def ensure_run(self, project_id: str, agent_id: str, run_id: str) -> None:
        self.run_detail(project_id, agent_id, run_id)

    def follow_events(self, run_id: str, after: int) -> Iterator[str]:
        last = after
        while True:
            events = self.repository.run_events_after(run_id, last)
            for event in events:
                last = int(event["sequence"])
                yield _sse_frame("runtime", event, event_id=str(last))
            row = self.repository.run(run_id)
            if row is None:
                raise ProjectError("unknown Agent run")
            if row["status"] not in {"running", "waiting"} and not events:
                yield _sse_frame("done", {"status": row["status"]})
                return
            if not events:
                time.sleep(0.05)

    def _persist_event(
        self,
        run_id: str,
        node_id: str | None,
        kind: str,
        payload: dict[str, Any],
    ) -> None:
        with self.repository.transaction() as connection:
            if kind == "tool.started":
                row = connection.execute(
                    "SELECT status FROM runtime_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                if row is None or row["status"] != "running":
                    raise _RunAbandoned()
            self.repository.add_run_events(
                connection, run_id, [(node_id, kind, payload)]
            )

    def _commit_outcome(
        self,
        run_id: str,
        outcome: _ExecutionOutcome,
        *,
        scope: str | None,
        idempotency_key: str | None,
        digest: str | None,
        conversation_id: str | None = None,
        extra_events: list[tuple[str | None, str, dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        if not self._is_running(run_id) and outcome.pause is None:
            return self._run_response(run_id)
        if outcome.pause is not None:
            return self._pause_run(
                run_id,
                _ExecutionPause(
                    node_id=outcome.pause.node_id,
                    prompt=outcome.pause.prompt,
                    values=outcome.pause.values,
                    events=[],
                    tool_calls=outcome.pause.tool_calls,
                ),
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            )
        with self.repository.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row["status"] != "running":
                return self._row_payload(row)
            self.repository.add_run_events(connection, run_id, list(extra_events or []))
            self._store_tool_calls(connection, run_id, outcome.tool_calls)
            final_status = "verified" if outcome.verified else "unverified"
            self.repository.add_run_events(
                connection,
                run_id,
                [(None, "run.completed", {"state": final_status})],
            )
            self.repository.finish_run(
                connection,
                run_id,
                status=final_status,
                result=outcome.result,
                code=None,
                message=None,
                finished_at=_now(),
            )
            if conversation_id and outcome.result is not None and self.conversations:
                self.conversations.append_assistant(
                    connection,
                    conversation_id=conversation_id,
                    run_id=run_id,
                    result=outcome.result,
                )
            return self._stored_run_response(
                connection,
                run_id,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            )

    def _fail_run(
        self,
        run_id: str,
        exc: RuntimeError,
        *,
        scope: str | None,
        idempotency_key: str | None,
        digest: str | None,
    ) -> dict[str, Any]:
        if not self._is_running(run_id):
            return self._run_response(run_id)
        with self.repository.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row["status"] != "running":
                return self._row_payload(row)
            self.repository.add_run_events(
                connection,
                run_id,
                [(None, "run.failed", {"code": exc.code})],
            )
            self._store_tool_calls(connection, run_id, exc.tool_calls)
            self.repository.finish_run(
                connection,
                run_id,
                status="failed",
                result=None,
                code=exc.code,
                message=str(exc),
                finished_at=_now(),
            )
            return self._stored_run_response(
                connection,
                run_id,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            )

    def _pause_run(
        self,
        run_id: str,
        pause: _ExecutionPause,
        *,
        scope: str | None,
        idempotency_key: str | None,
        digest: str | None,
    ) -> dict[str, Any]:
        now = _now()
        with self.repository.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row["status"] != "running":
                return self._row_payload(row)
            self._store_tool_calls(connection, run_id, pause.tool_calls)
            self.repository.insert_approval_request(
                connection,
                approval_id=new_uuid7(),
                run_id=run_id,
                node_id=pause.node_id,
                prompt=pause.prompt,
                created_at=now,
            )
            self.repository.insert_checkpoint(
                connection,
                checkpoint_id=new_uuid7(),
                run_id=run_id,
                node_id=pause.node_id,
                waiting_kind="approval",
                values=pause.values,
                created_at=now,
            )
            self.repository.set_run_status(connection, run_id, status="waiting")
            self.repository.add_run_events(
                connection,
                run_id,
                [
                    (pause.node_id, "node.waiting", {"reason": "approval"}),
                    (pause.node_id, "approval.requested", {"prompt": pause.prompt}),
                    (
                        pause.node_id,
                        "checkpoint.created",
                        {"waiting_kind": "approval"},
                    ),
                ],
            )
            return self._stored_run_response(
                connection,
                run_id,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            )

    def _stored_run_response(
        self,
        connection: Any,
        run_id: str,
        *,
        scope: str | None,
        idempotency_key: str | None,
        digest: str | None,
    ) -> dict[str, Any]:
        response = self._row_payload(
            connection.execute(
                "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        )
        if scope and idempotency_key and digest:
            self.repository.replace_idempotent_response(
                connection, scope, idempotency_key, digest, response
            )
        self.repository.replace_run_idempotent_payload(connection, run_id, response)
        return response

    def _store_tool_calls(
        self,
        connection: Any,
        run_id: str,
        records: tuple[_ToolCallRecord, ...],
    ) -> None:
        now = _now()
        for record in records:
            self.repository.insert_tool_call(
                connection,
                run_id=run_id,
                node_id=record.node_id,
                tool_reference=record.tool_reference,
                authorization=record.authorization,
                decision_code=record.decision_code,
                decision_reason=record.decision_reason,
                input_digest=record.input_digest,
                receipt=record.receipt,
                created_at=now,
            )

    def _recovery_identity(
        self, project_id: str, source: AgentSource
    ) -> dict[str, Any]:
        project = self.repository.project(project_id)
        if project is None:
            raise RuntimeError("project_invalid", "Project is unavailable")
        model = self._model_for(project_id, source.agent_id)
        return {
            "source_hash": source.source_hash,
            "permissions": source.permissions.to_dict(),
            "resource_lock": dict(source.lock),
            "project_root": str(self.projects._existing_root(project["root_path"])),
            "model_base_url": model.settings.model_base_url,
            "model_id": model.settings.model_id,
            "model_api_key_env": model.settings.model_api_key_env,
        }

    def _checkpoint_execution(
        self,
        project_id: str,
        run_id: str,
        source: AgentSource,
        node_id: str,
        values: dict[str, Any],
        *,
        approved: bool,
        verified: bool,
        conversation_context: str,
        tool_calls: tuple[_ToolCallRecord, ...],
    ) -> None:
        state = {
            "values": values,
            "approved": approved,
            "verified": verified,
            "conversation_context": conversation_context,
            "identity": self._recovery_identity(project_id, source),
        }
        checkpoint_id = new_uuid7()
        with self.repository.transaction() as connection:
            row = connection.execute(
                "SELECT status FROM runtime_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None or row["status"] != "running":
                raise _RunAbandoned()
            self._store_tool_calls(connection, run_id, tool_calls)
            self.repository.add_run_events(
                connection,
                run_id,
                [
                    (
                        node_id,
                        "checkpoint.created",
                        {
                            "checkpoint_id": checkpoint_id,
                            "waiting_kind": "execution",
                            "next_node_id": node_id,
                        },
                    )
                ],
            )
            state["sequence"] = connection.execute(
                "SELECT MAX(sequence) FROM runtime_run_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            self.repository.insert_checkpoint(
                connection,
                checkpoint_id=checkpoint_id,
                run_id=run_id,
                node_id=node_id,
                waiting_kind="execution",
                values=state,
                created_at=_now(),
            )

    def _resume_run(
        self,
        row: Any,
        *,
        checkpoint_id: str | None,
        scope: str,
        idempotency_key: str,
        digest: str,
    ) -> dict[str, Any]:
        if not checkpoint_id:
            raise RuntimeError(
                "command_not_applicable",
                "Resume requires an explicit execution checkpoint",
            )
        version = self.repository.version(row["version_id"])
        if version is None or version["agent_id"] != row["agent_id"]:
            raise RuntimeError(
                "agent_version_not_found", "Committed Agent version not found"
            )
        source = AgentSource.from_dict(json.loads(version["source_json"]))
        if (
            source.agent_id != row["agent_id"]
            or source.source_hash != version["source_hash"]
        ):
            raise RuntimeError(
                "agent_version_invalid", "Agent version integrity check failed"
            )
        inputs = self.repository.run_inputs(row["run_id"])
        self._validate_inputs(source, inputs)
        now, command_id, run_id = _now(), new_uuid7(), new_uuid7()
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, digest
            )
            if replay is not None:
                return replay
            current = connection.execute(
                "SELECT * FROM runtime_runs WHERE run_id = ?", (row["run_id"],)
            ).fetchone()
            if current["status"] not in {"failed", "interrupted"}:
                raise RuntimeError(
                    "command_not_applicable",
                    "Resume requires a failed or interrupted run; "
                    "Stop revokes recovery",
                )
            checkpoint = self.repository.latest_checkpoint(connection, row["run_id"])
            if (
                checkpoint is None
                or checkpoint["checkpoint_id"] != checkpoint_id
                or checkpoint["waiting_kind"] != "execution"
            ):
                raise RuntimeError(
                    "resume_checkpoint_invalid",
                    "Only the latest execution checkpoint is recoverable; "
                    "approval waits require Approve/Reject",
                )
            previous = connection.execute(
                "SELECT payload_json FROM runtime_run_commands WHERE run_id = ? "
                "AND command_type = 'resume' AND status = 'applied'",
                (row["run_id"],),
            ).fetchone()
            if previous is not None:
                child_id = json.loads(previous["payload_json"])["resume_run_id"]
                response = self._row_payload(
                    connection.execute(
                        "SELECT * FROM runtime_runs WHERE run_id = ?", (child_id,)
                    ).fetchone()
                )
                self.repository.remember_response(
                    connection, scope, idempotency_key, digest, response
                )
                return response
            state = json.loads(checkpoint["values_json"])
            dispatched = connection.execute(
                "SELECT 1 FROM runtime_run_events WHERE run_id = ? "
                "AND sequence > ? AND kind = 'tool.started' LIMIT 1",
                (row["run_id"], state["sequence"]),
            ).fetchone()
            if dispatched is not None:
                raise RuntimeError(
                    "resume_effect_unsafe",
                    "A Tool was dispatched after this checkpoint; "
                    "reconcile its effects before recovery",
                )
            if state["identity"] != self._recovery_identity(row["project_id"], source):
                raise RuntimeError(
                    "resume_identity_changed",
                    "Checkpoint resource, workspace or Runtime "
                    "profile identity changed",
                )
            dependencies = inspect_agent_dependencies(
                self.projects, self.tools.catalog, row["project_id"], source
            )
            if not dependencies["runtime_ready"]:
                raise RuntimeError(
                    "resume_dependencies_unavailable",
                    "Pinned checkpoint dependencies are not available",
                )
            self.repository.create_run(
                connection,
                run_id=run_id,
                project_id=row["project_id"],
                agent_id=row["agent_id"],
                version_id=row["version_id"],
                created_at=now,
                inputs=inputs,
                conversation_id=row["conversation_id"],
            )
            self.repository.insert_run_command(
                connection,
                command_id=command_id,
                run_id=row["run_id"],
                command_type="resume",
                payload={"resume_run_id": run_id, "checkpoint_id": checkpoint_id},
                status="applied",
                created_at=now,
                applied_at=now,
            )
            self.repository.add_run_events(
                connection,
                run_id,
                [
                    (
                        None,
                        "run.created",
                        {
                            "resume_of_run_id": row["run_id"],
                            "resume_command_id": command_id,
                            "checkpoint_id": checkpoint_id,
                            "next_node_id": checkpoint["node_id"],
                            "version_id": row["version_id"],
                            "inputs": inputs,
                            "recovery_identity": state["identity"],
                        },
                    ),
                    (None, "run.started", {}),
                ],
            )
            child_checkpoint_id = new_uuid7()
            self.repository.add_run_events(
                connection,
                run_id,
                [
                    (
                        checkpoint["node_id"],
                        "checkpoint.created",
                        {
                            "checkpoint_id": child_checkpoint_id,
                            "waiting_kind": "execution",
                            "next_node_id": checkpoint["node_id"],
                        },
                    )
                ],
            )
            self.repository.insert_checkpoint(
                connection,
                checkpoint_id=child_checkpoint_id,
                run_id=run_id,
                node_id=checkpoint["node_id"],
                waiting_kind="execution",
                values={
                    **state,
                    "sequence": connection.execute(
                        "SELECT MAX(sequence) FROM runtime_run_events WHERE run_id = ?",
                        (run_id,),
                    ).fetchone()[0],
                },
                created_at=now,
            )
            response = self._row_payload(
                connection.execute(
                    "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
            )
            self.repository.remember_response(
                connection, scope, idempotency_key, digest, response
            )
        self._schedule_execution(
            run_id,
            lambda: self._complete_execution(
                row["project_id"],
                run_id,
                source,
                state["values"],
                start_node=checkpoint["node_id"],
                approved=state["approved"],
                verified=state["verified"],
                conversation_context=state["conversation_context"],
                conversation_id=row["conversation_id"],
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            ),
        )
        return response

    def _retry_run(
        self,
        row: Any,
        *,
        scope: str,
        idempotency_key: str,
        digest: str,
    ) -> dict[str, Any]:
        if row["status"] not in {"failed", "interrupted", "cancelled"}:
            raise RuntimeError(
                "command_not_applicable",
                "Retry is only available for terminal unsuccessful runs",
            )
        inputs = self.repository.run_inputs(row["run_id"])
        version = self.repository.version(row["version_id"])
        if version is None or version["agent_id"] != row["agent_id"]:
            raise RuntimeError(
                "agent_version_not_found", "Committed Agent version not found"
            )
        source = AgentSource.from_dict(json.loads(version["source_json"]))
        if (
            source.agent_id != row["agent_id"]
            or source.source_hash != version["source_hash"]
        ):
            raise RuntimeError(
                "agent_version_invalid", "Agent version integrity check failed"
            )
        self._validate_inputs(source, inputs)
        now = _now()
        command_id = new_uuid7()
        run_id = new_uuid7()
        conversation_id = row["conversation_id"]
        conversation_context = ""
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, digest
            )
            if replay is not None:
                return replay
            # Receipts are stored at outcome/pause; absence cannot prove no effect.
            # The durable pre-dispatch event also covers cancellation and process loss.
            ancestor_id = row["run_id"]
            while ancestor_id:
                dispatched = connection.execute(
                    "SELECT 1 FROM runtime_run_events WHERE run_id = ? "
                    "AND kind = 'tool.started' LIMIT 1",
                    (ancestor_id,),
                ).fetchone()
                if dispatched is not None:
                    raise RuntimeError(
                        "retry_effect_unsafe",
                        "Retry blocked: a Tool may have produced external effects. "
                        "Inspect the original run and reconcile effects manually "
                        "before a new run.",
                    )
                created = connection.execute(
                    "SELECT payload_json FROM runtime_run_events WHERE run_id = ? "
                    "AND kind = 'run.created' ORDER BY sequence LIMIT 1",
                    (ancestor_id,),
                ).fetchone()
                ancestor_id = (
                    json.loads(created["payload_json"]).get("resume_of_run_id")
                    if created is not None
                    else None
                )
            if conversation_id and self.conversations is not None:
                conversation_id, conversation_context = self.conversations.prepare_turn(
                    connection,
                    project_id=row["project_id"],
                    agent_id=row["agent_id"],
                    conversation_id=conversation_id,
                    inputs=inputs,
                    run_id=run_id,
                    append_user=False,
                )
            elif conversation_id:
                raise RuntimeError(
                    "conversation_unavailable",
                    "Agent conversation service is unavailable",
                )
            self.repository.create_run(
                connection,
                run_id=run_id,
                project_id=row["project_id"],
                agent_id=row["agent_id"],
                version_id=row["version_id"],
                created_at=now,
                inputs=inputs,
                conversation_id=conversation_id,
            )
            self.repository.insert_run_command(
                connection,
                command_id=command_id,
                run_id=row["run_id"],
                command_type="retry",
                payload={"retry_run_id": run_id},
                status="applied",
                created_at=now,
                applied_at=now,
            )
            self.repository.add_run_events(
                connection,
                run_id,
                [
                    (
                        None,
                        "run.created",
                        {
                            "retry_of_run_id": row["run_id"],
                            "retry_command_id": command_id,
                            "version_id": row["version_id"],
                            "inputs": inputs,
                        },
                    ),
                    (None, "run.started", {}),
                ],
            )
            response = self._row_payload(
                connection.execute(
                    "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
            )
            self.repository.remember_response(
                connection, scope, idempotency_key, digest, response
            )
        self._schedule_execution(
            run_id,
            lambda: self._complete_execution(
                row["project_id"],
                run_id,
                source,
                inputs,
                start_node=None,
                approved=False,
                conversation_id=conversation_id,
                conversation_context=conversation_context,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            ),
        )
        return response

    def _stop_run(
        self,
        row: Any,
        *,
        scope: str,
        idempotency_key: str,
        digest: str,
    ) -> dict[str, Any]:
        now = _now()
        command_id = new_uuid7()
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, digest
            )
            if replay is not None:
                return replay
            row = connection.execute(
                "SELECT * FROM runtime_runs WHERE run_id = ?", (row["run_id"],)
            ).fetchone()
            if row["status"] not in {"waiting", "running"}:
                raise RuntimeError(
                    "command_not_applicable", "Stop is only available for active runs"
                )
            self.repository.remember_response(
                connection, scope, idempotency_key, digest, self._row_payload(row)
            )
            self.repository.insert_run_command(
                connection,
                command_id=command_id,
                run_id=row["run_id"],
                command_type="stop",
                payload={},
                status="applied",
                created_at=now,
                applied_at=now,
            )
            self.repository.cancel_pending_approvals(
                connection, row["run_id"], resolved_at=now
            )
            self.repository.add_run_events(
                connection, row["run_id"], [(None, "run.cancelled", {})]
            )
            self.repository.finish_run(
                connection,
                row["run_id"],
                status="cancelled",
                result=None,
                code="run_cancelled",
                message="run stopped by command",
                finished_at=now,
            )
            self.repository.mark_command_applied(connection, command_id, applied_at=now)
            return self._stored_run_response(
                connection,
                row["run_id"],
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            )

    def _resolve_approval(
        self,
        row: Any,
        *,
        decision: str,
        scope: str,
        idempotency_key: str,
        digest: str,
    ) -> dict[str, Any]:
        if row["status"] != "waiting":
            raise RuntimeError(
                "command_not_applicable", "This run is not waiting for approval"
            )
        now = _now()
        command_id = new_uuid7()
        with self.repository.transaction() as connection:
            replay = self.repository.idempotent_response(
                connection, scope, idempotency_key, digest
            )
            if replay is not None:
                return replay
            row = connection.execute(
                "SELECT * FROM runtime_runs WHERE run_id = ?", (row["run_id"],)
            ).fetchone()
            if row["status"] != "waiting":
                raise RuntimeError(
                    "command_not_applicable", "This run is not waiting for approval"
                )
            pending = self.repository.pending_approval(connection, row["run_id"])
            checkpoint = self.repository.latest_checkpoint(connection, row["run_id"])
            if pending is None or checkpoint is None:
                raise RuntimeError(
                    "command_not_applicable", "No pending approval checkpoint"
                )
            version = connection.execute(
                "SELECT source_json FROM agent_versions WHERE version_id = ?",
                (row["version_id"],),
            ).fetchone()
            if version is None:
                raise RuntimeError("version_missing", "Agent version is unavailable")
            source = AgentSource.from_dict(json.loads(version["source_json"]))
            values = json.loads(checkpoint["values_json"])
            if (
                decision == "rejected"
                and source.outputs.get("written") == "boolean"
                and "written" not in values
            ):
                values["written"] = False
            next_node = next(
                (
                    edge.to_node
                    for edge in source.transitions
                    if edge.from_node == pending["node_id"]
                    and edge.port.value == decision
                ),
                "",
            )
            if not next_node:
                raise RuntimeError(
                    "transition_missing",
                    f"node {pending['node_id']} did not select a valid transition",
                )
            self.repository.remember_response(
                connection, scope, idempotency_key, digest, self._row_payload(row)
            )
            self.repository.insert_run_command(
                connection,
                command_id=command_id,
                run_id=row["run_id"],
                command_type="approve" if decision == "approved" else "reject",
                payload={"decision": decision},
                status="accepted",
                created_at=now,
            )
            self.repository.resolve_approval(
                connection,
                pending["approval_id"],
                status=decision,
                command_id=command_id,
                resolved_at=now,
            )
            self.repository.set_run_status(connection, row["run_id"], status="running")
            self.repository.add_run_events(
                connection,
                row["run_id"],
                [
                    (
                        pending["node_id"],
                        "approval.resolved",
                        {"decision": decision},
                    ),
                    (
                        pending["node_id"],
                        "node.completed",
                        {"port": decision},
                    ),
                ],
            )
            self.repository.mark_command_applied(connection, command_id, applied_at=now)
            resumed = self._row_payload(
                connection.execute(
                    "SELECT * FROM runtime_runs WHERE run_id = ?", (row["run_id"],)
                ).fetchone()
            )
            self.repository.replace_idempotent_response(
                connection, scope, idempotency_key, digest, resumed
            )
            self.repository.replace_run_idempotent_payload(
                connection, row["run_id"], resumed
            )
        conversation_id = row["conversation_id"]
        conversation_context = (
            self.conversations.prompt_context(conversation_id)
            if self.conversations is not None and conversation_id
            else ""
        )
        self._schedule_execution(
            row["run_id"],
            lambda: self._complete_execution(
                row["project_id"],
                row["run_id"],
                source,
                values,
                start_node=next_node,
                approved=decision == "approved",
                conversation_id=conversation_id,
                conversation_context=conversation_context,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            ),
        )
        return resumed

    def _schedule_execution(self, run_id: str, worker: Callable[[], None]) -> None:
        threading.Thread(
            target=worker, daemon=True, name=f"veyra-run-{run_id[:8]}"
        ).start()

    def _complete_execution(
        self,
        project_id: str,
        run_id: str,
        source: AgentSource,
        inputs: dict[str, Any],
        *,
        start_node: str | None,
        approved: bool,
        scope: str | None,
        idempotency_key: str | None,
        digest: str | None,
        conversation_id: str | None = None,
        conversation_context: str = "",
        verified: bool = False,
    ) -> None:
        try:
            outcome = self._execute(
                project_id,
                run_id,
                source,
                inputs,
                self._model_for(project_id, source.agent_id),
                start_node=start_node,
                approved=approved,
                conversation_context=conversation_context,
                verified=verified,
            )
            if not self._is_running(run_id):
                return
            self._commit_outcome(
                run_id,
                outcome,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
                conversation_id=conversation_id,
            )
        except _RunAbandoned:
            return
        except RuntimeError as exc:
            if self._is_running(run_id):
                self._fail_run(
                    run_id,
                    exc,
                    scope=scope,
                    idempotency_key=idempotency_key,
                    digest=digest,
                )

    def _is_running(self, run_id: str) -> bool:
        row = self.repository.run(run_id)
        return row is not None and row["status"] == "running"

    def _run_response(self, run_id: str) -> dict[str, Any]:
        row = self.repository.run(run_id)
        assert row is not None
        return self._row_payload(row)

    @staticmethod
    def _row_payload(row: Any) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": row["run_id"],
            "project_id": row["project_id"],
            "agent_id": row["agent_id"],
            "version_id": row["version_id"],
            "conversation_id": row["conversation_id"],
            "status": row["status"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": (
                {"code": row["error_code"], "message": row["error_message"]}
                if row["error_code"]
                else None
            ),
            "created_at": row["created_at"],
            "finished_at": row["finished_at"],
        }

    @staticmethod
    def _validate_inputs(
        source: AgentSource | WorkflowSource, inputs: dict[str, Any]
    ) -> None:
        if set(inputs) != set(source.inputs):
            raise RuntimeError(
                "inputs_invalid", "inputs must exactly match the Agent source inputs"
            )
        validators: dict[str, Callable[[Any], bool]] = {
            "string": lambda value: isinstance(value, str),
            "boolean": lambda value: isinstance(value, bool),
            "integer": lambda value: isinstance(value, int)
            and not isinstance(value, bool),
            "number": lambda value: isinstance(value, int | float)
            and not isinstance(value, bool),
            "object": lambda value: isinstance(value, dict),
            "array": lambda value: isinstance(value, list),
        }
        for field, field_type in source.inputs.items():
            validator = validators.get(field_type)
            if validator is None or not validator(inputs[field]):
                raise RuntimeError(
                    "inputs_invalid", f"input {field} must be a {field_type}"
                )

    def _execute(
        self,
        project_id: str,
        run_id: str,
        source: AgentSource,
        inputs: dict[str, Any],
        model: RuntimeModelClient,
        *,
        start_node: str | None = None,
        approved: bool = False,
        conversation_context: str = "",
        verified: bool = False,
    ) -> _ExecutionOutcome:
        nodes = {node.id: node for node in source.nodes}
        edges = {
            (edge.from_node, edge.port.value): edge.to_node
            for edge in source.transitions
        }
        current = start_node or next(
            node.id
            for node in source.nodes
            if node.component_type is ComponentType.START
        )
        values = dict(inputs)
        result: dict[str, Any] = {}
        verifier_passed = verified
        events: list[tuple[str | None, str, dict[str, Any]]] = []
        tool_calls: list[_ToolCallRecord] = []

        def emit(node_id: str | None, kind: str, payload: dict[str, Any]) -> None:
            events.append((node_id, kind, payload))
            self._persist_event(run_id, node_id, kind, payload)

        for _ in range(len(nodes) + 1):
            if not self._is_running(run_id):
                raise _RunAbandoned()
            node = nodes[current]
            self._checkpoint_execution(
                project_id,
                run_id,
                source,
                node.id,
                values,
                approved=approved,
                verified=verifier_passed,
                conversation_context=conversation_context,
                tool_calls=tuple(tool_calls),
            )
            tool_calls.clear()
            emit(
                node.id,
                "node.started",
                {"component_type": node.component_type.value},
            )
            try:
                if node.component_type is ComponentType.START:
                    port = "next"
                elif node.component_type is ComponentType.TRANSFORM:
                    assert node.mapping is not None
                    values.update(
                        {
                            key: _interpolate(template, values)
                            for key, template in node.mapping.items()
                        }
                    )
                    port = "next"
                elif node.component_type is ComponentType.CONDITION:
                    assert node.expression is not None
                    port = "true" if _condition(node.expression, values) else "false"
                elif node.component_type is ComponentType.VERIFIER:
                    assert node.checks is not None
                    result = self._validated_outputs(source, values)
                    verifier_passed = all(
                        _check(check, result) for check in node.checks
                    )
                    port = "passed" if verifier_passed else "failed"
                    emit(node.id, "verifier.result", {"passed": verifier_passed})
                elif node.component_type is ComponentType.TOOL:
                    project = self.repository.project(project_id)
                    if project is None:
                        raise RuntimeError("project_invalid", "Project is unavailable")
                    tool_values = self._tool_input_values(node, values)
                    authorization = self._authorize_tool(
                        project_id, source, node, tool_values
                    )
                    resource = authorization.resource
                    identity = (
                        {
                            "resource_identity": {
                                "reference": resource["reference"],
                                "version": resource["version"],
                                "content_hash": resource["content_hash"],
                                "bound_content_hash": resource["bound_content_hash"],
                                "locked_content_hash": source.lock.get(node.uses or ""),
                            }
                        }
                        if resource is not None
                        else {}
                    )
                    emit(
                        node.id,
                        "tool.requested",
                        {
                            "tool_reference": authorization.tool_reference,
                            "input_digest": authorization.input_digest,
                            "permission": authorization.decision,
                            "code": authorization.code,
                            **identity,
                        },
                    )
                    record = _ToolCallRecord(
                        node_id=node.id,
                        tool_reference=authorization.tool_reference,
                        authorization=authorization.decision,
                        decision_code=authorization.code,
                        decision_reason=authorization.reason,
                        input_digest=authorization.input_digest,
                        receipt=None,
                    )
                    tool_calls.append(record)
                    if authorization.decision != "allowed":
                        raise RuntimeError(authorization.code, authorization.reason)
                    emit(
                        node.id,
                        "tool.started",
                        {"tool_reference": authorization.tool_reference, **identity},
                    )
                    execution = self.tools.execute(
                        project_root=self.projects._existing_root(project["root_path"]),
                        source=source,
                        node=node,
                        values=tool_values,
                        authorization=authorization,
                        approved=approved,
                    )
                    receipt = {**execution.receipt, **identity}
                    emit(node.id, "tool.completed", receipt)
                    tool_calls[-1] = _ToolCallRecord(
                        node_id=record.node_id,
                        tool_reference=record.tool_reference,
                        authorization=record.authorization,
                        decision_code=record.decision_code,
                        decision_reason=record.decision_reason,
                        input_digest=record.input_digest,
                        receipt=receipt,
                    )
                    values.update(self._tool_output_values(node, execution.output))
                    port = "next"
                elif node.component_type is ComponentType.OUTPUT:
                    assert node.output_name is not None
                    result = self._validated_outputs(source, values)
                    emit(node.id, "node.completed", {})
                    return _ExecutionOutcome(
                        events=events,
                        tool_calls=tuple(tool_calls),
                        result=result,
                        verified=verifier_passed,
                        pause=None,
                    )
                elif node.component_type in {ComponentType.AGENT, ComponentType.MODEL}:
                    context_text = ""
                    if source.skill_refs:
                        emit(
                            node.id,
                            "tool.requested",
                            {
                                "tool_reference": "skill.context",
                                "authorization": "allowed",
                                "references": list(source.skill_refs),
                            },
                        )
                        skill_resources = self._skill_resources(source)
                        emit(
                            node.id,
                            "tool.completed",
                            {
                                "tool_reference": "skill.context",
                                "receipts": [
                                    {
                                        "reference": resource["reference"],
                                        "name": resource["name"],
                                        "content_hash": resource["content_hash"],
                                        "instruction_byte_length": len(
                                            str(
                                                resource["spec"].get("instruction", "")
                                            ).encode("utf-8")
                                        ),
                                        "verified": True,
                                    }
                                    for resource in skill_resources
                                ],
                            },
                        )
                    if source.knowledge_refs or any(
                        item["kind"] == "knowledge"
                        for item in (source.ui.get("bindings") or {}).values()
                    ):
                        emit(
                            node.id,
                            "tool.requested",
                            {
                                "tool_reference": "knowledge.context",
                                "authorization": "allowed",
                                "references": list(source.knowledge_refs),
                            },
                        )
                        try:
                            query = json.dumps(
                                [
                                    values[name]
                                    for name in sorted(source.inputs)
                                    if name in values
                                ],
                                ensure_ascii=False,
                                sort_keys=True,
                            )
                            context_text, receipts = read_knowledge_context(
                                self.projects,
                                project_id,
                                source,
                                query,
                            )
                        except ProjectError as exc:
                            raise RuntimeError(exc.code, str(exc)) from exc
                        emit(
                            node.id,
                            "tool.completed",
                            {
                                "tool_reference": "knowledge.context",
                                "receipts": receipts,
                                "query_hash": file_hash(query),
                                "hit_count": len(receipts),
                            },
                        )

                    def emit_model_delta(token: str, node_id: str = node.id) -> None:
                        emit(node_id, "model.delta", {"delta": token})

                    values.update(
                        self._run_agent(
                            node,
                            source,
                            values,
                            model,
                            context_text,
                            conversation_context,
                            on_token=emit_model_delta,
                        )
                    )
                    port = "next"
                elif node.component_type is ComponentType.HUMAN_APPROVAL:
                    prompt = node.prompt or ""
                    if "{{" in prompt:
                        prompt = _interpolate(prompt, values)
                    return _ExecutionOutcome(
                        events=events,
                        tool_calls=tuple(tool_calls),
                        result=None,
                        verified=False,
                        pause=_ExecutionPause(
                            node_id=node.id,
                            prompt=prompt,
                            values=values,
                            events=events,
                            tool_calls=tuple(tool_calls),
                        ),
                    )
                else:
                    raise RuntimeError(
                        "runtime_not_supported",
                        f"{node.component_type.value} is not supported by "
                        "this local Runtime",
                    )
            except _RunAbandoned:
                raise
            except (RuntimeProviderError, ToolRuntimeError) as exc:
                runtime_error = RuntimeError(exc.code, str(exc))
                if isinstance(exc, ToolRuntimeError) and exc.receipt is not None:
                    emit(node.id, "tool.failed", exc.receipt)
                    tool_calls[-1] = replace(tool_calls[-1], receipt=exc.receipt)
                emit(node.id, "node.failed", {"code": runtime_error.code})
                runtime_error.events = events
                runtime_error.tool_calls = tuple(tool_calls)
                raise runtime_error from exc
            except RuntimeError as exc:
                emit(node.id, "node.failed", {"code": exc.code})
                exc.events = events
                exc.tool_calls = tuple(tool_calls)
                raise
            except Exception:
                runtime_error = RuntimeError(
                    "executor_failed", "local Runtime execution failed"
                )
                emit(node.id, "node.failed", {"code": runtime_error.code})
                runtime_error.events = events
                runtime_error.tool_calls = tuple(tool_calls)
                raise runtime_error from None
            emit(node.id, "node.completed", {"port": port})
            time.sleep(0.03)
            if not self._is_running(run_id):
                raise _RunAbandoned()
            current = edges.get((node.id, port), "")
            if not current:
                raise RuntimeError(
                    "transition_missing",
                    f"node {node.id} did not select a valid transition",
                )
        raise RuntimeError(
            "graph_execution_invalid", "graph exceeded deterministic execution limit"
        )

    @staticmethod
    def _validated_outputs(
        source: AgentSource | WorkflowSource, values: dict[str, Any]
    ) -> dict[str, Any]:
        validators: dict[str, Callable[[Any], bool]] = {
            "string": lambda value: isinstance(value, str),
            "boolean": lambda value: isinstance(value, bool),
            "integer": lambda value: isinstance(value, int)
            and not isinstance(value, bool),
            "number": lambda value: isinstance(value, int | float)
            and not isinstance(value, bool),
            "object": lambda value: isinstance(value, dict),
            "array": lambda value: isinstance(value, list),
        }
        result: dict[str, Any] = {}
        for name, output_type in source.outputs.items():
            if name not in values or not validators.get(output_type, lambda _: False)(
                values[name]
            ):
                raise RuntimeError(
                    "output_invalid",
                    f"output {name} is missing or is not a {output_type}",
                )
            result[name] = values[name]
        return result

    @staticmethod
    def _tool_input_values(node: Any, values: dict[str, Any]) -> dict[str, Any]:
        if not node.input_mapping:
            return values
        mapped: dict[str, Any] = {}
        for tool_name, source_name in node.input_mapping.items():
            if source_name not in values:
                raise RuntimeError(
                    "tool_input_missing",
                    f"Tool input mapping source {source_name} is unavailable",
                )
            mapped[tool_name] = values[source_name]
        return mapped

    @staticmethod
    def _tool_output_values(node: Any, output: dict[str, Any]) -> dict[str, Any]:
        if not node.output_mapping:
            return output
        mapped: dict[str, Any] = {}
        for tool_name, value in output.items():
            target_name = node.output_mapping.get(tool_name, tool_name)
            if target_name in mapped:
                raise RuntimeError(
                    "tool_output_mapping_invalid",
                    f"Tool outputs map to the same field {target_name}",
                )
            mapped[target_name] = value
        return mapped

    def _run_agent(
        self,
        node: Any,
        source: AgentSource,
        values: dict[str, Any],
        model: RuntimeModelClient,
        knowledge_context: str = "",
        conversation_context: str = "",
        on_token: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        if not model.configured:
            raise RuntimeError(
                "runtime_not_configured",
                "Agent nodes require a Runtime model API key",
            )
        if node.model_ref != "model.primary":
            raise RuntimeError(
                "runtime_model_unknown",
                "Agent model_ref is not the host Runtime profile",
            )
        prompt = self._agent_system_prompt(node, source)
        if "{{" in prompt:
            prompt = _interpolate(prompt, values)
        user_content = _agent_user_message(source, values) + knowledge_context
        if conversation_context:
            user_content += conversation_context
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ]
        fragments: list[str] = []
        for token in model.stream(messages):
            if not isinstance(token, str) or not token:
                continue
            fragments.append(token)
            if on_token is not None:
                on_token(token)
        return _model_output_values(
            "".join(fragments).strip(), source.outputs, values, node.id
        )

    def _model_for(self, project_id: str, agent_id: str) -> RuntimeModelClient:
        profile, _ = self.profiles.effective(project_id, agent_id)
        if profile is None:
            return self.model
        settings = self.model.settings.model_copy(
            update={
                "model_base_url": profile.base_url,
                "model_id": profile.model_id,
                "model_api_key_env": profile.api_key_env,
            }
        )
        return RuntimeModelClient(
            settings,
            transport=self.model.transport,
            secret_store=self.model.secret_store,
        )

    def _agent_system_prompt(self, node: Any, source: AgentSource) -> str:
        prompt = node.system_prompt or ""
        for resource in self._skill_resources(source):
            instruction = str(resource["spec"].get("instruction", "")).strip()
            marker = f"[{resource['name']}]"
            if instruction and marker not in prompt:
                block = f"{marker} {instruction}"
                prompt = f"{prompt}\n\n{block}" if prompt else block
        return prompt

    def _skill_resources(self, source: AgentSource) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        for reference in source.skill_refs:
            try:
                resource = self.tools.catalog.by_reference(reference)
            except ResourceCatalogError as exc:
                raise RuntimeError(
                    "skill_not_registered",
                    "Skill reference is not registered in the catalog",
                ) from exc
            if source.lock.get(reference) != resource["content_hash"]:
                raise RuntimeError(
                    "skill_lock_invalid",
                    "Skill lock does not match the catalog version",
                )
            if resource["kind"] != "skill":
                raise RuntimeError("skill_invalid", "Locked skill_ref is not a Skill")
            if resource["availability"] != "ready":
                raise RuntimeError(
                    "skill_unavailable",
                    "Skill is not enabled for local Runtime use",
                )
            resources.append(resource)
        return resources


def _agent_user_message(source: AgentSource, values: dict[str, Any]) -> str:
    parts: list[str] = []
    for name, value in values.items():
        parts.append(f"{name}: {value}")
    if not parts:
        raise RuntimeError(
            "agent_input_missing", "Agent nodes need at least one input value"
        )
    return "\n".join(parts)


def _model_output_values(
    content: str,
    outputs: Mapping[str, str],
    values: dict[str, Any],
    node_id: str,
) -> dict[str, Any]:
    """Accept declared outputs; later Model nodes may overwrite earlier results."""

    recorded = {} if node_id in outputs else {node_id: content}
    targets = [
        (name, field_type) for name, field_type in outputs.items() if name not in values
    ]
    if not targets:
        targets = list(outputs.items())
    if len(targets) == 1 and targets[0][1] == "string":
        return {**recorded, targets[0][0]: content}
    try:
        parsed: Any = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "agent_output_invalid", "Agent model did not return valid JSON outputs"
        ) from exc
    if len(targets) == 1:
        name, field_type = targets[0]
        if not _value_matches_type(parsed, field_type):
            raise RuntimeError(
                "agent_output_invalid", f"Agent output {name} is not a {field_type}"
            )
        return {**recorded, name: parsed}
    if not isinstance(parsed, dict) or set(parsed) != {name for name, _ in targets}:
        raise RuntimeError(
            "agent_output_invalid", "Agent model output fields do not match the Agent"
        )
    if not all(
        _value_matches_type(parsed[name], field_type) for name, field_type in targets
    ):
        raise RuntimeError(
            "agent_output_invalid", "Agent model output types are invalid"
        )
    return {**recorded, **parsed}


def _value_matches_type(value: Any, field_type: str) -> bool:
    validators: dict[str, Callable[[Any], bool]] = {
        "string": lambda item: isinstance(item, str),
        "boolean": lambda item: isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, int | float)
        and not isinstance(item, bool),
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
    }
    validator = validators.get(field_type)
    return validator(value) if validator is not None else False


def _interpolate(template: str, values: dict[str, Any]) -> str:
    def replacement(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise RuntimeError("interpolation_missing", f"field {name} is unavailable")
        return str(values[name])

    rendered = _TOKEN.sub(replacement, template)
    if "{{" in rendered or "}}" in rendered:
        raise RuntimeError(
            "interpolation_invalid", "Transform interpolation only accepts {{field}}"
        )
    return rendered


def _condition(expression: str, values: dict[str, Any]) -> bool:
    match = _COMPARE.fullmatch(expression)
    if match is None or match.group(1) not in values:
        raise RuntimeError(
            "condition_invalid",
            "Condition must use field == or != a string, boolean, or integer literal",
        )
    left, operator, raw = values[match.group(1)], match.group(2), match.group(3)
    if raw.startswith('"'):
        try:
            right: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "condition_invalid",
                "Condition contains an invalid string literal",
            ) from exc
    elif raw.startswith("'"):
        right = raw[1:-1]
    elif raw == "true":
        right = True
    elif raw == "false":
        right = False
    else:
        right = int(raw)
    return bool(left == right if operator == "==" else left != right)


def _check(check: str, values: dict[str, Any]) -> bool:
    if check == "output.not_empty":
        return any(bool(value) for value in values.values())
    raise RuntimeError("verifier_invalid", f"unsupported verifier check: {check}")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sse_frame(event: str, data: dict[str, Any], event_id: str | None = None) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {payload}")
    return "\n".join(lines) + "\n\n"
