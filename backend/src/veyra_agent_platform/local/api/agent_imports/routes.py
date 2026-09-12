"""Local external Agent Import V1 routes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, TypeVar, cast

from fastapi import APIRouter, File, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from veyra_agent_platform.local.agent_imports import (
    AgentImportError,
    AgentImportService,
)
from veyra_agent_platform.local.agent_imports.service import MAX_ARCHIVE_BYTES
from veyra_agent_platform.local.api.projects import TypedApiError

_Result = TypeVar("_Result")


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalyzeFolderRequest(_ClosedModel):
    path: str = Field(min_length=1)


class ApplyAgentImportRequest(_ClosedModel):
    project_id: str = Field(min_length=1)
    confirm: StrictBool
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    parent_agent_id: str | None = None


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/agent-imports", tags=["agent-imports"])

    @router.post("/file", status_code=status.HTTP_201_CREATED)
    def analyze_file(
        request: Request,
        file: Annotated[UploadFile, File()],
    ) -> dict[str, Any]:
        contents = file.file.read(MAX_ARCHIVE_BYTES + 1)
        return _translate(
            lambda: _importer(request).analyze_file(
                filename=file.filename, contents=contents
            )
        )

    @router.post("/folder", status_code=status.HTTP_201_CREATED)
    def analyze_folder(
        payload: AnalyzeFolderRequest, request: Request
    ) -> dict[str, Any]:
        return _translate(lambda: _importer(request).analyze_folder(payload.path))

    @router.get("/{import_id}")
    def get_import(import_id: str, request: Request) -> dict[str, Any]:
        return _translate(lambda: _importer(request).get(import_id))

    @router.post("/{import_id}/apply")
    def apply_import(
        import_id: str,
        payload: ApplyAgentImportRequest,
        request: Request,
    ) -> dict[str, Any]:
        return _translate(
            lambda: _importer(request).apply(
                import_id,
                project_id=payload.project_id,
                confirm=payload.confirm,
                name=payload.name,
                description=payload.description,
                parent_agent_id=payload.parent_agent_id,
            )
        )

    return router


def _importer(request: Request) -> AgentImportService:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(AgentImportService, request.app.state.agent_imports)


def _translate(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except AgentImportError as exc:
        status_code = 404 if exc.code == "agent_import_not_found" else 422
        raise TypedApiError(status_code, exc.code, str(exc)) from exc
    except TypedApiError:
        raise
    except Exception as exc:
        raise TypedApiError(
            500, "local_internal_error", str(exc) or "local service failed"
        ) from exc
