"""Execute Workflow control flow and pinned Agent calls with durable evidence."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from typing import Any

from veyra_agent_platform.contracts.agent import ComponentType
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import IdempotencyKey, new_uuid7
from veyra_agent_platform.contracts.workflow import WorkflowSource
from veyra_agent_platform.local.library.workflow_dependencies import (
    resolve_workflow_calls,
)

from .service import (
    RuntimeError,
    RuntimeService,
    _check,
    _condition,
    _interpolate,
    _sse_frame,
)
from .workflow_store import WorkflowRunStore, utc_now


class WorkflowRuntimeService:
    def __init__(self, runtime: RuntimeService) -> None:
        self.runtime = runtime
        self.repository = runtime.repository
        self.library = runtime.library
        self.store = WorkflowRunStore(self.repository)
        self._commands = threading.RLock()
        self.store.interrupt_orphans()

    def detail(self, project_id: str, workflow_id: str, run_id: str) -> dict[str, Any]:
        self.library._workflow_in_project(project_id, workflow_id)
        row = self.store.row(run_id)
        if (
            row is None
            or row["project_id"] != project_id
            or row["workflow_id"] != workflow_id
        ):
            raise RuntimeError("workflow_run_not_found", "Workflow run not found")
        return self.store.detail(run_id)

    def runs(self, project_id: str, workflow_id: str) -> dict[str, Any]:
        self.library._workflow_in_project(project_id, workflow_id)
        with self.repository._connect() as connection:
            ids = [
                row[0]
                for row in connection.execute(
                    "SELECT run_id FROM workflow_runs WHERE workflow_id = ? "
                    "ORDER BY created_at DESC",
                    (workflow_id,),
                )
            ]
        return {
            "schema_version": "1.0",
            "runs": [self.store.detail(run_id) for run_id in ids],
        }

    def run(
        self, project_id: str, workflow_id: str, inputs: dict[str, Any], key: str
    ) -> dict[str, Any]:
        IdempotencyKey("1.0", key)
        draft = self.library.workflow_draft(project_id, workflow_id)
        source = WorkflowSource.from_dict(draft["source"])
        self.runtime._validate_inputs(source, inputs)
        calls = resolve_workflow_calls(self.repository, project_id, source)
        for call in calls.values():
            for permission in (
                "tools",
                "network_hosts",
                "filesystem_read_roots",
                "filesystem_write_roots",
            ):
                if not set(getattr(call.source.permissions, permission)).issubset(
                    set(getattr(source.permissions, permission))
                ):
                    raise RuntimeError(
                        "workflow_permission_denied",
                        "Workflow must explicitly allow the called Agent's "
                        f"{permission}",
                    )
        _, _, _, _, manifest = self.runtime.projects._project_manifest_state(project_id)
        policy = manifest.resource_policy
        if len(source.nodes) > policy.max_nodes_per_run:
            raise RuntimeError(
                "workflow_node_limit", "Workflow exceeds the Project node limit"
            )
        digest = sha256_digest({"source_hash": source.source_hash, "inputs": inputs})
        scope = f"workflow-run:{project_id}:{workflow_id}"
        with self._commands:
            with self.repository.transaction() as connection:
                previous = self.repository.idempotent_response(
                    connection, scope, key, digest
                )
            if previous is not None:
                return self.detail(project_id, workflow_id, previous["run_id"])
            version = self.library.commit_workflow(
                project_id=project_id,
                workflow_id=workflow_id,
                expected_revision=draft["revision"],
                expected_etag=draft["etag"],
                idempotency_key=new_uuid7(),
            )
            run_id = new_uuid7()
            first = next(
                node.id
                for node in source.nodes
                if node.component_type is ComponentType.START
            )
            context = {
                "node_id": first,
                "values": inputs,
                "verified": False,
                "waiting": None,
                "deadline": time.time() + policy.max_run_seconds,
                "remaining_seconds": policy.max_run_seconds,
            }
            with self.repository.transaction() as connection:
                active = connection.execute(
                    "SELECT COUNT(*) FROM workflow_runs WHERE project_id = ? "
                    "AND status IN ('running', 'waiting')",
                    (project_id,),
                ).fetchone()[0]
                if active >= policy.max_concurrent_runs:
                    raise RuntimeError(
                        "workflow_concurrency_limit",
                        "Project Workflow concurrency limit reached",
                    )
                connection.execute(
                    "INSERT INTO workflow_runs(run_id, project_id, workflow_id, "
                    "version_id, status, context_json, created_at) VALUES (?, ?, "
                    "?, ?, 'running', ?, ?)",
                    (
                        run_id,
                        project_id,
                        workflow_id,
                        version["version_id"],
                        json.dumps(context),
                        utc_now(),
                    ),
                )
                self.store.event(connection, run_id, None, "run.created", {})
                self.store.event(connection, run_id, None, "run.started", {})
                self.repository.remember_response(
                    connection, scope, key, digest, {"run_id": run_id}
                )
            started = self.store.detail(run_id)
            self._schedule(run_id)
            return started

    def _source(self, version_id: str) -> WorkflowSource:
        version = self.repository.workflow_version(version_id)
        if version is None:
            raise RuntimeError(
                "workflow_version_not_found", "Workflow version not found"
            )
        source = WorkflowSource.from_dict(json.loads(version["source_json"]))
        if source.source_hash != version["source_hash"]:
            raise RuntimeError(
                "workflow_version_invalid", "Workflow snapshot hash mismatch"
            )
        return source

    def _schedule(self, run_id: str) -> None:
        threading.Thread(
            target=self._execute,
            args=(run_id,),
            daemon=True,
            name=f"veyra-workflow-{run_id[:8]}",
        ).start()

    def _running(self, run_id: str) -> bool:
        row = self.store.row(run_id)
        return row is not None and row["status"] == "running"

    def _checkpoint(
        self, run_id: str, context: dict[str, Any], status: str = "running"
    ) -> bool:
        if status == "waiting":
            context["remaining_seconds"] = max(0, context["deadline"] - time.time())
        with self.repository.transaction() as connection:
            updated = connection.execute(
                "UPDATE workflow_runs SET context_json = ?, status = ? WHERE "
                "run_id = ? AND status = 'running'",
                (json.dumps(context), status, run_id),
            )
            if updated.rowcount and status == "waiting":
                self.store.event(
                    connection,
                    run_id,
                    context["node_id"],
                    "node.waiting",
                    context["waiting"],
                )
            return bool(updated.rowcount)

    def _finish(
        self,
        run_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: dict[str, str] | None = None,
    ) -> None:
        with self.repository.transaction() as connection:
            changed = connection.execute(
                "UPDATE workflow_runs SET status = ?, result_json = ?, "
                "error_json = ?, finished_at = ? WHERE run_id = ? AND status "
                "= 'running'",
                (
                    status,
                    json.dumps(result) if result is not None else None,
                    json.dumps(error) if error else None,
                    utc_now(),
                    run_id,
                ),
            )
            if changed.rowcount:
                self.store.event(
                    connection,
                    run_id,
                    None,
                    "run.failed" if error else "run.completed",
                    {"status": status, **(error or {})},
                )

    def _execute(self, run_id: str) -> None:
        current: str | None = None
        try:
            row = self.store.row(run_id)
            source = self._source(row["version_id"])
            calls = resolve_workflow_calls(self.repository, row["project_id"], source)
            context = json.loads(row["context_json"])
            nodes = {node.id: node for node in source.nodes}
            edges = {
                (edge.from_node, edge.port.value): edge.to_node
                for edge in source.transitions
            }
            for _ in range(len(nodes) + 1):
                if not self._running(run_id):
                    return
                if time.time() >= context["deadline"]:
                    raise RuntimeError(
                        "workflow_timeout",
                        "Workflow exceeded its execution time budget",
                    )
                current = context["node_id"]
                node = nodes[current]
                values = context["values"]
                with self.repository.transaction() as connection:
                    self.store.event(
                        connection,
                        run_id,
                        current,
                        "node.started",
                        {"component_type": node.component_type.value},
                    )
                port = "next"
                if node.component_type is ComponentType.START:
                    pass
                elif node.component_type is ComponentType.TRANSFORM:
                    values.update(
                        {
                            name: _interpolate(value, values)
                            for name, value in (node.mapping or {}).items()
                        }
                    )
                elif node.component_type is ComponentType.CONDITION:
                    port = (
                        "true" if _condition(node.expression or "", values) else "false"
                    )
                elif node.component_type is ComponentType.VERIFIER:
                    passed = all(_check(check, values) for check in (node.checks or ()))
                    context["verified"] = passed
                    port = "passed" if passed else "failed"
                elif node.component_type is ComponentType.HUMAN_APPROVAL:
                    context["waiting"] = {
                        "kind": "approval",
                        "node_id": current,
                        "prompt": _interpolate(node.prompt or "", values),
                    }
                    self._checkpoint(run_id, context, "waiting")
                    return
                elif node.component_type is ComponentType.AGENT_CALL:
                    call = calls[current]
                    inputs = {
                        name: values[value]
                        for name, value in (node.input_mapping or {}).items()
                    }
                    child = self._child(
                        run_id,
                        current,
                        row["project_id"],
                        call.agent_id,
                        call.version_id,
                        inputs,
                    )
                    while child["status"] == "running" and self._running(run_id):
                        if time.time() >= context["deadline"]:
                            self.runtime.command(
                                row["project_id"],
                                call.agent_id,
                                child["run_id"],
                                "stop",
                                new_uuid7(),
                            )
                            raise RuntimeError(
                                "workflow_timeout",
                                "Workflow exceeded its execution time budget",
                            )
                        time.sleep(0.04)
                        child = self.runtime.run_detail(
                            row["project_id"], call.agent_id, child["run_id"]
                        )
                    if not self._running(run_id):
                        if child["status"] in {"running", "waiting"}:
                            self.runtime.command(
                                row["project_id"],
                                call.agent_id,
                                child["run_id"],
                                "stop",
                                new_uuid7(),
                            )
                        return
                    if child["status"] == "waiting":
                        context["waiting"] = {
                            "kind": "agent",
                            "node_id": current,
                            "agent_id": call.agent_id,
                            "child_run_id": child["run_id"],
                            "prompt": "Agent requires approval",
                        }
                        self._checkpoint(run_id, context, "waiting")
                        return
                    if child["status"] not in {"verified", "unverified"}:
                        raise RuntimeError(
                            "workflow_agent_failed",
                            f"AgentCall {current} ended as {child['status']}",
                        )
                    values.update(
                        {
                            target: child["result"][name]
                            for name, target in (node.output_mapping or {}).items()
                        }
                    )
                elif node.component_type is ComponentType.OUTPUT:
                    result = self.runtime._validated_outputs(source, values)
                    with self.repository.transaction() as connection:
                        self.store.event(
                            connection, run_id, current, "node.completed", {}
                        )
                    self._finish(
                        run_id,
                        "verified" if context["verified"] else "unverified",
                        result,
                    )
                    return
                else:
                    raise RuntimeError(
                        "runtime_not_supported", "Unsupported Workflow node"
                    )
                with self.repository.transaction() as connection:
                    self.store.event(
                        connection, run_id, current, "node.completed", {"port": port}
                    )
                context.update(node_id=edges[(current, port)], waiting=None)
                if not self._checkpoint(run_id, context):
                    return
            raise RuntimeError(
                "workflow_execution_limit", "Workflow exceeded its graph bound"
            )
        except Exception as exc:
            code = (
                exc.code
                if isinstance(exc, RuntimeError)
                else "workflow_execution_failed"
            )
            message = (
                str(exc)
                if isinstance(exc, RuntimeError)
                else "Workflow execution failed"
            )
            with self.repository.transaction() as connection:
                if self._running(run_id):
                    self.store.event(
                        connection, run_id, current, "node.failed", {"code": code}
                    )
            self._finish(run_id, "failed", error={"code": code, "message": message})

    def _child(
        self,
        run_id: str,
        node_id: str,
        project_id: str,
        agent_id: str,
        version_id: str,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        with self.repository.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO workflow_run_calls(run_id, node_id, "
                "agent_id, version_id, dispatch_key) VALUES (?, ?, ?, ?, ?)",
                (run_id, node_id, agent_id, version_id, new_uuid7()),
            )
            row = connection.execute(
                "SELECT * FROM workflow_run_calls WHERE run_id = ? AND node_id = ?",
                (run_id, node_id),
            ).fetchone()
        if row["child_run_id"]:
            return self.runtime.run_detail(project_id, agent_id, row["child_run_id"])
        if not self._running(run_id):
            raise RuntimeError("workflow_cancelled", "Workflow was cancelled")
        child = self.runtime.run_version(
            project_id, agent_id, version_id, inputs, row["dispatch_key"]
        )
        with self.repository.transaction() as connection:
            connection.execute(
                "UPDATE workflow_run_calls SET child_run_id = ? WHERE run_id "
                "= ? AND node_id = ?",
                (child["run_id"], run_id, node_id),
            )
        return child

    def command(
        self, project_id: str, workflow_id: str, run_id: str, command: str, key: str
    ) -> dict[str, Any]:
        IdempotencyKey("1.0", key)
        if command not in {"approve", "reject", "stop"}:
            raise RuntimeError(
                "command_invalid", "Workflow supports approve, reject, and stop"
            )
        scope = f"workflow-command:{run_id}"
        digest = sha256_digest({"command": command})
        with self._commands:
            self.detail(project_id, workflow_id, run_id)
            with self.repository.transaction() as connection:
                replay = self.repository.idempotent_response(
                    connection, scope, key, digest
                )
            if replay is not None:
                return self.store.detail(run_id)
            row = self.store.row(run_id)
            context = json.loads(row["context_json"])
            if command == "stop":
                with self.repository.transaction() as connection:
                    changed = connection.execute(
                        "UPDATE workflow_runs SET status = 'cancelled', finished_at "
                        "= ? WHERE run_id = ? AND status IN ('running', 'waiting')",
                        (utc_now(), run_id),
                    )
                    if not changed.rowcount:
                        raise RuntimeError(
                            "command_not_applicable", "Workflow is already terminal"
                        )
                    self.store.event(connection, run_id, None, "run.cancelled", {})
                for child in self.store.calls(run_id):
                    if child["status"] in {"running", "waiting"}:
                        self.runtime.command(
                            project_id,
                            child["agent_id"],
                            child["child_run_id"],
                            "stop",
                            new_uuid7(),
                        )
            else:
                waiting = context.get("waiting")
                if row["status"] != "waiting" or not waiting:
                    raise RuntimeError(
                        "command_not_applicable", "Workflow is not waiting for approval"
                    )
                if waiting["kind"] == "agent":
                    self.runtime.command(
                        project_id,
                        waiting["agent_id"],
                        waiting["child_run_id"],
                        command,
                        key,
                    )
                else:
                    source = self._source(row["version_id"])
                    port = "approved" if command == "approve" else "rejected"
                    context["node_id"] = next(
                        edge.to_node
                        for edge in source.transitions
                        if edge.from_node == waiting["node_id"]
                        and edge.port.value == port
                    )
                context["waiting"] = None
                context["deadline"] = time.time() + context["remaining_seconds"]
                with self.repository.transaction() as connection:
                    connection.execute(
                        "UPDATE workflow_runs SET status = 'running', context_json = "
                        "? WHERE run_id = ? AND status = 'waiting'",
                        (json.dumps(context), run_id),
                    )
                    self.store.event(
                        connection,
                        run_id,
                        waiting["node_id"],
                        "approval.resolved",
                        {"decision": command},
                    )
                self._schedule(run_id)
            with self.repository.transaction() as connection:
                self.repository.remember_response(
                    connection, scope, key, digest, {"run_id": run_id}
                )
            return self.store.detail(run_id)

    def follow_events(self, run_id: str, after: int) -> Iterator[str]:
        sequence = after
        while True:
            events = self.store.events(run_id, sequence)
            for event in events:
                sequence = event["sequence"]
                yield _sse_frame("runtime", event, str(sequence))
            row = self.store.row(run_id)
            if row["status"] not in {"running", "waiting"} and not events:
                yield _sse_frame("done", {"status": row["status"]})
                return
            if not events:
                time.sleep(0.05)
