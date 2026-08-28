"""Local-only Project directory and Agent library HTTP surface."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from fastapi import APIRouter, Header, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from veyra_agent_platform.contracts.common import ContractValidationError, new_uuid7
from veyra_agent_platform.local.library.service import DraftConflict, LibraryService
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.storage import IdempotencyConflict

_Result = TypeVar("_Result")


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateProjectRequest(_ClosedModel):
    parent_path: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    agents: list[dict[str, Any]] = Field(default_factory=list)
    templates: list[dict[str, str]] = Field(default_factory=list)


class OpenProjectRequest(_ClosedModel):
    root_path: str = Field(min_length=1)


class SetProjectPinnedRequest(_ClosedModel):
    pinned: StrictBool


class ReplaceDraftRequest(_ClosedModel):
    source: dict[str, Any]
    expected_revision: int = Field(ge=0)


class TypedApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


def typed_error_response(_: Request, error: Exception) -> JSONResponse:
    typed_error = cast(TypedApiError, error)
    return JSONResponse(
        status_code=typed_error.status_code,
        content={
            "schema_version": "1.0",
            "code": typed_error.code,
            "message": typed_error.message,
            "request_id": new_uuid7(),
        },
    )


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

    @router.get("")
    def list_projects(request: Request) -> dict[str, Any]:
        projects, _ = _services(request)
        return {
            "schema_version": "1.0",
            "projects": [
                projects.project_summary(row["project_id"])
                for row in projects.repository.projects()
            ],
        }

    @router.post("", status_code=status.HTTP_201_CREATED)
    def create_project(
        payload: CreateProjectRequest, request: Request
    ) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(
            lambda: projects.create_in_parent(
                parent_path=payload.parent_path,
                name=payload.name,
                description=payload.description,
                sources=payload.agents,
                template_selections=payload.templates,
            )
        )

    @router.post("/open")
    def open_project(payload: OpenProjectRequest, request: Request) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(lambda: projects.index(payload.root_path))

    @router.get("/{project_id}")
    def get_project(project_id: str, request: Request) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(lambda: projects.project_summary(project_id))

    @router.patch("/{project_id}")
    def set_project_pinned(
        project_id: str, payload: SetProjectPinnedRequest, request: Request
    ) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(
            lambda: projects.set_pinned(project_id, pinned=payload.pinned)
        )

    @router.get("/{project_id}/agents")
    def list_agents(project_id: str, request: Request) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(
            lambda: {
                "schema_version": "1.0",
                "agents": projects.project_summary(project_id)["agents"],
            }
        )

    @router.get("/{project_id}/agents/{agent_id}/draft")
    def get_draft(
        project_id: str, agent_id: str, response: Response, request: Request
    ) -> dict[str, Any]:
        _, library = _services(request)
        result = _translate(lambda: library.draft(project_id, agent_id))
        response.headers["ETag"] = result["etag"]
        return result

    @router.patch("/{project_id}/agents/{agent_id}/draft")
    def patch_draft(
        project_id: str,
        agent_id: str,
        payload: ReplaceDraftRequest,
        response: Response,
        request: Request,
        if_match: str = Header(),
        idempotency_key: str = Header(),
    ) -> dict[str, Any]:
        _, library = _services(request)
        result = _translate(
            lambda: library.replace_draft(
                project_id=project_id,
                agent_id=agent_id,
                expected_etag=if_match,
                idempotency_key=idempotency_key,
                **payload.model_dump(),
            )
        )
        response.headers["ETag"] = result["etag"]
        return result

    @router.post("/{project_id}/agents/{agent_id}/validate")
    def validate_agent(
        project_id: str, agent_id: str, request: Request
    ) -> dict[str, Any]:
        _, library = _services(request)
        return _translate(lambda: library.validate(project_id, agent_id))

    @router.post("/{project_id}/agents/{agent_id}/commit")
    def commit_agent(
        project_id: str,
        agent_id: str,
        request: Request,
        idempotency_key: str = Header(),
    ) -> dict[str, Any]:
        _, library = _services(request)
        return _translate(
            lambda: library.commit(
                project_id=project_id,
                agent_id=agent_id,
                idempotency_key=idempotency_key,
            )
        )

    @router.post("/{project_id}/agents/{agent_id}/draft/reload")
    def reload_draft(
        project_id: str, agent_id: str, response: Response, request: Request
    ) -> dict[str, Any]:
        _, library = _services(request)
        result = _translate(lambda: library.reload_from_disk(project_id, agent_id))
        response.headers["ETag"] = result["etag"]
        return result

    @router.get("/{project_id}/agents/{agent_id}/export")
    def export_agent(
        project_id: str, agent_id: str, request: Request
    ) -> dict[str, Any]:
        _, library = _services(request)
        return _translate(lambda: library.export(project_id, agent_id))

    return router


def _services(request: Request) -> tuple[ProjectService, LibraryService]:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return request.app.state.projects, request.app.state.library


def _translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except DraftConflict as exc:
        raise TypedApiError(409, "draft_conflict", str(exc)) from exc
    except IdempotencyConflict as exc:
        raise TypedApiError(409, "idempotency_conflict", str(exc)) from exc
    except ProjectError as exc:
        raise TypedApiError(422, "project_invalid", str(exc)) from exc
    except ContractValidationError as exc:
        raise TypedApiError(422, "contract_invalid", str(exc)) from exc
