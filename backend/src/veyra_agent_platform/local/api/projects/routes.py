"""Local-only Project directory and Agent library HTTP surface."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Literal, TypeVar, cast

from fastapi import APIRouter, File, Form, Header, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from veyra_agent_platform.contracts.common import ContractValidationError, new_uuid7
from veyra_agent_platform.local.library.service import DraftConflict, LibraryService
from veyra_agent_platform.local.projects.service import (
    MAX_AGENT_IMPORT_BYTES,
    ProjectError,
    ProjectService,
)
from veyra_agent_platform.local.storage import IdempotencyConflict

_Result = TypeVar("_Result")


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateProjectRequest(_ClosedModel):
    name: str | None = None
    description: str = ""
    agents: list[dict[str, Any]] = Field(default_factory=list)
    templates: list[dict[str, str]] = Field(default_factory=list)


class OpenProjectRequest(_ClosedModel):
    root_path: str = Field(min_length=1)


class UpdateProjectRequest(_ClosedModel):
    name: str | None = None
    description: str | None = None
    pinned: StrictBool | None = None

    @model_validator(mode="after")
    def require_update(self) -> UpdateProjectRequest:
        if not self.model_fields_set:
            raise ValueError("at least one Project field is required")
        return self


class ReplaceDraftRequest(_ClosedModel):
    source: dict[str, Any]
    expected_revision: int = Field(ge=0)


class CommitAgentRequest(_ClosedModel):
    expected_revision: int = Field(ge=0)


class CreateAgentRequest(_ClosedModel):
    mode: Literal["blank", "template"]
    template_id: str | None = None
    name: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def require_template_for_template_mode(self) -> CreateAgentRequest:
        if self.mode == "template" and self.template_id is None:
            raise ValueError("template_id is required for template mode")
        if self.mode == "blank" and self.template_id is not None:
            raise ValueError("template_id is only valid for template mode")
        return self


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
            lambda: projects.create_managed(
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
    def update_project(
        project_id: str, payload: UpdateProjectRequest, request: Request
    ) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(
            lambda: projects.edit(
                project_id,
                name=payload.name if "name" in payload.model_fields_set else None,
                description=(
                    payload.description
                    if "description" in payload.model_fields_set
                    else None
                ),
                pinned=payload.pinned if "pinned" in payload.model_fields_set else None,
            )
        )

    @router.delete("/{project_id}")
    def delete_project(project_id: str, request: Request) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(lambda: projects.remove(project_id))

    @router.get("/{project_id}/agent-templates")
    def list_agent_templates(project_id: str, request: Request) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(
            lambda: {
                "schema_version": "1.0",
                "project_id": projects.project_summary(project_id)["project_id"],
                "templates": projects.template_metadata(),
            }
        )

    @router.post("/{project_id}/agents", status_code=status.HTTP_201_CREATED)
    def create_agent(
        project_id: str, payload: CreateAgentRequest, request: Request
    ) -> dict[str, Any]:
        projects, _ = _services(request)
        return _translate(
            lambda: projects.create_agent(project_id=project_id, **payload.model_dump())
        )

    @router.post("/{project_id}/agents/import", status_code=status.HTTP_201_CREATED)
    def import_agent(
        project_id: str,
        request: Request,
        file: Annotated[UploadFile, File()],
        name: Annotated[str | None, Form()] = None,
        description: Annotated[str | None, Form()] = None,
    ) -> dict[str, Any]:
        projects, _ = _services(request)
        contents = file.file.read(MAX_AGENT_IMPORT_BYTES + 1)
        return _translate(
            lambda: projects.import_agent(
                project_id=project_id,
                filename=file.filename,
                contents=contents,
                name=name,
                description=description,
            )
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
        payload: CommitAgentRequest,
        request: Request,
        if_match: str = Header(),
        idempotency_key: str = Header(),
    ) -> dict[str, Any]:
        _, library = _services(request)
        return _translate(
            lambda: library.commit(
                project_id=project_id,
                agent_id=agent_id,
                expected_revision=payload.expected_revision,
                expected_etag=if_match,
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
        code = getattr(exc, "code", "project_invalid")
        if code != "project_invalid":
            raise TypedApiError(422, code, str(exc)) from exc
        raise TypedApiError(422, "project_invalid", str(exc)) from exc
    except ContractValidationError as exc:
        raise TypedApiError(422, "contract_invalid", str(exc)) from exc
