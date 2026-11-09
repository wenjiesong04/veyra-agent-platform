"""Candidate-to-delivery gate. The caller owns the same-run continuation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Protocol

from veyra_agent_platform.contracts.agent import AgentSource

from .evidence_review import evidence_packet, parse_evidence_assessment
from .finalization import CandidateReview, ReviewPhase, candidate_fingerprint
from .native_images import all_images_cached


class _GateHost(Protocol):
    def _is_running(self, run_id: str) -> bool: ...

    def _loop_evidence_review(
        self,
        run_id: str,
        model: Any,
        packet: dict[str, Any],
        emit: Any,
        on_assessed: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]: ...

    def _prepare_outputs(
        self, project_id: str, source: AgentSource, values: dict[str, Any]
    ) -> dict[str, Any]: ...

    def _loop_render_images(
        self,
        project_id: str,
        run_id: str,
        source: AgentSource,
        values: dict[str, Any],
        final_outputs: Mapping[str, Any],
        emit: Any,
        *,
        cache: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def _loop_candidate_review(
        self,
        project_id: str,
        run_id: str,
        source: AgentSource,
        model: Any,
        values: dict[str, Any],
        outputs: Mapping[str, Any],
        messages: list[dict[str, Any]],
        emit: Any,
        *,
        phase: ReviewPhase,
        user_replies: list[dict[str, str]] | None = None,
        pending_images: Mapping[str, Any] | None = None,
        design_context: str = "",
        evidence_assessment: Mapping[str, Any] | None = None,
    ) -> CandidateReview: ...


@dataclass(frozen=True)
class FinalizationDecision:
    outputs: dict[str, Any] | None
    feedback: dict[str, Any] | None
    model_requests: int
    candidate_hash: str


def evidence_review_required(
    source: AgentSource,
    values: Mapping[str, Any],
    user_replies: list[dict[str, str]],
    cache: Mapping[str, Any],
) -> bool:
    policy = source.finalization
    if policy is None or policy.review_strategy != "evidence_first":
        return False
    packet = evidence_packet(source, values, user_replies)
    return cache.get("input_hash") != candidate_fingerprint(packet)


def _evidence_assessment(
    host: _GateHost,
    run_id: str,
    source: AgentSource,
    model: Any,
    values: dict[str, Any],
    user_replies: list[dict[str, str]],
    cache: dict[str, Any],
    emit: Any,
) -> tuple[dict[str, Any] | None, int]:
    import json

    if source.finalization is None or source.finalization.review_strategy == "direct":
        return None, 0
    packet = evidence_packet(source, values, user_replies)
    fingerprint = candidate_fingerprint(packet)
    if cache.get("input_hash") == fingerprint:
        assessment = parse_evidence_assessment(
            json.dumps(cache.get("assessment")), packet
        )
        return assessment, 0

    def remember(assessment: dict[str, Any]) -> None:
        cache.clear()
        cache.update(input_hash=fingerprint, assessment=assessment)

    assessment = host._loop_evidence_review(run_id, model, packet, emit, remember)
    return assessment, 1


def finalize_candidate(
    host: _GateHost,
    project_id: str,
    run_id: str,
    source: AgentSource,
    model: Any,
    values: dict[str, Any],
    candidate: Mapping[str, Any],
    messages: list[dict[str, Any]],
    emit: Callable[[str | None, str, dict[str, Any]], None],
    *,
    remaining_requests: int,
    render_cache: dict[str, Any],
    evidence_cache: dict[str, Any] | None = None,
    user_replies: list[dict[str, str]] | None = None,
    skip_pre_review: bool = False,
) -> FinalizationDecision:
    from .service import RuntimeError, _check, _RunAbandoned

    policy = source.finalization
    assert policy is not None
    requests = 0
    evidence_cache = evidence_cache if evidence_cache is not None else {}
    assessed_candidate = dict(candidate)

    def passes(check: str, outputs: dict[str, Any]) -> bool:
        try:
            return _check(check, outputs)
        except RuntimeError as exc:
            if exc.code == "condition_invalid":
                return False
            raise

    def reject(feedback: dict[str, Any], phase: str) -> FinalizationDecision:
        emit(
            "model",
            "finalization.rejected",
            {"phase": phase, **feedback, "published": False},
        )
        return FinalizationDecision(
            None, feedback, requests, candidate_fingerprint(assessed_candidate)
        )

    deferred = {
        check
        for check in policy.checks
        if check.split(":", 1)[-1] in source.outputs
        and source.outputs[check.split(":", 1)[-1]].is_artifact()
    }
    failed = [
        check
        for check in policy.checks
        if check not in deferred and not passes(check, dict(candidate))
    ]
    if failed:
        return reject(
            {
                "status": "revise",
                "failed_checks": failed,
                "evidence_kind": "deterministic",
            },
            "preflight",
        )
    merged = {**values, **candidate}
    phases = (
        (
            [False, True]
            if policy.pre_render_review
            and not skip_pre_review
            and not all_images_cached(host, project_id, source, render_cache)
            else [True]
        )
        if policy.review_images
        else [False]
    )
    required_reviews = len(phases) + int(
        evidence_review_required(source, values, user_replies or [], evidence_cache)
    )
    if policy.criteria and remaining_requests < required_reviews:
        emit(
            "model",
            "agent.budget_insufficient",
            {
                "required_remaining": required_reviews,
                "remaining_requests": remaining_requests,
                "phase": "delivery_review",
                "published": False,
            },
        )
        raise RuntimeError(
            "agent_finalization_budget_exhausted",
            "No image was requested: the remaining budget cannot cover "
            "all required delivery reviews",
        )
    if not policy.criteria and remaining_requests < len(phases):
        phases = (
            ([True] if policy.review_images else [False]) if remaining_requests else []
        )
    final_findings: list[dict[str, Any]] = []
    advisory_errors: list[str] = []
    assessed = False
    evidence_assessment, requests = _evidence_assessment(
        host, run_id, source, model, values, user_replies or [], evidence_cache, emit
    )
    for images in phases if policy.review_criteria else []:
        if requests >= remaining_requests:
            raise RuntimeError(
                "agent_finalization_budget_exhausted",
                "The candidate is not published: no model turn remains "
                "for its required review",
            )
        if images:
            merged = host._loop_render_images(
                project_id, run_id, source, merged, candidate, emit, cache=render_cache
            )
            host._prepare_outputs(project_id, source, merged)
        assessed_candidate = {
            name: merged[name] for name in source.outputs if name in merged
        }
        phase: ReviewPhase = (
            "images"
            if images
            else "pre_render"
            if policy.review_images
            else "candidate"
        )
        pending_images: dict[str, Any] | None = None
        if phase == "pre_render":
            pending_images = {}
            for name, field in source.outputs.items():
                if not (field.is_artifact() and field.artifact_kind == "image"):
                    continue
                cached = render_cache.get(name)
                pending_images[name] = (
                    {"artifact": cached["artifact"]}
                    if isinstance(cached, dict) and cached.get("native")
                    else {
                        "source": "candidate_and_output_description",
                        "description": field.description,
                    }
                )
        review_options: dict[str, Any] = (
            {"evidence_assessment": evidence_assessment}
            if evidence_assessment is not None
            else {}
        )
        try:
            review = host._loop_candidate_review(
                project_id,
                run_id,
                source,
                model,
                values,
                merged,
                messages,
                emit,
                phase=phase,
                user_replies=user_replies,
                pending_images=pending_images,
                **review_options,
            )
        except RuntimeError as exc:
            if policy.criteria or not (
                exc.code.startswith("runtime_")
                or exc.code == "agent_finalization_review_invalid"
            ):
                raise
            advisory_errors.append(exc.code)
            requests += 1
            continue
        requests += 1
        assessed = True
        final_findings = list(review.findings)
        if review.status != "pass":
            if phase != "pre_render":
                for name in review.invalidate_images:
                    render_cache.pop(name, None)
            return reject(review.observation(), phase)
    merged = host._loop_render_images(
        project_id, run_id, source, merged, candidate, emit, cache=render_cache
    )
    outputs = host._prepare_outputs(project_id, source, merged)
    if not host._is_running(run_id):
        raise _RunAbandoned()
    failed = [check for check in policy.checks if not passes(check, outputs)]
    if failed:
        return reject(
            {
                "status": "revise",
                "failed_checks": failed,
                "evidence_kind": "deterministic",
            },
            "artifacts",
        )
    emit(
        "model",
        "finalization.accepted",
        {
            "checks": list(policy.checks),
            "criteria_count": len(policy.review_criteria),
            "findings": final_findings,
            "advisory_unverified": (
                len(policy.advisory_criteria) if not assessed or advisory_errors else 0
            )
            or sum(
                finding["criterion"] >= len(policy.criteria)
                and finding["status"] != "pass"
                for finding in final_findings
            ),
            "image_review": policy.review_images,
            "advisory_review_errors": advisory_errors,
            "evidence_kind": "model_assessment" if assessed else "deterministic",
            "independent_verification": False,
        },
    )
    return FinalizationDecision(outputs, None, requests, candidate_fingerprint(outputs))


def review_before_render(
    host: _GateHost,
    project_id: str,
    run_id: str,
    source: AgentSource,
    model: Any,
    values: dict[str, Any],
    candidate: Mapping[str, Any],
    messages: list[dict[str, Any]],
    emit: Callable[[str | None, str, dict[str, Any]], None],
    *,
    remaining_requests: int,
    user_replies: list[dict[str, str]],
    pending_images: Mapping[str, Any],
    design_context: str = "",
    evidence_cache: dict[str, Any] | None = None,
) -> FinalizationDecision:
    from .service import RuntimeError, _check, _RunAbandoned

    policy = source.finalization
    assert policy is not None
    image_names = {
        name
        for name, field in source.outputs.items()
        if field.is_artifact() and field.artifact_kind == "image"
    }
    preview = replace(
        source,
        outputs={
            name: field
            for name, field in source.outputs.items()
            if not (field.is_artifact() and field.artifact_kind == "image")
        },
    )
    # Only output validation uses the text projection. Review keeps the original
    # declarations and pending effects; readiness is not a delivery candidate.
    outputs = host._prepare_outputs(project_id, preview, {**values, **candidate})
    failed = []
    for check in policy.checks:
        if check.split(":", 1)[-1] in image_names:
            continue
        try:
            passed = _check(check, outputs)
        except RuntimeError as exc:
            if exc.code != "condition_invalid":
                raise
            passed = False
        if not passed:
            failed.append(check)
    feedback: dict[str, Any] | None = None
    requests = 0
    evidence_cache = evidence_cache if evidence_cache is not None else {}
    required_reviews = 1 + int(
        evidence_review_required(source, values, user_replies, evidence_cache)
    )
    if failed:
        feedback = {
            "status": "revise",
            "failed_checks": failed,
            "evidence_kind": "deterministic",
        }
    elif policy.criteria and remaining_requests < required_reviews:
        raise RuntimeError(
            "agent_finalization_budget_exhausted",
            "No image was requested: no model turn remains for its required pre-review",
        )
    elif policy.review_criteria and remaining_requests:
        evidence_assessment, requests = _evidence_assessment(
            host, run_id, source, model, values, user_replies, evidence_cache, emit
        )
        requests += 1
        review_options: dict[str, Any] = (
            {"evidence_assessment": evidence_assessment}
            if evidence_assessment is not None
            else {}
        )
        try:
            review = host._loop_candidate_review(
                project_id,
                run_id,
                source,
                model,
                values,
                {**values, **candidate},
                messages,
                emit,
                phase="pre_render",
                user_replies=user_replies,
                pending_images=pending_images,
                design_context=design_context,
                **review_options,
            )
        except RuntimeError as exc:
            if policy.criteria or not (
                exc.code.startswith("runtime_")
                or exc.code == "agent_finalization_review_invalid"
            ):
                raise
        else:
            if review.status != "pass":
                feedback = review.observation()
    if not host._is_running(run_id):
        raise _RunAbandoned()
    if feedback is not None:
        emit(
            "model",
            "finalization.rejected",
            {"phase": "pre_render", **feedback, "published": False},
        )
    return FinalizationDecision(
        outputs if feedback is None else None,
        feedback,
        requests,
        candidate_fingerprint(candidate),
    )
