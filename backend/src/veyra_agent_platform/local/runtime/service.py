"""Closed, deterministic executor for the initial V1 flow components."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
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
from veyra_agent_platform.local.storage.repositories import LocalRepository

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


class RuntimeService:
    def __init__(
        self,
        repository: LocalRepository,
        projects: ProjectService,
        library: LibraryService,
    ) -> None:
        self.repository, self.projects, self.library = repository, projects, library
        self.repository.interrupt_orphan_runs()

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
            result, events, verified = self._execute(source, inputs)
            with self.repository.transaction() as connection:
                self.repository.add_run_events(connection, run_id, events)
                final_status = "verified" if verified else "unverified"
                self.repository.add_run_events(
                    connection,
                    run_id,
                    [(None, "run.completed", {"state": final_status})],
                )
                self.repository.finish_run(
                    connection,
                    run_id,
                    status=final_status,
                    result=result,
                    code=None,
                    message=None,
                    finished_at=_now(),
                )
                response = self._row_payload(
                    connection.execute(
                        "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
                    ).fetchone()
                )
                self.repository.replace_idempotent_response(
                    connection, scope, idempotency_key, digest, response
                )
                return response
        except RuntimeError as exc:
            with self.repository.transaction() as connection:
                self.repository.add_run_events(
                    connection,
                    run_id,
                    exc.events + [(None, "run.failed", {"code": exc.code})],
                )
                self.repository.finish_run(
                    connection,
                    run_id,
                    status="failed",
                    result=None,
                    code=exc.code,
                    message=str(exc),
                    finished_at=_now(),
                )
                response = self._row_payload(
                    connection.execute(
                        "SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,)
                    ).fetchone()
                )
                self.repository.replace_idempotent_response(
                    connection, scope, idempotency_key, digest, response
                )
                return response

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
        }
        for field, field_type in source.inputs.items():
            validator = validators.get(field_type)
            if validator is None or not validator(inputs[field]):
                raise RuntimeError(
                    "inputs_invalid", f"input {field} must be a {field_type}"
                )

    def _execute(
        self, source: AgentSource, inputs: dict[str, Any]
    ) -> tuple[dict[str, Any], list[tuple[str | None, str, dict[str, Any]]], bool]:
        nodes = {node.id: node for node in source.nodes}
        edges = {
            (edge.from_node, edge.port.value): edge.to_node
            for edge in source.transitions
        }
        current = next(
            node.id
            for node in source.nodes
            if node.component_type is ComponentType.START
        )
        values = dict(inputs)
        result: dict[str, Any] = {}
        verifier_passed = False
        events: list[tuple[str | None, str, dict[str, Any]]] = []
        for _ in range(len(nodes) + 1):
            node = nodes[current]
            events.append(
                (node.id, "node.started", {"component_type": node.component_type.value})
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
                    events.append(
                        (node.id, "verifier.result", {"passed": verifier_passed})
                    )
                elif node.component_type is ComponentType.OUTPUT:
                    assert node.output_name is not None
                    result = self._validated_outputs(source, values)
                    events.append((node.id, "node.completed", {}))
                    return result, events, verifier_passed
                elif node.component_type in {
                    ComponentType.TOOL,
                    ComponentType.HUMAN_APPROVAL,
                }:
                    raise RuntimeError(
                        "runtime_not_supported",
                        f"{node.component_type.value} is not supported by "
                        "this local Runtime",
                    )
                else:
                    raise RuntimeError(
                        "runtime_not_supported",
                        "Agent nodes require a configured provider",
                    )
            except RuntimeError as exc:
                events.append((node.id, "node.failed", {"code": exc.code}))
                exc.events = events
                raise
            except Exception:
                runtime_error = RuntimeError(
                    "executor_failed", "local Runtime execution failed"
                )
                events.append((node.id, "node.failed", {"code": runtime_error.code}))
                runtime_error.events = events
                raise runtime_error from None
            events.append((node.id, "node.completed", {"port": port}))
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
