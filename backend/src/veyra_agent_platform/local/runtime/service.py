"""Closed, deterministic executor for the initial V1 flow components."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource, ComponentType
from veyra_agent_platform.contracts.canonical import file_hash, sha256_digest
from veyra_agent_platform.contracts.common import (
    SCHEMA_VERSION,
    IdempotencyKey,
    new_uuid7,
)
from veyra_agent_platform.local.library.service import LibraryService
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.resources import ResourceCatalog
from veyra_agent_platform.local.storage.repositories import LocalRepository

from .client import RuntimeModelClient, RuntimeProviderError
from .config import RuntimeSettings
from .profiles import RuntimeProfileStore
from .tools import ToolRuntime, ToolRuntimeError

_TOKEN = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")
_COMPARE = re.compile(
    r"^([a-z][a-z0-9_]*)(?:\s*)(==|!=)(?:\s*)('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|true|false|[0-9]+)$"
)


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
    ) -> None:
        self.repository, self.projects, self.library = repository, projects, library
        self.model = model or RuntimeModelClient(RuntimeSettings())
        self.tools = tools or ToolRuntime(ResourceCatalog())
        self.profiles = profiles or RuntimeProfileStore(repository)
        self.repository.interrupt_orphan_runs()

    def status(self) -> dict[str, Any]:
        return self.model.status()

    def components(self) -> dict[str, Any]:
        from veyra_agent_platform.local.components import component_registry

        return {"schema_version": SCHEMA_VERSION, "components": component_registry()}

    def run(
        self,
        project_id: str,
        agent_id: str,
        inputs: dict[str, Any],
        idempotency_key: str,
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
        digest = sha256_digest({"file_hash": fingerprint, "inputs": inputs})
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
            self.repository.remember_response(
                connection,
                scope,
                idempotency_key,
                digest,
                self._row_payload(
                    connection.execute(
                        "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
                    ).fetchone()
                ),
            )
        try:
            outcome = self._execute(
                project_id,
                run_id,
                source,
                inputs,
                self._model_for(project_id, agent_id),
            )
            return self._commit_outcome(
                run_id,
                outcome,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            )
        except RuntimeError as exc:
            return self._fail_run(
                run_id,
                exc,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            )

    def command(
        self,
        project_id: str,
        agent_id: str,
        run_id: str,
        command: str,
        idempotency_key: str,
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
            raise RuntimeError(
                "command_not_applicable",
                "Approval waits must be approved or rejected",
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
        extra_events: list[tuple[str | None, str, dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
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
            self.repository.add_run_events(
                connection, run_id, list(extra_events or [])
            )
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
        with self.repository.transaction() as connection:
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
        now = _now()
        command_id = new_uuid7()
        with self.repository.transaction() as connection:
            self.repository.remember_response(
                connection, scope, idempotency_key, digest, self._row_payload(row)
            )
            self.repository.insert_run_command(
                connection,
                command_id=command_id,
                run_id=row["run_id"],
                command_type="retry",
                payload={},
                status="accepted",
                created_at=now,
            )
        child = self.run(row["project_id"], row["agent_id"], inputs, new_uuid7())
        with self.repository.transaction() as connection:
            self.repository.mark_command_applied(
                connection, command_id, applied_at=_now()
            )
            response = dict(child)
            self.repository.replace_idempotent_response(
                connection, scope, idempotency_key, digest, response
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
        if row["status"] not in {"waiting", "running"}:
            raise RuntimeError(
                "command_not_applicable", "Stop is only available for active runs"
            )
        now = _now()
        command_id = new_uuid7()
        with self.repository.transaction() as connection:
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
        try:
            outcome = self._execute(
                row["project_id"],
                row["run_id"],
                source,
                values,
                self._model_for(row["project_id"], row["agent_id"]),
                start_node=next_node,
                approved=decision == "approved",
            )
            return self._commit_outcome(
                row["run_id"],
                outcome,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            )
        except RuntimeError as exc:
            return self._fail_run(
                row["run_id"],
                exc,
                scope=scope,
                idempotency_key=idempotency_key,
                digest=digest,
            )

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
    def _validate_inputs(source: AgentSource, inputs: dict[str, Any]) -> None:
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
        verifier_passed = False
        events: list[tuple[str | None, str, dict[str, Any]]] = []
        tool_calls: list[_ToolCallRecord] = []

        def emit(node_id: str | None, kind: str, payload: dict[str, Any]) -> None:
            events.append((node_id, kind, payload))
            self._persist_event(run_id, node_id, kind, payload)

        for _ in range(len(nodes) + 1):
            node = nodes[current]
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
                    authorization = self.tools.authorize(
                        source=source, node=node, values=values
                    )
                    emit(
                        node.id,
                        "tool.requested",
                        {
                            "tool_reference": authorization.tool_reference,
                            "input_digest": authorization.input_digest,
                            "permission": authorization.decision,
                            "code": authorization.code,
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
                    execution = self.tools.execute(
                        project_root=Path(project["root_path"]),
                        source=source,
                        node=node,
                        values=values,
                        authorization=authorization,
                        approved=approved,
                    )
                    emit(
                        node.id,
                        "tool.started",
                        {"tool_reference": authorization.tool_reference},
                    )
                    emit(node.id, "tool.completed", execution.receipt)
                    tool_calls[-1] = _ToolCallRecord(
                        node_id=record.node_id,
                        tool_reference=record.tool_reference,
                        authorization=record.authorization,
                        decision_code=record.decision_code,
                        decision_reason=record.decision_reason,
                        input_digest=record.input_digest,
                        receipt=execution.receipt,
                    )
                    values.update(execution.output)
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
                elif node.component_type is ComponentType.AGENT:
                    values.update(self._run_agent(node, source, values, model))
                    port = "next"
                elif node.component_type is ComponentType.HUMAN_APPROVAL:
                    prompt = node.prompt or ""
                    if "{{" in prompt:
                        prompt = _interpolate(prompt, values)
                    emit(node.id, "node.waiting", {"reason": "approval"})
                    emit(node.id, "approval.requested", {"prompt": prompt})
                    emit(
                        node.id, "checkpoint.created", {"waiting_kind": "approval"}
                    )
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
            except (RuntimeProviderError, ToolRuntimeError) as exc:
                runtime_error = RuntimeError(exc.code, str(exc))
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
        source: AgentSource, values: dict[str, Any]
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

    def _run_agent(
        self,
        node: Any,
        source: AgentSource,
        values: dict[str, Any],
        model: RuntimeModelClient,
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
        prompt = node.system_prompt or ""
        if "{{" in prompt:
            prompt = _interpolate(prompt, values)
        completion = model.complete(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": _agent_user_message(source, values)},
            ]
        )
        return _model_output_values(completion.content.strip(), source.outputs, values)

    def _model_for(self, project_id: str, agent_id: str) -> RuntimeModelClient:
        profile, _ = self.profiles.effective(project_id, agent_id)
        if profile is None or self.model.transport is not None:
            return self.model
        settings = self.model.settings.model_copy(
            update={
                "model_base_url": profile.base_url,
                "model_id": profile.model_id,
                "model_api_key_env": profile.api_key_env,
            }
        )
        return RuntimeModelClient(settings)


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
    content: str, outputs: Mapping[str, str], values: dict[str, Any]
) -> dict[str, Any]:
    """Accept only values matching the declared outputs not already populated."""
    targets = [
        (name, field_type) for name, field_type in outputs.items() if name not in values
    ]
    if len(targets) == 1 and targets[0][1] == "string":
        return {targets[0][0]: content}
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
        return {name: parsed}
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
    return parsed


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
