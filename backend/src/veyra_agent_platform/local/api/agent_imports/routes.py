"""HTTP surface for external Agent analysis and explicit application."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, TypeVar, cast

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from veyra_agent_platform.local.agent_imports import (
    AgentImportError,
    AgentImportService,
)
from veyra_agent_platform.local.api.projects import TypedApiError

_Result = TypeVar("_Result")


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApplyAgentImportRequest(_ClosedModel):
    project_id: str = Field(min_length=1)
    confirm: StrictBool
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    parent_agent_id: str | None = None


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/agent-imports", tags=["agent-imports"])

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def analyze_file(
        request: Request,
        file: Annotated[UploadFile | None, File()] = None,
        path: Annotated[str | None, Form()] = None,
    ) -> dict[str, Any]:
        service = _imports(request)
        if file is not None:
            contents = await file.read(12_000_001)
            await file.close()
            return _translate(
                lambda: service.analyze_file(filename=file.filename, contents=contents)
            )
        if path is not None:
            return _translate(lambda: service.analyze_folder(path))
        raise TypedApiError(
            422,
            "agent_import_source_required",
            "Upload a YAML/ZIP file or provide an Agent folder path",
        )

    @router.get("/{import_id}")
    def get_import(import_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _imports(request).get(import_id))

    @router.post("/{import_id}/apply")
    def apply_import(
        import_id: str,
        payload: ApplyAgentImportRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _translate(
            lambda: _imports(request).apply(
                import_id,
                project_id=payload.project_id,
                confirm=payload.confirm,
                name=payload.name,
                description=payload.description,
                parent_agent_id=payload.parent_agent_id,
            )
        )

    return router


def _imports(request: Request) -> AgentImportService:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    service = getattr(request.app.state, "agent_imports", None)
    if service is None:
        raise TypedApiError(503, "agent_import_unavailable", "Agent Import is starting")
    return cast(AgentImportService, service)


def _translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except AgentImportError as exc:
        status_code = (
            404
            if exc.code == "agent_import_not_found"
            else 409
            if exc.code == "agent_import_already_applied"
            else 422
        )
        raise TypedApiError(status_code, exc.code, str(exc)) from exc
