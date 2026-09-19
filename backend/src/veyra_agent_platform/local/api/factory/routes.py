"""HTTP surface for Factory status and Project-scoped conversations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.local.api.projects import TypedApiError
from veyra_agent_platform.local.factory import (
    FactoryError,
    FactoryProviderError,
    FactoryService,
)
from veyra_agent_platform.local.library.service import DraftConflict
from veyra_agent_platform.local.projects.service import ProjectError

_Result = TypeVar("_Result")
_PROVIDER_UNAVAILABLE = {
    "factory_provider_not_configured",
    "factory_unavailable",
    "factory_timeout",
}


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
    parent_agent_id: str | None = Field(default=None, max_length=64)


def build_router() -> APIRouter:
    router = APIRouter(tags=["factory"])

    @router.get("/api/v1/factory/status")
    def factory_status(request: Request) -> dict[str, Any]:
        return _translate(lambda: _factory(request).status())

    sessions = APIRouter(prefix="/api/v1/projects/{project_id}/factory")

    @sessions.post("/sessions", status_code=status.HTTP_201_CREATED)
    def create_session(
        project_id: str, payload: CreateFactorySessionRequest, request: Request
    ) -> dict[str, Any]:
        return _translate(
            lambda: _factory(request).create_session(project_id, payload.goal)
        )

    @sessions.get("/sessions/{session_id}")
    def get_session(
        project_id: str, session_id: str, request: Request
    ) -> dict[str, Any]:
        return _translate(lambda: _factory(request).get_session(project_id, session_id))

    @sessions.post("/sessions/{session_id}/messages")
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

    @sessions.post("/sessions/{session_id}/generate")
    def generate(project_id: str, session_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _factory(request).generate(project_id, session_id))

    @sessions.post("/sessions/{session_id}/apply-draft")
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
                parent_agent_id=payload.parent_agent_id,
            )
        )

    router.include_router(sessions)
    return router


def _factory(request: Request) -> FactoryService:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(FactoryService, request.app.state.factory)


def _translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except FactoryProviderError as exc:
        status_code = 503 if exc.code in _PROVIDER_UNAVAILABLE else 502
        raise TypedApiError(
            status_code,
            exc.code,
            str(exc),
            details=exc.details or None,
        ) from exc
    except FactoryError as exc:
        status_code = (
            404
            if exc.code
            in {
                "factory_session_not_found",
                "factory_project_not_found",
                "edit_proposal_not_found",
            }
            else 422
        )
        raise TypedApiError(status_code, exc.code, str(exc)) from exc
    except DraftConflict as exc:
        raise TypedApiError(409, "draft_conflict", str(exc)) from exc
    except ProjectError as exc:
        raise TypedApiError(422, exc.code, str(exc)) from exc
    except ContractValidationError as exc:
        raise TypedApiError(422, "contract_invalid", str(exc)) from exc
    except TypedApiError:
        raise
