"""HTTP surface for local WorkItem scheduling."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, Field

from veyra_agent_platform.local.api.projects import TypedApiError
from veyra_agent_platform.local.orchestrator import (
    OrchestratorError,
    OrchestratorService,
)

_Result = TypeVar("_Result")
_NOT_FOUND = {
    "work_item_not_found",
    "orchestrator_project_not_found",
    "orchestrator_agent_not_found",
}


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateWorkItemRequest(_ClosedModel):
    title: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=10_000)
    depends_on: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)


class UpdateWorkItemRequest(_ClosedModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    agent_id: str | None = Field(default=None, max_length=64)
    depends_on: list[str] | None = None
    inputs: dict[str, Any] | None = None


def build_router() -> APIRouter:
    router = APIRouter(tags=["orchestrator"])

    @router.get("/api/v1/orchestrator/status")
    def orchestrator_status(request: Request) -> dict[str, Any]:
        return _translate(lambda: _orchestrator(request).status())

    @router.get("/api/v1/projects/{project_id}/work-items")
    def list_work_items(project_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _orchestrator(request).list_work_items(project_id))

    @router.post(
        "/api/v1/projects/{project_id}/work-items",
        status_code=status.HTTP_201_CREATED,
    )
    def create_work_item(
        project_id: str, payload: CreateWorkItemRequest, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _orchestrator(request).create_work_item(
                project_id,
                title=payload.title,
                agent_id=payload.agent_id,
                description=payload.description,
                depends_on=payload.depends_on,
                inputs=payload.inputs,
            )
        )

    @router.patch("/api/v1/work-items/{work_item_id}")
    def update_work_item(
        work_item_id: str, payload: UpdateWorkItemRequest, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _orchestrator(request).update_work_item(
                work_item_id,
                title=payload.title,
                description=payload.description,
                agent_id=payload.agent_id,
                depends_on=payload.depends_on,
                inputs=payload.inputs,
            )
        )

    @router.post("/api/v1/work-items/{work_item_id}/dispatch")
    def dispatch(work_item_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _orchestrator(request).dispatch(work_item_id))

    @router.post("/api/v1/work-items/{work_item_id}/retry")
    def retry(work_item_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _orchestrator(request).retry(work_item_id))

    @router.post("/api/v1/work-items/{work_item_id}/cancel")
    def cancel(work_item_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _orchestrator(request).cancel(work_item_id))

    @router.post("/api/v1/work-items/{work_item_id}/recover")
    def recover(work_item_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _orchestrator(request).recover_stalled(work_item_id))

    return router


def _orchestrator(request: Request) -> OrchestratorService:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(OrchestratorService, request.app.state.orchestrator)


def _translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except OrchestratorError as exc:
        status_code = 404 if exc.code in _NOT_FOUND else 422
        raise TypedApiError(status_code, exc.code, str(exc)) from exc
