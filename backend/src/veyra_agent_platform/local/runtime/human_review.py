"""Append-only local user reviews over an immutable evaluation snapshot."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from veyra_agent_platform.contracts.canonical import sha256_digest
from veyra_agent_platform.contracts.common import IdempotencyKey, new_uuid7
from veyra_agent_platform.contracts.evaluation import EvaluationReview, EvaluationSpec
from veyra_agent_platform.local.projects.service import ProjectError

from .evaluation import evaluation_decision
from .workflow_store import utc_now

if TYPE_CHECKING:
    from .evaluation import RunEvaluationService


def _snapshot(report: dict[str, Any]) -> dict[str, Any]:
    return {
        **{
            key: report[key]
            for key in (
                "version_id",
                "source_hash",
                "behavior_hash",
                "lock_hash",
                "spec_hash",
                "input_hash",
                "result_hash",
                "output_contract",
                "run_status",
            )
        },
        "checks": [
            {key: finding.get(key) for key in ("id", "actual_hash", "evidence")}
            for finding in report["checks"]
        ],
    }


def submit_review(
    host: RunEvaluationService,
    project_id: str,
    kind: str,
    target_id: str,
    run_id: str,
    evaluation_id: str,
    value: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    IdempotencyKey("1.0", key)
    request = EvaluationReview.from_dict(value)
    host._row(project_id, kind, target_id, run_id)
    scope = f"evaluation-review:{kind}:{run_id}:{evaluation_id}"
    digest = sha256_digest(request.to_dict())
    with host.repository.transaction() as connection:
        replay = host.repository.idempotent_response(connection, scope, key, digest)
        if replay is not None:
            return replay
        table = "runtime_run_events" if kind == "agent" else "workflow_run_events"
        events = connection.execute(
            f"SELECT payload_json FROM {table} WHERE run_id=? AND kind IN "
            "('evaluation.completed','evaluation.reviewed') ORDER BY sequence DESC",
            (run_id,),
        ).fetchall()
        reports: list[dict[str, Any]] = [
            json.loads(event["payload_json"]) for event in events
        ]
        chain = [
            report
            for report in reports
            if report.get("root_evaluation_id", report["evaluation_id"])
            == evaluation_id
        ]
        if not chain:
            raise ProjectError(
                "Evaluation report was not found", "evaluation_report_not_found"
            )
        base = chain[0]
        if base["evaluation_id"] != request.expected_report_id:
            raise ProjectError(
                "Review history changed; refresh before submitting",
                "evaluation_review_conflict",
            )
        if any(
            base[name] != getattr(request, name)
            for name in ("version_id", "spec_hash", "result_hash")
        ):
            raise ProjectError(
                "Review does not match the selected result snapshot",
                "evaluation_review_mismatch",
            )
        row = host._row(project_id, kind, target_id, run_id)
        fresh = host._assess(
            project_id,
            kind,
            target_id,
            run_id,
            row,
            EvaluationSpec.from_dict(base["spec"]),
        )
        if _snapshot(fresh) != _snapshot(base):
            raise ProjectError(
                "Result or artifact contents changed; create a new evaluation",
                "evaluation_snapshot_changed",
            )
        findings = {item["id"]: item for item in fresh["checks"]}
        if any(
            entry["check_id"] not in findings
            or findings[entry["check_id"]]["method"] != "human_review"
            or findings[entry["check_id"]]["status"] != "awaiting_human"
            or not findings[entry["check_id"]].get("actual_hash")
            for entry in request.decisions
        ):
            raise ProjectError(
                "Only available human-review outputs can be assessed",
                "evaluation_check_not_reviewable",
            )
        report = deepcopy(base)
        review_id, created_at = new_uuid7(), utc_now()
        decisions = {entry["check_id"]: entry for entry in request.decisions}
        codes = {
            "pass": "user_review_accepted",
            "fail": "user_review_rejected",
            "unknown": "user_review_uncertain",
        }
        for finding in report["checks"]:
            entry = decisions.get(finding["id"])
            if entry is not None:
                finding.update(
                    status=entry["outcome"],
                    code=codes[entry["outcome"]],
                    human_review={
                        **entry,
                        "review_id": review_id,
                        "source": "local_user",
                        "created_at": created_at,
                        "base_evaluation_id": base["evaluation_id"],
                    },
                )
        report.update(
            evaluator_version="2",
            evaluation_id=new_uuid7(),
            root_evaluation_id=evaluation_id,
            parent_evaluation_id=base["evaluation_id"],
            created_at=created_at,
            review={
                "review_id": review_id,
                "source": "local_user",
                "created_at": created_at,
                "base_evaluation_id": base["evaluation_id"],
                "supersedes_review_id": base.get("review", {}).get("review_id"),
                "decisions": [dict(entry) for entry in request.decisions],
            },
            decision=evaluation_decision(report["checks"], report["output_contract"]),
            independent_scope="baseline_comparison_artifact_integrity_and_user_review",
        )
        host._store_report(connection, kind, run_id, "evaluation.reviewed", report)
        host.repository.remember_response(connection, scope, key, digest, report)
        return report
