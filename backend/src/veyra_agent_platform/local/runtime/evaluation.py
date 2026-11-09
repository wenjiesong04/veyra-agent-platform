"""Offline checks over persisted results; no model, Tool or continuation access."""

from __future__ import annotations

import json
from collections.abc import Hashable, Mapping
from typing import Any

from veyra_agent_platform.contracts.agent import AgentSource
from veyra_agent_platform.contracts.canonical import canonical_json, sha256_digest
from veyra_agent_platform.contracts.common import IdempotencyKey, new_uuid7, thaw_json
from veyra_agent_platform.contracts.condition import resolve_value_path
from veyra_agent_platform.contracts.evaluation import (
    EvaluationCheck,
    EvaluationSpec,
    exact_decimal,
)
from veyra_agent_platform.contracts.typed_io import value_matches_field
from veyra_agent_platform.contracts.workflow import WorkflowSource
from veyra_agent_platform.local.artifacts import ArtifactService
from veyra_agent_platform.local.library.service import LibraryService
from veyra_agent_platform.local.projects.service import ProjectError
from veyra_agent_platform.local.storage.repositories import LocalRepository

from .workflow_store import WorkflowRunStore, utc_now


def _equal(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) != isinstance(expected, bool):
        return False
    if isinstance(actual, int | float) and isinstance(expected, int | float):
        return exact_decimal(actual) == exact_decimal(expected)
    if isinstance(actual, Mapping) and isinstance(expected, Mapping):
        return actual.keys() == expected.keys() and all(
            _equal(actual[key], expected[key]) for key in actual
        )
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _equal(left, right) for left, right in zip(actual, expected, strict=True)
        )
    return type(actual) is type(expected) and actual == expected


def _value_key(value: Any) -> Hashable:
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, int | float):
        return ("number", exact_decimal(value))
    if isinstance(value, Mapping):
        return (
            "object",
            tuple(sorted((key, _value_key(item)) for key, item in value.items())),
        )
    if isinstance(value, list):
        return ("array", tuple(_value_key(item) for item in value))
    return (type(value).__name__, value)


def _same_set(actual: Any, expected: list[Any]) -> bool:
    if not isinstance(actual, list):
        return False
    return {_value_key(item) for item in actual} == {
        _value_key(item) for item in expected
    }


def evaluation_decision(findings: list[dict[str, Any]], output_contract: str) -> str:
    required = [finding for finding in findings if finding["required"]]
    if output_contract == "fail" or any(item["status"] == "fail" for item in required):
        return "rejected"
    if (
        required
        and output_contract == "pass"
        and all(item["status"] == "pass" for item in required)
    ):
        return "accepted"
    return "inconclusive"


class RunEvaluationService:
    def __init__(
        self,
        repository: LocalRepository,
        library: LibraryService,
        artifacts: ArtifactService,
    ) -> None:
        self.repository = repository
        self.library = library
        self.artifacts = artifacts
        self.workflows = WorkflowRunStore(repository)

    def _row(self, project_id: str, kind: str, target_id: str, run_id: str) -> Any:
        if kind == "agent":
            self.library._agent_in_project(project_id, target_id)
            row = self.repository.run(run_id)
        elif kind == "workflow":
            self.library._workflow_in_project(project_id, target_id)
            row = self.workflows.row(run_id)
        else:
            raise ProjectError(
                "Unsupported evaluation target", "evaluation_target_invalid"
            )
        if (
            row is None
            or row["project_id"] != project_id
            or row[f"{kind}_id"] != target_id
        ):
            raise ProjectError(
                "Evaluation Run was not found", "evaluation_run_not_found"
            )
        return row

    def reports(
        self, project_id: str, kind: str, target_id: str, run_id: str
    ) -> dict[str, Any]:
        self._row(project_id, kind, target_id, run_id)
        events = (
            self.repository.run_events(run_id)
            if kind == "agent"
            else self.workflows.events(run_id)
        )
        return {
            "schema_version": "1.0",
            "reports": [
                event["payload"]
                for event in reversed(events)
                if event["kind"] in {"evaluation.completed", "evaluation.reviewed"}
            ],
        }

    def evaluate(
        self,
        project_id: str,
        kind: str,
        target_id: str,
        run_id: str,
        value: dict[str, Any],
        key: str,
    ) -> dict[str, Any]:
        IdempotencyKey("1.0", key)
        spec = EvaluationSpec.from_dict(value)
        row = self._row(project_id, kind, target_id, run_id)
        if row["version_id"] != spec.version_id:
            raise ProjectError(
                "Evaluation version does not match the Run",
                "evaluation_version_mismatch",
            )
        if row["status"] not in {
            "verified",
            "unverified",
            "failed",
            "interrupted",
            "cancelled",
        }:
            raise ProjectError(
                "Wait for the Run to finish before evaluating", "evaluation_run_active"
            )
        scope = f"run-evaluation:{kind}:{run_id}"
        spec_data = spec.to_dict()
        digest = sha256_digest(spec_data)
        # A replay returns the original snapshot, even if an artifact later changes.
        with self.repository.transaction() as connection:
            previous = self.repository.idempotent_response(
                connection, scope, key, digest
            )
            if previous is not None:
                return previous
        report = self._assess(project_id, kind, target_id, run_id, row, spec)
        with self.repository.transaction() as connection:
            previous = self.repository.idempotent_response(
                connection, scope, key, digest
            )
            if previous is not None:
                return previous
            self._store_report(connection, kind, run_id, "evaluation.completed", report)
            self.repository.remember_response(connection, scope, key, digest, report)
        return report

    def _store_report(
        self,
        connection: Any,
        kind: str,
        run_id: str,
        event: str,
        report: dict[str, Any],
    ) -> None:
        if kind == "agent":
            self.repository.add_run_events(connection, run_id, [(None, event, report)])
        else:
            self.workflows.event(connection, run_id, None, event, report)

    def submit_review(
        self,
        project_id: str,
        kind: str,
        target_id: str,
        run_id: str,
        evaluation_id: str,
        value: dict[str, Any],
        key: str,
    ) -> dict[str, Any]:
        from .human_review import submit_review

        return submit_review(
            self, project_id, kind, target_id, run_id, evaluation_id, value, key
        )

    def _assess(
        self,
        project_id: str,
        kind: str,
        target_id: str,
        run_id: str,
        row: Any,
        spec: EvaluationSpec,
    ) -> dict[str, Any]:
        spec_data = spec.to_dict()
        digest = sha256_digest(spec_data)
        version = (
            self.repository.version(spec.version_id)
            if kind == "agent"
            else self.repository.workflow_version(spec.version_id)
        )
        if version is None or version[f"{kind}_id"] != target_id:
            raise ProjectError(
                "Pinned evaluation version is unavailable", "evaluation_version_invalid"
            )
        source = (
            AgentSource.from_dict(json.loads(version["source_json"]))
            if kind == "agent"
            else WorkflowSource.from_dict(json.loads(version["source_json"]))
        )
        if any(
            getattr(source, name) != version[name]
            for name in ("source_hash", "behavior_hash", "lock_hash")
        ):
            raise ProjectError(
                "Pinned evaluation version failed integrity checks",
                "evaluation_version_invalid",
            )
        result = json.loads(row["result_json"]) if row["result_json"] else None
        completed = row["status"] in {"verified", "unverified"} and isinstance(
            result, dict
        )
        outputs: dict[str, Any] = result if isinstance(result, dict) else {}
        findings = [
            self._check(project_id, check, result if completed else None)
            for check in spec.checks
        ]
        conforms = (
            completed
            and all(
                (name in outputs and value_matches_field(field, outputs[name]))
                if field.required
                else (name not in outputs or value_matches_field(field, outputs[name]))
                for name, field in source.outputs.items()
            )
            and not (set(outputs) - set(source.outputs))
        )
        output_contract = (
            "pass" if conforms else "fail" if completed else "not_evaluated"
        )
        report = {
            "schema_version": "1.0",
            "evaluator_version": "2",
            "scope": "declared_checks",
            "evaluation_id": new_uuid7(),
            "project_id": project_id,
            "target_kind": kind,
            "target_id": target_id,
            "run_id": run_id,
            "version_id": spec.version_id,
            "run_status": row["status"],
            "source_hash": source.source_hash,
            "behavior_hash": source.behavior_hash,
            "lock_hash": source.lock_hash,
            "spec_hash": digest,
            "input_hash": sha256_digest(self.repository.run_inputs(run_id))
            if kind == "agent"
            else None,
            "input_evidence": "persisted" if kind == "agent" else "not_saved",
            "result_hash": sha256_digest(result) if result is not None else None,
            "created_at": utc_now(),
            "spec": spec_data,
            "decision": evaluation_decision(findings, output_contract),
            "checks": findings,
            "output_contract": output_contract,
            "independent_scope": "baseline_comparison_and_artifact_integrity_only",
        }
        return report

    def _check(
        self, project_id: str, check: EvaluationCheck, result: dict[str, Any] | None
    ) -> dict[str, Any]:
        finding: dict[str, Any] = {
            "id": check.id,
            "label": check.label,
            "required": check.required,
            "path": list(check.path),
            "method": check.method,
            "status": "not_evaluated",
            "code": "result_unavailable",
            "baseline": thaw_json(check.baseline),
            "evidence": [],
        }
        if result is None:
            return finding
        try:
            actual = resolve_value_path(result, check.path)
        except KeyError:
            return {**finding, "status": "fail", "code": "output_missing"}
        finding["actual_hash"] = sha256_digest(actual)
        if len(canonical_json(actual)) <= 2048:
            finding["actual_value"] = actual
        if check.method == "human_review":
            try:
                finding["evidence"] = self._review_artifacts(project_id, actual)
            except ProjectError as exc:
                return {**finding, "status": "fail", "code": exc.code}
            return {
                **finding,
                "status": "awaiting_human",
                "code": "human_review_required",
            }
        if check.method == "artifact_integrity":
            try:
                evidence = self._artifacts(project_id, actual)
            except ProjectError as exc:
                return {**finding, "status": "fail", "code": exc.code}
            return {
                **finding,
                "status": "pass",
                "code": "artifact_integrity_confirmed",
                "evidence": evidence,
            }
        if check.baseline["kind"] == "model":
            return {
                **finding,
                "status": "unknown",
                "code": "model_baseline_not_independent",
            }
        expected = thaw_json(check.expected)
        finding["expected_hash"] = sha256_digest(expected)
        if check.method == "number_equals":
            try:
                passed = exact_decimal(actual) == exact_decimal(expected)
            except ValueError:
                passed = False
        elif check.method == "set_equals":
            passed = _same_set(actual, expected)
        else:
            passed = _equal(actual, expected)
        return {
            **finding,
            "status": "pass" if passed else "fail",
            "code": "baseline_match" if passed else "baseline_mismatch",
        }

    def _review_artifacts(self, project_id: str, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            if value.get("kind") in {"artifact", "collection"}:
                return self._artifacts(project_id, value)
            return [
                item
                for nested in value.values()
                for item in self._review_artifacts(project_id, nested)
            ]
        if isinstance(value, list):
            return [
                item
                for nested in value
                for item in self._review_artifacts(project_id, nested)
            ]
        return []

    def _artifacts(self, project_id: str, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict) and value.get("kind") == "collection":
            value = value.get("items")
        items = value if isinstance(value, list) else [value]
        if not items:
            raise ProjectError("No artifact was supplied", "artifact_empty")
        evidence = []
        for item in items:
            if (
                not isinstance(item, dict)
                or item.get("kind") != "artifact"
                or not isinstance(item.get("artifact_id"), str)
            ):
                raise ProjectError(
                    "Output is not an ArtifactRef", "artifact_ref_invalid"
                )
            record, content = self.artifacts.read_bytes(project_id, item["artifact_id"])
            metadata = record.to_dict()
            if any(
                name in item and not _equal(item[name], metadata[name])
                for name in ("media_type", "filename", "sha256", "size_bytes")
            ):
                raise ProjectError(
                    "Artifact metadata differs from storage", "artifact_ref_mismatch"
                )
            if not content:
                raise ProjectError("Artifact is empty", "artifact_empty")
            evidence.append(
                {
                    "kind": "artifact",
                    "artifact_id": record.artifact_id,
                    "sha256": record.sha256,
                    "size_bytes": record.size_bytes,
                    "source_run_id": record.run_id,
                }
            )
        return evidence
