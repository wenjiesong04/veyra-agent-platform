"""Local execution and evidence endpoints."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict

from veyra_agent_platform.local.api.projects.routes import TypedApiError, _translate
from veyra_agent_platform.local.runtime.service import RuntimeService


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inputs: dict[str, Any]


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["runtime"])

    @router.get("/components")
    def components(request: Request) -> dict[str, Any]:
        return _runtime(request).components()

    @router.post("/projects/{project_id}/agents/{agent_id}/run")
    def run(
        project_id: str,
        agent_id: str,
        payload: RunRequest,
        request: Request,
        idempotency_key: str = Header(),
    ) -> dict[str, Any]:
        return _translate(
            lambda: _runtime(request).run(
                project_id, agent_id, payload.inputs, idempotency_key
            )
        )

    @router.get("/projects/{project_id}/agents/{agent_id}/runs")
    def runs(project_id: str, agent_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _runtime(request).runs(project_id, agent_id))

    @router.get("/projects/{project_id}/agents/{agent_id}/runs/{run_id}")
    def detail(
        project_id: str, agent_id: str, run_id: str, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _runtime(request).run_detail(project_id, agent_id, run_id)
        )

    return router


def _runtime(request: Request) -> RuntimeService:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(RuntimeService, request.app.state.runtime)
