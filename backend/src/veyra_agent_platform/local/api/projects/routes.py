"""Local-only Project directory and Agent library HTTP surface."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from veyra_agent_platform.contracts.common import ContractValidationError
from veyra_agent_platform.local.library.service import DraftConflict, LibraryService
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService

_Result = TypeVar("_Result")


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateProjectRequest(_ClosedModel):
    root_path: str = Field(min_length=1)
    name: str = Field(min_length=1)
    agents: list[dict[str, Any]] = Field(min_length=1)


class OpenProjectRequest(_ClosedModel):
    root_path: str = Field(min_length=1)


class ReplaceDraftRequest(_ClosedModel):
    source: dict[str, Any]
    expected_revision: int = Field(ge=0)
    idempotency_key: str


class IdempotentRequest(_ClosedModel):
    idempotency_key: str


def build_router(projects: ProjectService, library: LibraryService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

    @router.get("")
    def list_projects() -> dict[str, Any]:
        return {
            "projects": [
                projects.project_summary(row["project_id"])
                for row in projects.repository.projects()
            ]
        }

    @router.post("")
    def create_project(payload: CreateProjectRequest) -> dict[str, Any]:
        return _translate(
            lambda: projects.create(
                root_path=payload.root_path,
                name=payload.name,
                sources=payload.agents,
            )
        )

    @router.post("/open")
    def open_project(payload: OpenProjectRequest) -> dict[str, Any]:
        return _translate(lambda: projects.index(payload.root_path))

    @router.get("/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        return _translate(lambda: projects.project_summary(project_id))

    @router.get("/{project_id}/agents")
    def list_agents(project_id: str) -> dict[str, Any]:
        return _translate(
            lambda: {"agents": projects.project_summary(project_id)["agents"]}
        )

    @router.get("/{project_id}/agents/{agent_id}/draft")
    def get_draft(project_id: str, agent_id: str, response: Response) -> dict[str, Any]:
        result = _translate(lambda: library.draft(project_id, agent_id))
        response.headers["ETag"] = result["etag"]
        return result

    @router.patch("/{project_id}/agents/{agent_id}/draft")
    def patch_draft(
        project_id: str,
        agent_id: str,
        payload: ReplaceDraftRequest,
        response: Response,
        if_match: str | None = Header(default=None),
    ) -> dict[str, Any]:
        result = _translate(
            lambda: library.replace_draft(
                project_id=project_id,
                agent_id=agent_id,
                expected_etag=if_match,
                **payload.model_dump(),
            )
        )
        response.headers["ETag"] = result["etag"]
        return result

    @router.post("/{project_id}/agents/{agent_id}/validate")
    def validate_agent(project_id: str, agent_id: str) -> dict[str, Any]:
        return _translate(lambda: library.validate(project_id, agent_id))

    @router.post("/{project_id}/agents/{agent_id}/commit")
    def commit_agent(
        project_id: str, agent_id: str, payload: IdempotentRequest
    ) -> dict[str, Any]:
        return _translate(
            lambda: library.commit(
                project_id=project_id, agent_id=agent_id, **payload.model_dump()
            )
        )

    @router.get("/{project_id}/agents/{agent_id}/export")
    def export_agent(project_id: str, agent_id: str) -> dict[str, Any]:
        return _translate(lambda: library.export(project_id, agent_id))

    return router


def _translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except DraftConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProjectError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ContractValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
