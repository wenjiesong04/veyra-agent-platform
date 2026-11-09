"""Explicitly authorized local desktop system routes."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlsplit

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, Field

from veyra_agent_platform.local.api.projects.routes import TypedApiError
from veyra_agent_platform.local.projects.service import ProjectError, ProjectService
from veyra_agent_platform.local.system import (
    DirectoryPicker,
    DirectorySelection,
    FileSelection,
)
from veyra_agent_platform.local.system.directory_picker import (
    DirectoryPickerError,
    DirectoryPickerUnsupportedError,
)

_DESKTOP_INTENT_HEADER = "X-Veyra-Desktop-Intent"
_LOOPBACK_ORIGIN_HOSTS = {"127.0.0.1", "localhost"}


class SelectedDirectoryResponse(BaseModel):
    """Typed response for a native directory-selection request."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    status: Literal["selected"]
    root_path: str


class CancelledDirectoryResponse(BaseModel):
    """Typed response for a cancelled native directory-selection request."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    status: Literal["cancelled"]
    root_path: None = None


class SelectedArchiveResponse(BaseModel):
    """Typed response for a native archive-selection request."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    status: Literal["selected"]
    path: str


class CancelledArchiveResponse(BaseModel):
    """Typed response for a cancelled native archive-selection request."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    status: Literal["cancelled"]
    path: None = None


class RevealProjectRequest(BaseModel):
    """Reveal only an indexed Project folder; callers never supply a raw path."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)


class RevealedProjectResponse(BaseModel):
    """Typed response after revealing an indexed Project in the file manager."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    status: Literal["revealed"]
    root_path: str


DirectorySelectionResponse = SelectedDirectoryResponse | CancelledDirectoryResponse
ArchiveSelectionResponse = SelectedArchiveResponse | CancelledArchiveResponse


def build_router(picker: DirectoryPicker) -> APIRouter:
    router = APIRouter(prefix="/api/v1/system", tags=["system"])

    @router.post(
        "/select-directory",
        response_model=DirectorySelectionResponse,
        status_code=status.HTTP_200_OK,
    )
    def select_directory(request: Request) -> DirectorySelectionResponse:
        _require_explicit_desktop_intent(request, "select-directory")
        try:
            selection = picker.select_directory()
        except DirectoryPickerUnsupportedError as exc:
            raise TypedApiError(501, "directory_picker_unsupported", str(exc)) from exc
        except DirectoryPickerError as exc:
            raise TypedApiError(500, "directory_picker_failed", str(exc)) from exc
        try:
            return _directory_response(selection)
        except DirectoryPickerError as exc:
            raise TypedApiError(500, "directory_picker_failed", str(exc)) from exc

    @router.post(
        "/select-archive",
        response_model=ArchiveSelectionResponse,
        status_code=status.HTTP_200_OK,
    )
    def select_archive(request: Request) -> ArchiveSelectionResponse:
        _require_explicit_desktop_intent(request, "select-archive")
        try:
            selection = picker.select_archive()
        except DirectoryPickerUnsupportedError as exc:
            raise TypedApiError(501, "directory_picker_unsupported", str(exc)) from exc
        except DirectoryPickerError as exc:
            raise TypedApiError(500, "directory_picker_failed", str(exc)) from exc
        try:
            return _archive_response(selection)
        except DirectoryPickerError as exc:
            raise TypedApiError(500, "directory_picker_failed", str(exc)) from exc

    @router.post(
        "/reveal-project",
        response_model=RevealedProjectResponse,
        status_code=status.HTTP_200_OK,
    )
    def reveal_project(
        payload: RevealProjectRequest, request: Request
    ) -> RevealedProjectResponse:
        _require_explicit_desktop_intent(request, "reveal-project")
        projects = _projects(request)
        try:
            summary = projects.project_summary(payload.project_id)
        except ProjectError as exc:
            raise TypedApiError(422, exc.code, str(exc)) from exc
        root = Path(summary["root_path"])
        try:
            picker.reveal_directory(root)
        except DirectoryPickerUnsupportedError as exc:
            raise TypedApiError(501, "directory_picker_unsupported", str(exc)) from exc
        except DirectoryPickerError as exc:
            raise TypedApiError(500, "directory_picker_failed", str(exc)) from exc
        return RevealedProjectResponse(status="revealed", root_path=str(root))

    return router


def _projects(request: Request) -> ProjectService:
    if not bool(getattr(request.app.state, "database_ready", False)):
        raise TypedApiError(503, "database_unavailable", "local database is starting")
    return cast(ProjectService, request.app.state.projects)


def _require_explicit_desktop_intent(request: Request, intent: str) -> None:
    if request.headers.get(_DESKTOP_INTENT_HEADER) != intent:
        raise TypedApiError(
            403, "desktop_intent_required", "desktop intent is required"
        )
    origin = request.headers.get("origin")
    if origin is not None and not _is_trusted_loopback_origin(origin):
        raise TypedApiError(
            403, "origin_not_allowed", "origin is not a trusted loopback origin"
        )


def _is_trusted_loopback_origin(origin: str) -> bool:
    parsed = urlsplit(origin)
    return (
        parsed.scheme == "http"
        and parsed.hostname in _LOOPBACK_ORIGIN_HOSTS
        and not parsed.username
        and not parsed.password
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


def _directory_response(selection: DirectorySelection) -> DirectorySelectionResponse:
    if not selection.selected:
        return CancelledDirectoryResponse(status="cancelled")
    if selection.path is None:
        raise DirectoryPickerError("selected directory is absent")
    return SelectedDirectoryResponse(
        status="selected",
        root_path=str(selection.path),
    )


def _archive_response(selection: FileSelection) -> ArchiveSelectionResponse:
    if not selection.selected:
        return CancelledArchiveResponse(status="cancelled")
    if selection.path is None:
        raise DirectoryPickerError("selected archive is absent")
    return SelectedArchiveResponse(status="selected", path=str(selection.path))
