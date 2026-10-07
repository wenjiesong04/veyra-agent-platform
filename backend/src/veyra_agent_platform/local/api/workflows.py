"""Project-scoped Workflow execution, evidence, and approval controls."""

from __future__ import annotations

from typing import Any, Literal, cast

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..runtime.workflow_service import WorkflowRuntimeService
from .projects.routes import TypedApiError, _translate
from .runtime.routes import RunCommandRequest


class WorkflowRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, Any] = Field(default_factory=dict)
    source: Literal["draft", "committed"] = "draft"
    version_id: str | None = Field(default=None, min_length=36, max_length=36)

    @model_validator(mode="after")
    def validate_version_selection(self) -> WorkflowRunRequest:
        if self.version_id is not None and self.source != "committed":
            raise ValueError("version_id requires source='committed'")
        return self


def build_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/workflows/{workflow_id}",
        tags=["workflow-runtime"],
    )

    @router.post("/run")
    def run(
        project_id: str,
        workflow_id: str,
        payload: WorkflowRunRequest,
        request: Request,
        idempotency_key: str = Header(),
    ) -> dict[str, Any]:
        return _translate(
            lambda: _runtime(request).run(
                project_id,
                workflow_id,
                payload.inputs,
                idempotency_key,
                source=payload.source,
                version_id=payload.version_id,
            )
        )

    @router.get("/runtime-readiness")
    def runtime_readiness(
        project_id: str,
        workflow_id: str,
        request: Request,
        version_id: str | None = Query(default=None, min_length=36, max_length=36),
    ) -> dict[str, Any]:
        return _translate(
            lambda: _runtime(request).readiness(
                project_id, workflow_id, version_id=version_id
            )
        )

    @router.get("/runs")
    def runs(project_id: str, workflow_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _runtime(request).runs(project_id, workflow_id))

    @router.get("/runs/{run_id}")
    def detail(
        project_id: str, workflow_id: str, run_id: str, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _runtime(request).detail(project_id, workflow_id, run_id)
        )

    @router.post("/runs/{run_id}/commands")
    def command(
        project_id: str,
        workflow_id: str,
        run_id: str,
        payload: RunCommandRequest,
        request: Request,
        idempotency_key: str = Header(),
    ) -> dict[str, Any]:
        return _translate(
            lambda: _runtime(request).command(
                project_id,
                workflow_id,
                run_id,
                payload.command,
                idempotency_key,
                inputs=payload.inputs,
            )
        )

    @router.get("/runs/{run_id}/events")
    def events(
        project_id: str,
        workflow_id: str,
        run_id: str,
        request: Request,
        after: int = Query(default=0, ge=0),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        runtime = _runtime(request)
        _translate(lambda: runtime.detail(project_id, workflow_id, run_id))
        start = (
            max(after, int(last_event_id))
            if last_event_id and last_event_id.isdigit()
            else after
        )
        return StreamingResponse(
            runtime.follow_events(run_id, start),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router


def _runtime(request: Request) -> WorkflowRuntimeService:
    if not getattr(request.app.state, "database_ready", False):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(WorkflowRuntimeService, request.app.state.workflow_runtime)
