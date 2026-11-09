"""User-requested offline result evaluation for Agents and Workflows."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict

from veyra_agent_platform.local.api.projects.routes import TypedApiError, _translate
from veyra_agent_platform.local.runtime.evaluation import RunEvaluationService


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec: dict[str, Any]


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_report_id: str
    version_id: str
    spec_hash: str
    result_hash: str
    decisions: list[dict[str, Any]]


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["run-evaluation"])

    @router.get("/agents/{agent_id}/runs/{run_id}/evaluations")
    def agent_reports(
        project_id: str, agent_id: str, run_id: str, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _service(request).reports(project_id, "agent", agent_id, run_id)
        )

    @router.post("/agents/{agent_id}/runs/{run_id}/evaluations")
    def agent_evaluate(
        project_id: str,
        agent_id: str,
        run_id: str,
        payload: EvaluationRequest,
        request: Request,
        idempotency_key: str = Header(),
    ) -> dict[str, Any]:
        return _translate(
            lambda: _service(request).evaluate(
                project_id, "agent", agent_id, run_id, payload.spec, idempotency_key
            )
        )

    @router.get("/workflows/{workflow_id}/runs/{run_id}/evaluations")
    def workflow_reports(
        project_id: str, workflow_id: str, run_id: str, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _service(request).reports(
                project_id, "workflow", workflow_id, run_id
            )
        )

    @router.post("/workflows/{workflow_id}/runs/{run_id}/evaluations")
    def workflow_evaluate(
        project_id: str,
        workflow_id: str,
        run_id: str,
        payload: EvaluationRequest,
        request: Request,
        idempotency_key: str = Header(),
    ) -> dict[str, Any]:
        return _translate(
            lambda: _service(request).evaluate(
                project_id,
                "workflow",
                workflow_id,
                run_id,
                payload.spec,
                idempotency_key,
            )
        )

    @router.post("/agents/{agent_id}/runs/{run_id}/evaluations/{evaluation_id}/reviews")
    def agent_review(
        project_id: str,
        agent_id: str,
        run_id: str,
        evaluation_id: str,
        payload: ReviewRequest,
        request: Request,
        idempotency_key: str = Header(),
    ) -> dict[str, Any]:
        return _translate(
            lambda: _service(request).submit_review(
                project_id,
                "agent",
                agent_id,
                run_id,
                evaluation_id,
                payload.model_dump(),
                idempotency_key,
            )
        )

    @router.post(
        "/workflows/{workflow_id}/runs/{run_id}/evaluations/{evaluation_id}/reviews"
    )
    def workflow_review(
        project_id: str,
        workflow_id: str,
        run_id: str,
        evaluation_id: str,
        payload: ReviewRequest,
        request: Request,
        idempotency_key: str = Header(),
    ) -> dict[str, Any]:
        return _translate(
            lambda: _service(request).submit_review(
                project_id,
                "workflow",
                workflow_id,
                run_id,
                evaluation_id,
                payload.model_dump(),
                idempotency_key,
            )
        )

    return router


def _service(request: Request) -> RunEvaluationService:
    if not getattr(request.app.state, "database_ready", False):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(RunEvaluationService, request.app.state.run_evaluations)
