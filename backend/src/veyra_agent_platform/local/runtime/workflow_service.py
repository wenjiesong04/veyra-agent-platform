"""Execute Workflow control flow and pinned Agent calls with durable evidence."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

from veyra_agent_platform.contracts.agent import ComponentType
from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import (
    ContractValidationError,
    IdempotencyKey,
    new_uuid7,
)
from veyra_agent_platform.contracts.typed_io import value_matches_field
from veyra_agent_platform.contracts.workflow import WorkflowSource
from veyra_agent_platform.local.library.workflow_dependencies import (
    resolve_workflow_calls,
)
from veyra_agent_platform.local.projects.service import ProjectError

from .service import (
    RuntimeError,
    RuntimeService,
    _check,
    _condition,
    _interpolate,
    _sse_frame,
    _transform_value,
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

    def readiness(
        self,
        project_id: str,
        workflow_id: str,
        *,
        version_id: str | None = None,
    ) -> dict[str, Any]:
        """Preflight the pinned Agent versions a Workflow would execute.

        This is a no-effect check: it resolves references and inspects each
        immutable child sources and registered Tools, but it does not commit a
        Workflow version, contact the model provider, or start an Agent run.
        """
        self.library._workflow_in_project(project_id, workflow_id)
        source_kind = "draft" if version_id is None else "committed"
        if version_id is None:
            draft = self.library.workflow_draft(project_id, workflow_id)
            source = WorkflowSource.from_dict(draft["source"])
            selected_version_id = None
        else:
            version = self._committed_version(
                project_id, workflow_id, version_id=version_id
            )
            source = WorkflowSource.from_dict(json.loads(version["source_json"]))
            selected_version_id = version["version_id"]
        try:
            calls = resolve_workflow_calls(self.repository, project_id, source)
        except (ContractValidationError, ProjectError) as exc:
            failure = _workflow_readiness_failure(
                project_id,
                workflow_id,
                code=getattr(exc, "code", "workflow_dependency_invalid"),
                detail=str(exc),
            )
            failure.update(
                {
                    "source_kind": source_kind,
                    "version_id": selected_version_id,
                    "source_hash": source.source_hash,
                }
            )
            return failure

        call_reports: list[dict[str, Any]] = []
        setup_issues: list[dict[str, Any]] = []
        permission_gaps: list[dict[str, Any]] = []
        for node in source.nodes:
            if node.component_type is not ComponentType.AGENT_CALL:
                continue
            call = calls[node.id]
            gaps = _permission_gaps(source, call.source)
            permission_gaps.extend({"node_id": node.id, **gap} for gap in gaps)
            child = self.runtime.readiness_for_source(
                project_id, call.agent_id, call.source
            )
            child_setup_issues = [
                {
                    **issue,
                    "scope": f"{node.id}.{issue['scope']}",
                    "node_id": node.id,
                    "agent_id": call.agent_id,
                }
                for issue in child.get("setup_issues") or []
            ]
            setup_issues.extend(child_setup_issues)
            call_reports.append(
                {
                    "node_id": node.id,
                    "agent_id": call.agent_id,
                    "version_id": call.version_id,
                    "source_hash": call.source_hash,
                    "ready": bool(child["ready"]) and not gaps,
                    "detail": (
                        "Pinned Agent Runtime preflight passed."
                        if child["ready"] and not gaps
                        else (
                            "Workflow permissions do not cover the pinned Agent."
                            if gaps
                            else "Pinned Agent Runtime needs attention."
                        )
                    ),
                    "permission_gaps": gaps,
                    "model": child["model"],
                    "dependency_summary": child["dependency_summary"],
                    "checks": child["checks"],
                    "tool_checks": child["tool_checks"],
                    "setup_issues": child_setup_issues,
                }
            )

        _, _, _, _, manifest = self.runtime.projects._project_manifest_state(project_id)
        within_limit = len(source.nodes) <= manifest.resource_policy.max_nodes_per_run
        agents_ready = all(item["ready"] for item in call_reports)
        permissions_ready = not permission_gaps
        tool_reports = self._tool_readiness(source, {})
        tools_ready = all(item["ready"] for item in tool_reports)
        checks = [
            {
                "id": "agent_calls",
                "ready": agents_ready,
                "code": "ready" if agents_ready else "agent_runtime_attention",
                "detail": (
                    "All pinned Agent Runtime preflights passed."
                    if agents_ready
                    else "One or more pinned Agents need Runtime attention."
                ),
            },
            {
                "id": "permissions",
                "ready": permissions_ready,
                "code": "ready" if permissions_ready else "workflow_permission_denied",
                "detail": (
                    "Workflow permissions cover every pinned Agent."
                    if permissions_ready
                    else "Workflow permissions do not cover every pinned Agent."
                ),
            },
            {
                "id": "tools",
                "ready": tools_ready,
                "code": "ready" if tools_ready else "workflow_tool_attention",
                "detail": (
                    "All Workflow Tools are ready and do not require "
                    "unsupported approval."
                    if tools_ready
                    else "One or more Workflow Tools need attention or require "
                    "an unsupported approval gate."
                ),
            },
            {
                "id": "limits",
                "ready": within_limit,
                "code": "ready" if within_limit else "workflow_node_limit",
                "detail": (
                    "Workflow is within the Project execution limit."
                    if within_limit
                    else "Workflow exceeds the Project execution node limit."
                ),
            },
        ]
        return {
            "schema_version": "1.0",
            "project_id": project_id,
            "workflow_id": workflow_id,
            "source_kind": source_kind,
            "version_id": selected_version_id,
            "source_hash": source.source_hash,
            "ready": all(item["ready"] for item in checks),
            "calls": call_reports,
            "setup_issues": setup_issues,
            "tools": tool_reports,
            "checks": checks,
        }

    def run(
        self,
        project_id: str,
        workflow_id: str,
        inputs: dict[str, Any],
        key: str,
        *,
        source: str = "draft",
        version_id: str | None = None,
    ) -> dict[str, Any]:
        IdempotencyKey("1.0", key)
        self.library._workflow_in_project(project_id, workflow_id)
        if source not in {"draft", "committed"}:
            raise RuntimeError("workflow_source_invalid", "Unsupported Workflow source")
        if version_id is not None and source != "committed":
            raise RuntimeError(
                "workflow_version_selection_invalid",
                "version_id requires source='committed'",
            )

        draft: dict[str, Any] | None = None
        committed_version: dict[str, Any] | None = None
        if source == "draft":
            draft = self.library.workflow_draft(project_id, workflow_id)
            workflow_source = WorkflowSource.from_dict(draft["source"])
        else:
            committed_version = self._committed_version(
                project_id, workflow_id, version_id=version_id
            )
            workflow_source = WorkflowSource.from_dict(
                json.loads(committed_version["source_json"])
            )
        prepared_inputs = self.runtime._prepare_inputs(
            project_id, workflow_source, inputs
        )
        calls = resolve_workflow_calls(self.repository, project_id, workflow_source)
        for call in calls.values():
            gaps = _permission_gaps(workflow_source, call.source)
            if gaps:
                raise RuntimeError(
                    "workflow_permission_denied",
                    "Workflow must explicitly allow the called Agent's "
                    + ", ".join(item["field"] for item in gaps),
                )
            child_readiness = self.runtime.readiness_for_source(
                project_id, call.agent_id, call.source
            )
            setup_issues = child_readiness.get("setup_issues") or []
            if setup_issues:
                first = setup_issues[0]
                raise RuntimeError(first["code"], first["message"])
        for report in self._tool_readiness(workflow_source, prepared_inputs):
            if not report["ready"]:
                raise RuntimeError(report["code"], report["detail"])
        _, _, _, _, manifest = self.runtime.projects._project_manifest_state(project_id)
        policy = manifest.resource_policy
        if len(workflow_source.nodes) > policy.max_nodes_per_run:
            raise RuntimeError(
                "workflow_node_limit", "Workflow exceeds the Project node limit"
            )
        request_digest = sha256_digest(
            {"source_hash": workflow_source.source_hash, "inputs": prepared_inputs}
        )
        if committed_version is not None:
            request_digest = sha256_digest(
                {
                    "source": source,
                    "version_id": committed_version["version_id"],
                    "source_hash": workflow_source.source_hash,
                    "inputs": prepared_inputs,
                }
            )
        scope = f"workflow-run:{project_id}:{workflow_id}"
        with self._commands:
            with self.repository.transaction() as connection:
                previous = self.repository.idempotent_response(
                    connection, scope, key, request_digest
                )
            if previous is not None:
                return self.detail(project_id, workflow_id, previous["run_id"])
            if source == "draft":
                assert draft is not None
                version = self.library.snapshot_workflow_draft(
                    project_id=project_id,
                    workflow_id=workflow_id,
                    expected_revision=draft["revision"],
                    expected_etag=draft["etag"],
                )
            else:
                assert committed_version is not None
                version = committed_version
            run_id = new_uuid7()
            first = next(
                node.id
                for node in workflow_source.nodes
                if node.component_type is ComponentType.START
            )
            context = {
                "node_id": first,
                "values": prepared_inputs,
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
                    connection, scope, key, request_digest, {"run_id": run_id}
                )
            started = self.store.detail(run_id)
            self._schedule(run_id)
            return started

    def _committed_version(
        self,
        project_id: str,
        workflow_id: str,
        *,
        version_id: str | None,
    ) -> dict[str, Any]:
        try:
            version = self.library.workflow_version_snapshot(
                project_id,
                workflow_id,
                version_id,
                committed_only=True,
            )
        except ProjectError as exc:
            raise RuntimeError(exc.code, str(exc)) from exc
        if version is None:
            code = (
                "workflow_has_no_committed_version"
                if version_id is None
                else "workflow_version_not_found"
            )
            raise RuntimeError(
                code,
                "Workflow has no committed version"
                if version_id is None
                else "Committed Workflow version not found",
            )
        return version

    def _tool_readiness(
        self, source: WorkflowSource, values: dict[str, Any]
    ) -> list[dict[str, Any]]:
        host = _workflow_tool_host(source)
        reports: list[dict[str, Any]] = []
        for node in source.nodes:
            if node.component_type is not ComponentType.TOOL:
                continue
            mapped = {
                name: values.get(source_name)
                for name, source_name in (node.input_mapping or {}).items()
            }
            if not mapped.get("entity_type"):
                mapped["entity_type"] = values.get("entity_type") or "ProjectEntity"
            if not mapped.get("status"):
                mapped["status"] = values.get("status") or "active"
            if mapped.get("payload") is None:
                mapped["payload"] = values.get("result") or dict(values)
            if not mapped.get("entity_id") and values.get("entity_id"):
                mapped["entity_id"] = values["entity_id"]
            authorization = self.runtime.tools.authorize(
                source=host,  # type: ignore[arg-type]
                node=node,
                values=mapped,
            )
            if authorization.decision != "allowed":
                ready = False
                code = authorization.code
                detail = authorization.reason
            elif authorization.approval_required:
                ready = False
                code = "workflow_tool_approval_not_supported"
                detail = (
                    "This Workflow Tool requires approval, but no verified "
                    "Tool approval gate is available for Workflow execution."
                )
            else:
                ready = True
                code = "ready"
                detail = "Workflow Tool is ready for execution."
            reports.append(
                {
                    "node_id": node.id,
                    "tool_reference": node.uses,
                    "ready": ready,
                    "code": code,
                    "detail": detail,
                    "approval_required": authorization.approval_required,
                }
            )
        return reports

    def _source(
        self, version_id: str, project_id: str, workflow_id: str
    ) -> WorkflowSource:
        try:
            version = self.library.workflow_version_snapshot(
                project_id,
                workflow_id,
                version_id,
                committed_only=False,
            )
        except ProjectError as exc:
            raise RuntimeError(exc.code, str(exc)) from exc
        if version is None:
            raise RuntimeError(
                "workflow_version_not_found", "Workflow version not found"
            )
        return WorkflowSource.from_dict(json.loads(version["source_json"]))

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
            source = self._source(
                row["version_id"], row["project_id"], row["workflow_id"]
            )
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
                            name: _transform_value(value, values)
                            for name, value in (node.mapping or {}).items()
                        }
                    )
                elif node.component_type is ComponentType.CONDITION:
                    port = (
                        "true" if _condition(node.expression or "", values) else "false"
                    )
                elif node.component_type is ComponentType.VERIFIER:
                    outputs = self.runtime._prepare_outputs(
                        row["project_id"], source, values
                    )
                    passed = all(
                        _check(
                            check,
                            values if check.startswith("artifact_exists:") else outputs,
                        )
                        for check in (node.checks or ())
                    )
                    context["verified"] = passed
                    port = "passed" if passed else "failed"
                    with self.repository.transaction() as connection:
                        self.store.event(
                            connection,
                            run_id,
                            current,
                            "verifier.result",
                            {"passed": passed},
                        )
                elif node.component_type is ComponentType.HUMAN_APPROVAL:
                    kind = "input" if node.review == "input" else "approval"
                    expected = list((node.inputs or {}).keys())
                    context["waiting"] = {
                        "kind": kind,
                        "node_id": current,
                        "prompt": _interpolate(node.prompt or "", values),
                        "expected_fields": expected,
                    }
                    self._checkpoint(run_id, context, "waiting")
                    return
                elif node.component_type is ComponentType.TOOL:
                    mapped = {
                        name: values.get(source_name)
                        for name, source_name in (node.input_mapping or {}).items()
                    }
                    if "entity_type" not in mapped or not mapped.get("entity_type"):
                        mapped["entity_type"] = (
                            values.get("entity_type") or "ProjectEntity"
                        )
                    if "status" not in mapped or not mapped.get("status"):
                        mapped["status"] = values.get("status") or "active"
                    if "payload" not in mapped or mapped.get("payload") is None:
                        mapped["payload"] = values.get("result") or dict(values)
                    # Mapping keys must be hyphenated slugs, so entity_id can
                    # only reach entity tools through this default.
                    if not mapped.get("entity_id") and values.get("entity_id"):
                        mapped["entity_id"] = values["entity_id"]
                    host = _workflow_tool_host(source)
                    authorization = self.runtime.tools.authorize(
                        source=host,  # type: ignore[arg-type]
                        node=node,
                        values=mapped,
                    )
                    if authorization.decision != "allowed":
                        raise RuntimeError(authorization.code, authorization.reason)
                    if authorization.approval_required:
                        raise RuntimeError(
                            "workflow_tool_approval_not_supported",
                            "Workflow Tool approval is required, but no verified "
                            "Tool approval gate is available for Workflow execution",
                        )
                    project = self.runtime.repository.project(row["project_id"])
                    if project is None:
                        raise RuntimeError("project_invalid", "Project is unavailable")
                    execution = self.runtime.tools.execute(
                        project_root=self.runtime.projects._existing_root(
                            project["root_path"]
                        ),
                        source=host,  # type: ignore[arg-type]
                        node=node,
                        values=mapped,
                        authorization=authorization,
                        approved=False,
                        project_id=row["project_id"],
                    )
                    values.update(
                        {
                            target: execution.output.get(name)
                            for name, target in (node.output_mapping or {}).items()
                        }
                    )
                    if not node.output_mapping:
                        values.update(
                            {
                                key: value
                                for key, value in execution.output.items()
                                if isinstance(key, str)
                            }
                        )
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
                    result = self.runtime._prepare_outputs(
                        row["project_id"], source, values
                    )
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
        self,
        project_id: str,
        workflow_id: str,
        run_id: str,
        command: str,
        key: str,
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        IdempotencyKey("1.0", key)
        if command not in {"approve", "reject", "stop", "reply"}:
            raise RuntimeError(
                "command_invalid",
                "Workflow supports approve, reject, reply, and stop",
            )
        scope = f"workflow-command:{run_id}"
        digest = sha256_digest({"command": command, "inputs": inputs or {}})
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
                        "command_not_applicable",
                        "Workflow is not waiting for approval or input",
                    )
                if command == "reply":
                    if waiting.get("kind") != "input":
                        raise RuntimeError(
                            "command_not_applicable",
                            "Reply is only valid while waiting for human input",
                        )
                    source = self._source(row["version_id"], project_id, workflow_id)
                    node = next(
                        item for item in source.nodes if item.id == waiting["node_id"]
                    )
                    fields = node.inputs or {}
                    reply = inputs or {}
                    if set(reply) - set(fields) or any(
                        field.required and name not in reply
                        for name, field in fields.items()
                    ):
                        raise RuntimeError(
                            "inputs_invalid", "Reply must match the requested fields"
                        )
                    for name, value in reply.items():
                        if not value_matches_field(fields[name], value) or (
                            fields[name].required
                            and isinstance(value, str)
                            and not value.strip()
                        ):
                            raise RuntimeError(
                                "inputs_invalid",
                                f"Reply field {name} has an invalid value",
                            )
                    typed = self.runtime._bind_typed_values(
                        project_id, fields, reply, "inputs_invalid"
                    )
                    context.setdefault("values", {}).update(typed)
                    port = "approved"
                elif waiting["kind"] == "input":
                    raise RuntimeError(
                        "command_not_applicable",
                        "Use reply to provide the requested inputs",
                    )
                elif waiting["kind"] == "agent":
                    self.runtime.command(
                        project_id,
                        waiting["agent_id"],
                        waiting["child_run_id"],
                        command,
                        key,
                    )
                    port = None
                else:
                    port = "approved" if command == "approve" else "rejected"
                if port is not None:
                    source = self._source(
                        row["version_id"], row["project_id"], row["workflow_id"]
                    )
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


def _permission_gaps(parent: WorkflowSource, child: Any) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for field in (
        "tools",
        "network_hosts",
        "filesystem_read_roots",
        "filesystem_write_roots",
    ):
        missing = sorted(
            set(getattr(child.permissions, field))
            - set(getattr(parent.permissions, field))
        )
        if missing:
            gaps.append({"field": field, "missing": missing})
    if (
        child.permissions.shell_workspace_only
        and not parent.permissions.shell_workspace_only
    ):
        gaps.append({"field": "shell_workspace_only", "missing": [True]})
    return gaps


def _workflow_readiness_failure(
    project_id: str, workflow_id: str, *, code: str, detail: str
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "workflow_id": workflow_id,
        "ready": False,
        "calls": [],
        "tools": [],
        "checks": [
            {
                "id": "agent_calls",
                "ready": False,
                "code": code,
                "detail": detail,
            },
            {
                "id": "permissions",
                "ready": False,
                "code": "workflow_dependency_invalid",
                "detail": (
                    "Workflow permissions cannot be evaluated until Agent "
                    "references resolve."
                ),
            },
            {
                "id": "tools",
                "ready": False,
                "code": "not_checked",
                "detail": (
                    "Tool readiness was not reached because Workflow "
                    "references are invalid."
                ),
            },
            {
                "id": "limits",
                "ready": True,
                "code": "not_checked",
                "detail": "Execution limit check was not reached.",
            },
        ],
    }


def _workflow_tool_host(source: WorkflowSource) -> SimpleNamespace:
    return SimpleNamespace(
        lock=source.lock,
        permissions=source.permissions,
        secret_refs=(),
    )
