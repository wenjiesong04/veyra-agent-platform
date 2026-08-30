"""HTTP surface for the Project-scoped Factory conversation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from veyra_agent_platform.local.api.projects.routes import TypedApiError
from veyra_agent_platform.local.factory import FactoryProviderError, FactoryService

_Result = TypeVar("_Result")


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateFactorySessionRequest(_ClosedModel):
    goal: str | None = Field(default=None, max_length=10_000)


class FactoryMessageRequest(_ClosedModel):
    content: str = Field(min_length=1, max_length=10_000)


class ApplyFactoryDraftRequest(_ClosedModel):
    confirm: StrictBool
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}/factory", tags=["factory"])

    @router.post("/sessions", status_code=status.HTTP_201_CREATED)
    def create_session(
        project_id: str, payload: CreateFactorySessionRequest, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _factory(request).create_session(project_id, payload.goal)
        )

    @router.get("/sessions/{session_id}")
    def get_session(
        project_id: str, session_id: str, request: Request
    ) -> dict[str, Any]:
        return _translate(lambda: _factory(request).get_session(project_id, session_id))

    @router.post("/sessions/{session_id}/messages")
    def add_message(
        project_id: str,
        session_id: str,
        payload: FactoryMessageRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _translate(
            lambda: _factory(request).add_message(
                project_id, session_id, payload.content
            )
        )

    @router.post("/sessions/{session_id}/generate")
    def generate(project_id: str, session_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _factory(request).generate(project_id, session_id))

    @router.post("/sessions/{session_id}/apply-draft")
    def apply_draft(
        project_id: str,
        session_id: str,
        payload: ApplyFactoryDraftRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _translate(
            lambda: _factory(request).apply_draft(
                project_id,
                session_id,
                confirm=payload.confirm,
                name=payload.name,
                description=payload.description,
            )
        )

    return router


def _factory(request: Request) -> FactoryService:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(FactoryService, request.app.state.factory)


def _translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except FactoryProviderError as exc:
        unavailable = {
            "factory_provider_not_configured",
            "factory_unavailable",
            "factory_timeout",
        }
        status_code = 503 if exc.code in unavailable else 502
        raise TypedApiError(status_code, exc.code, str(exc)) from exc
    except TypedApiError:
        raise
    except Exception as exc:
        code = getattr(exc, "code", "factory_invalid")
        status_code = 404 if code == "factory_session_not_found" else 422
        raise TypedApiError(status_code, code, str(exc)) from exc
